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


def _dentro_horario_comercial():
    """Verifica se está dentro do horário permitido para envio."""
    agora = datetime.now()
    if CONFIG.get("apenas_dias_uteis") and agora.weekday() >= 5:  # sáb=5, dom=6
        return False
    hora = agora.hour
    return CONFIG["horario_inicio"] <= hora < CONFIG["horario_fim"]


def _enviar_via_webhook(numero, mensagem):
    """Envia via Evolution API ou webhook genérico."""
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
        # Tenta payload v2 (textMessage); fallback p/ v1 (text) em caso de 400
        payload = {
            "number": digitos,
            "options": {"delay": 1200, "presence": "composing"},
            "textMessage": {"text": mensagem},
        }
    else:
        # Webhook genérico (Z-API ou customizado)
        url     = base_url
        headers = {"Content-Type": "application/json"}
        payload = {"numero": numero, "mensagem": mensagem}

    resp = http_requests.post(url, json=payload, headers=headers, timeout=30)

    # Se v2 falhou com 400, tenta payload v1 simples
    if resp.status_code == 400 and api_key and instance:
        logger.warning("payload v2 retornou 400 (%s) — tentando payload v1", resp.text[:200])
        payload_v1 = {"number": digitos, "text": mensagem}
        resp = http_requests.post(url, json=payload_v1, headers=headers, timeout=30)

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


def enviar_mensagem_whatsapp(empresa_id, numero, nome_empresa, template_id=None):
    """
    Ponto de entrada para envio individual.
    Retorna (sucesso: bool, template_id_usado: int|None)
    """
    if not _numero_valido(numero):
        logger.warning("Número inválido para '%s': %s", nome_empresa, numero)
        registrar_erro_envio(empresa_id, "Número inválido")
        return False, None

    if esta_na_blacklist(numero):
        logger.info("Número na blacklist: %s — pulando.", numero)
        return False, None

    if not _dentro_horario_comercial():
        logger.warning("Fora do horário comercial — envio bloqueado.")
        registrar_erro_envio(empresa_id, "Fora do horário comercial")
        return False, None

    mensagem, tid_usado = obter_mensagem(nome_empresa, template_id)

    try:
        webhook = CONFIG.get("webhook_whatsapp", "").strip()
        if webhook:
            _enviar_via_webhook(numero, mensagem)
        else:
            _enviar_via_pywhatkit(numero, mensagem)

        logger.info("✓ Enviado para %s (%s)", nome_empresa, numero)
        return True, tid_usado

    except Exception as exc:
        msg_erro = str(exc)[:200]
        logger.error("✗ Falha para %s: %s", nome_empresa, msg_erro)
        registrar_erro_envio(empresa_id, msg_erro)
        return False, None


def disparar_lote(empresas, callback_progresso=None):
    """
    Envia para lista de empresas com intervalo anti-ban.
    callback_progresso recebe dict: {atual, total, empresa, sucesso, id, template_id}
    """
    resultados = []
    total = len(empresas)

    for i, emp in enumerate(empresas):
        nome     = emp.get("nome", "Empresa")
        numero   = emp.get("telefone")
        emp_id   = emp.get("id")
        tmpl_id  = emp.get("template_id")

        sucesso, tid = enviar_mensagem_whatsapp(emp_id, numero, nome, tmpl_id)

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

        # Intervalo aleatório — só entre envios (não após o último)
        if i < total - 1:
            seg = random.randint(CONFIG["intervalo_min"], CONFIG["intervalo_max"])
            logger.info("Aguardando %ds...", seg)
            time.sleep(seg)

    enviados = sum(1 for r in resultados if r["sucesso"])
    logger.info("Lote concluído: %d/%d enviados.", enviados, total)
    return resultados
