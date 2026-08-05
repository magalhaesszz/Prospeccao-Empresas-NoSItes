"""
Disparo de mensagens WhatsApp.
Suporta pywhatkit (padrão) ou webhook externo (Evolution API / Z-API).
Respeita blacklist, horário comercial e intervalo anti-ban.
"""
import os, re, sys, time, random, logging
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
    }


def _dentro_horario_comercial():
    """Verifica se está dentro do horário permitido para envio."""
    agora = datetime.now()
    if CONFIG.get("apenas_dias_uteis") and agora.weekday() >= 5:  # sáb=5, dom=6
        return False
    hora = agora.hour
    return CONFIG["horario_inicio"] <= hora < CONFIG["horario_fim"]


def _enviar_via_webhook(numero, mensagem, delay_ms=None):
    """Envia via Evolution API ou webhook genérico.
    delay_ms: tempo de 'digitando...' que a Evolution mostra antes de enviar
    (simulação humana anti-ban). Ignorado no webhook genérico."""
    base_url = CONFIG.get("webhook_whatsapp", "").strip()
    if not base_url:
        raise ValueError("webhook_whatsapp não configurado")

    api_key  = CONFIG.get("evolution_api_key",  "").strip()
    instance = CONFIG.get("evolution_instance", "").strip()

    if api_key and instance:
        # Extrai só dígitos; garante código 55 (Brasil)
        digitos = re.sub(r"\D", "", numero)
        if not digitos.startswith("55"):
            digitos = "55" + digitos
        url     = f"{base_url.rstrip('/')}/message/sendText/{instance}"
        headers = {"apikey": api_key, "Content-Type": "application/json"}
        # Payload flat {number,text} — mesmo formato do chat, que funciona nesta
        # versão da Evolution (2.3.x). O formato antigo {textMessage:{text}} falhava.
        # delay + presence: Evolution mostra "digitando..." pelo tempo do delay
        # antes de enviar. Faz o envio parecer digitação humana (anti-ban).
        payload = {"number": digitos, "text": mensagem}
        if delay_ms and delay_ms > 0:
            payload["delay"] = int(delay_ms)
            payload["presence"] = "composing"
    else:
        # Webhook genérico (Z-API ou customizado)
        url     = base_url
        headers = {"Content-Type": "application/json"}
        payload = {"numero": numero, "mensagem": mensagem}

    resp = http_requests.post(url, json=payload, headers=headers, timeout=30)

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
    Retorna (sucesso: bool, template_id_usado: int|None)
    """
    if not _numero_valido(numero):
        logger.warning("Número inválido para '%s': %s", nome_empresa, numero)
        registrar_erro_envio(empresa_id, "Número inválido")
        return False, None

    if esta_na_blacklist(numero):
        logger.info("Número na blacklist: %s — pulando.", numero)
        return False, None

    if not ignorar_horario and not _dentro_horario_comercial():
        logger.warning("Fora do horário comercial — envio bloqueado.")
        registrar_erro_envio(empresa_id, "Fora do horário comercial")
        return False, None

    if mensagem_custom:
        mensagem  = mensagem_custom
        tid_usado = None
    else:
        mensagem, tid_usado = obter_mensagem(nome_empresa, template_id)

    # Anti-ban: resolve spintax e injeta variação invisível para que nenhuma
    # mensagem saia idêntica a outra (esconde o padrão de disparo em massa).
    mensagem = humanizar_mensagem(mensagem)

    try:
        webhook = CONFIG.get("webhook_whatsapp", "").strip()
        if webhook:
            _enviar_via_webhook(numero, mensagem, delay_ms=delay_digitacao(mensagem))
        else:
            _enviar_via_pywhatkit(numero, mensagem)

        logger.info("✓ Enviado para %s (%s)%s", nome_empresa, numero,
                    " [Gemini]" if mensagem_custom else "")
        return True, tid_usado

    except Exception as exc:
        msg_erro = str(exc)[:200]
        logger.error("✗ Falha para %s: %s", nome_empresa, msg_erro)
        registrar_erro_envio(empresa_id, msg_erro)
        return False, None


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

    # Anti-ban: embaralha a ordem para não enviar numa sequência previsível.
    empresas = list(empresas)
    random.shuffle(empresas)

    for i, emp in enumerate(empresas):
        nome      = emp.get("nome", "Empresa")
        numero    = emp.get("telefone")
        emp_id    = emp.get("id")
        tmpl_id   = emp.get("template_id")
        msg_gemini = emp.get("gemini_mensagem")

        sucesso, tid = enviar_mensagem_whatsapp(
            emp_id, numero, nome, tmpl_id, msg_gemini, ignorar_horario=ignorar_horario)

        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid})

        if callback_progresso:
            callback_progresso({
                "atual":       i + 1,
                "total":       total,
                "empresa":     nome,
                "sucesso":     sucesso,
                "id":          emp_id,
                "template_id": tid,
            })

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
