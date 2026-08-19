"""
Disparo de mensagens WhatsApp.
Suporta pywhatkit (padrão) ou webhook externo (Evolution API / Z-API).
Respeita blacklist, horário comercial e intervalo anti-ban.
"""
import os, re, sys, time, random, logging, threading
from datetime import datetime

import requests as http_requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from database.db import esta_na_blacklist, registrar_erro_envio
from whatsapp.templates import obter_mensagem
from whatsapp.humanizar import humanizar_mensagem, delay_digitacao

logger = logging.getLogger(__name__)

# Validação de número via phonenumbers (opcional)
try:
    import phonenumbers
    def _numero_valido(numero):
        try:
            p = phonenumbers.parse(numero, "BR")
            return phonenumbers.is_valid_number(p)
        except Exception:
            return len(''.join(filter(str.isdigit, numero or ''))) >= 10
except ImportError:
    def _numero_valido(numero):
        return bool(numero) and len(''.join(filter(str.isdigit, numero or ''))) >= 10


def _config_disparo():
    """Lê a configuração de ritmo do disparo do banco (kv), com fallback seguro.
    Chaves: envio_intervalo_min/max (segundos entre envios),
            envio_pausa_cada (contatos), envio_pausa_seg (descanso)."""
    from database.db import get_config

    def _int(chave, padrao):
        try:
            v = get_config(chave, None)
            return int(v) if v not in (None, "") else padrao
        except Exception:
            return padrao

    imin = _int("envio_intervalo_min", CONFIG.get("intervalo_min", 40))
    imax = _int("envio_intervalo_max", CONFIG.get("intervalo_max", 90))
    if imax < imin:
        imax = imin
    return {
        "intervalo_min": max(1, imin),
        "intervalo_max": max(1, imax),
        "pausa_cada":    max(0, _int("envio_pausa_cada", 20)),
        "pausa_seg":     max(0, _int("envio_pausa_seg", 300)),
        "limite_dia":    max(0, _int("envio_limite_dia", 200)),
        "warmup":        (get_config("envio_warmup", "on") or "on").lower() != "off",
    }


# Rampa de aquecimento (warm-up): teto de envios por dia conforme a idade do
# número no disparo. Número novo que dispara 300 no dia 1 é banido na hora —
# WhatsApp espera crescimento gradual. Dia 7+ libera o limite configurado.
_WARMUP_RAMPA = {1: 30, 2: 60, 3: 90, 4: 120, 5: 170, 6: 220}


def _limite_diario_efetivo(cfg):
    """Teto de envios para HOJE. Combina o limite configurado com a rampa de
    aquecimento (se ligada). Retorna 0 = sem limite."""
    from database.db import get_config, set_config

    limite = cfg.get("limite_dia", 0)
    if not cfg.get("warmup"):
        return limite

    # Marca o primeiro dia de disparo na primeira vez que roda.
    primeiro = get_config("wa_primeiro_disparo", None)
    hoje = datetime.now().date()
    if not primeiro:
        set_config("wa_primeiro_disparo", hoje.isoformat())
        dias = 1
    else:
        try:
            d0 = datetime.fromisoformat(primeiro).date()
            dias = max(1, (hoje - d0).days + 1)
        except Exception:
            dias = 1

    teto_rampa = _WARMUP_RAMPA.get(dias)  # None = dia 7+ (sem teto de rampa)
    if teto_rampa is None:
        return limite
    if limite <= 0:
        return teto_rampa
    return min(limite, teto_rampa)


def _dentro_horario_comercial():
    """Verifica se está dentro do horário permitido para envio."""
    agora = datetime.now()
    if CONFIG.get("apenas_dias_uteis") and agora.weekday() >= 5:  # sáb=5, dom=6
        return False
    hora = agora.hour
    return CONFIG["horario_inicio"] <= hora < CONFIG["horario_fim"]


def _enviar_via_webhook(numero, mensagem, delay_ms=None):
    """Envia via Evolution API ou webhook genérico."""
    base_url = CONFIG.get("webhook_whatsapp", "").strip()
    if not base_url:
        raise ValueError("webhook_whatsapp não configurado")

    api_key = CONFIG.get("evolution_api_key", "").strip()
    instance = CONFIG.get("evolution_instance", "").strip()

    if api_key and instance:
        from whatsapp.evolution import EvolutionClient
        EvolutionClient(base_url=base_url, instance=instance, api_key=api_key).send_text(
            numero, mensagem, delay_ms=delay_ms,
        )
        return True

    # Webhook genérico (Z-API/customizado) permanece compatível.
    resp = http_requests.post(
        base_url,
        json={"numero": numero, "mensagem": mensagem},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if not resp.ok:
        raise Exception(f"{resp.status_code} {resp.reason} — {resp.text[:300]}")
    return True


def _enviar_via_pywhatkit(numero, mensagem):
    """Envia via pywhatkit (WhatsApp Web automatizado — só funciona localmente com tela)."""
    try:
        import pywhatkit as kit
    except ImportError:
        raise RuntimeError(
            "pywhatkit não está instalado. "
            "No servidor configure WEBHOOK_WHATSAPP com Evolution API ou Z-API."
        )
    kit.sendwhatmsg_instantly(
        phone_no=numero,
        message=mensagem,
        wait_time=15,
        tab_close=True,
        close_time=3,
    )
    return True


def enviar_mensagem_whatsapp(empresa_id, numero, nome_empresa, template_id=None,
                             mensagem_custom=None, ignorar_horario=False):
    """
    Ponto de entrada para envio individual.
    mensagem_custom: se fornecida (ex: Gemini), usa diretamente (ignora template).
    ignorar_horario: envio manual — não bloqueia fora do horário comercial.
    Retorna (sucesso: bool, template_id_usado: int|None, falha_tipo: str|None)
    """
    if not _numero_valido(numero):
        logger.warning("Número inválido para '%s': %s", nome_empresa, numero)
        registrar_erro_envio(empresa_id, "Número inválido")
        return False, None, "numero_invalido"

    if esta_na_blacklist(numero):
        logger.info("Número na blacklist: %s — pulando.", numero)
        return False, None, "blacklist"

    if not ignorar_horario and not _dentro_horario_comercial():
        logger.warning("Fora do horário comercial — envio bloqueado.")
        registrar_erro_envio(empresa_id, "Fora do horário comercial")
        return False, None, "fora_horario"

    if mensagem_custom:
        mensagem  = mensagem_custom
        tid_usado = None
    else:
        mensagem, tid_usado = obter_mensagem(nome_empresa, template_id)

    # Variação editorial explícita do template (spintax); sem caracteres ocultos.
    mensagem = humanizar_mensagem(mensagem)

    try:
        webhook = CONFIG.get("webhook_whatsapp", "").strip()
        if webhook:
            _enviar_via_webhook(numero, mensagem, delay_ms=delay_digitacao(mensagem))
        else:
            _enviar_via_pywhatkit(numero, mensagem)

        logger.info("✓ Enviado para %s (%s)%s", nome_empresa, numero,
                    " [Gemini]" if mensagem_custom else "")
        return True, tid_usado, None

    except Exception as exc:
        msg_erro = str(exc)[:200]
        logger.error("✗ Falha para %s: %s", nome_empresa, msg_erro)
        registrar_erro_envio(empresa_id, msg_erro)
        return False, None, "api"


def disparar_lote(empresas, callback_progresso=None, ignorar_horario=False):
    """
    Envia para lista de empresas com intervalo anti-ban.
    callback_progresso recebe dict: {atual, total, empresa, sucesso, id, template_id}
    ignorar_horario: envio manual — não bloqueia fora do horário comercial.
    """
    resultados = []
    total = len(empresas)
    cfg = _config_disparo()
    imin, imax = cfg["intervalo_min"], cfg["intervalo_max"]
    pausa_cada, pausa_seg = cfg["pausa_cada"], cfg["pausa_seg"]
    falhas_consecutivas = 0

    empresas = list(empresas)

    # Limite operacional diário + rampa conservadora para contas novas.
    from database.db import contagem_enviadas_hoje
    cap = _limite_diario_efetivo(cfg)
    if cap > 0:
        enviados_hoje = contagem_enviadas_hoje()
        restante = cap - enviados_hoje
        if restante <= 0:
            logger.warning("Limite diário atingido (%d/%d) — disparo bloqueado.", enviados_hoje, cap)
            if callback_progresso:
                callback_progresso({
                    "atual": 0, "total": total,
                    "empresa": f"Limite diário atingido ({enviados_hoje}/{cap}). Envio adiado.",
                    "sucesso": None, "id": None, "template_id": None, "limite": cap,
                })
            return []
        if len(empresas) > restante:
            logger.info("Limite diário: enviando %d de %d (restam %d hoje).",
                        restante, total, restante)
            empresas = empresas[:restante]
            total = len(empresas)

    for i, emp in enumerate(empresas):
        nome      = emp.get("nome", "Empresa")
        numero    = emp.get("telefone")
        emp_id    = emp.get("id")
        tmpl_id   = emp.get("template_id")
        msg_gemini = emp.get("gemini_mensagem")

        sucesso, tid, falha_tipo = enviar_mensagem_whatsapp(
            emp_id, numero, nome, tmpl_id, msg_gemini, ignorar_horario=ignorar_horario)

        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid, "falha_tipo": falha_tipo})

        if falha_tipo == "api":
            falhas_consecutivas += 1
        else:
            falhas_consecutivas = 0

        if callback_progresso:
            callback_progresso({
                "atual":       i + 1,
                "total":       total,
                "empresa":     nome,
                "sucesso":     sucesso,
                "id":          emp_id,
                "template_id": tid,
            })

        if falhas_consecutivas >= 2:
            logger.error("Circuit breaker: %d falhas consecutivas; lote interrompido.", falhas_consecutivas)
            if callback_progresso:
                callback_progresso({
                    "atual": i + 1, "total": total,
                    "empresa": "Lote interrompido após falhas consecutivas. Verifique a conexão/API.",
                    "sucesso": None, "id": None, "template_id": None, "interrompido": True,
                })
            break

        if i < total - 1:  # nada após o último
            enviados_ate_agora = i + 1
            # Pausa longa a cada X contatos (descanso anti-ban, estilo WaSeller).
            if pausa_cada > 0 and pausa_seg > 0 and enviados_ate_agora % pausa_cada == 0:
                logger.info("Pausa de descanso: %ds após %d contatos.", pausa_seg, enviados_ate_agora)
                if callback_progresso:
                    callback_progresso({
                        "atual": enviados_ate_agora, "total": total,
                        "empresa": f"Pausa de {pausa_seg}s (descanso anti-ban)...",
                        "sucesso": None, "id": None, "template_id": None, "pausa": pausa_seg,
                    })
                time.sleep(pausa_seg)
            else:
                seg = random.randint(imin, imax)
                logger.info("Aguardando %ds...", seg)
                time.sleep(seg)

    enviados = sum(1 for r in resultados if r["sucesso"])
    logger.info("Lote concluído: %d/%d enviados.", enviados, total)
    return resultados


# ── Guard de idempotência de lote ─────────────────────────────────────────────
_DISPARO_LOCK = threading.Lock()
_disparar_lote_base = disparar_lote


def _chave_empresa_lote(emp):
    if emp.get("id") is not None:
        return ("id", str(emp.get("id")))
    digitos = re.sub(r"\D", "", emp.get("telefone") or "")
    return ("telefone", digitos) if digitos else ("obj", id(emp))


def disparar_lote(empresas, callback_progresso=None, ignorar_horario=False):
    """Serializa lotes e remove/revalida duplicatas antes de qualquer envio."""
    from database.db import buscar_empresa_por_id

    with _DISPARO_LOCK:
        if (CONFIG.get("webhook_whatsapp") and CONFIG.get("evolution_api_key") and CONFIG.get("evolution_instance")):
            from whatsapp.evolution import EvolutionClient
            estado = EvolutionClient().connection_state()
            if not estado.get("conectado"):
                msg = f"Evolution indisponível antes do lote (state={estado.get('state') or '?'}): {estado.get('erro') or 'instância não conectada'}"
                logger.error(msg)
                if callback_progresso:
                    callback_progresso({
                        "atual": 0, "total": len(empresas), "empresa": msg,
                        "sucesso": None, "id": None, "template_id": None,
                        "interrompido": True, "motivo": "evolution_offline",
                    })
                return []

        filtradas = []
        vistos = set()
        for original in empresas:
            chave = _chave_empresa_lote(original)
            if chave in vistos:
                logger.warning("Lote: duplicata ignorada (%s).", chave)
                continue
            vistos.add(chave)

            emp_id = original.get("id")
            if emp_id is not None:
                atual = buscar_empresa_por_id(emp_id)
                if not atual:
                    logger.warning("Lote: empresa id=%s não existe mais; ignorando.", emp_id)
                    continue
                if atual.get("mensagem_enviada"):
                    logger.info("Lote: empresa id=%s já enviada; ignorando re-disparo.", emp_id)
                    continue
                # Preserva overrides da chamada atual (mensagem/template manual).
                if original.get("gemini_mensagem"):
                    atual["gemini_mensagem"] = original["gemini_mensagem"]
                if original.get("template_id") is not None:
                    atual["template_id"] = original["template_id"]
                filtradas.append(atual)
            else:
                filtradas.append(original)

        if not filtradas:
            logger.info("Lote sem empresas elegíveis após deduplicação/revalidação.")
            return []

        return _disparar_lote_base(
            filtradas, callback_progresso=callback_progresso,
            ignorar_horario=ignorar_horario,
        )
