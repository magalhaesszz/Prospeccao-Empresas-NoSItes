"""Fase 2: centraliza Evolution, alinha limites e melhora diagnóstico de envio."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = read(path)
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: esperado 1 trecho, encontrado {n}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path, pattern, repl, flags=0):
    text = read(path)
    new, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f"{path}: regex sem match único: {pattern[:120]!r}")
    write(path, new)


# Ritmo padrão consistente com o painel. O banco continua podendo sobrescrever.
replace_once(
    "config.py",
    '    "intervalo_min":    int(os.environ.get("WA_INTERVALO_MIN", "8")),\n'
    '    "intervalo_max":    int(os.environ.get("WA_INTERVALO_MAX", "15")),\n',
    '    "intervalo_min":    int(os.environ.get("WA_INTERVALO_MIN", "40")),\n'
    '    "intervalo_max":    int(os.environ.get("WA_INTERVALO_MAX", "90")),\n',
)
replace_once(
    ".env.example",
    'WA_INTERVALO_MIN=8\nWA_INTERVALO_MAX=15\n',
    'WA_INTERVALO_MIN=40\nWA_INTERVALO_MAX=90\n',
)

# ---------------------------------------------------------------------------
# whatsapp/disparar.py: Evolution central + falhas classificadas.
# ---------------------------------------------------------------------------
regex_once(
    "whatsapp/disparar.py",
    r'def _enviar_via_webhook\(numero, mensagem, delay_ms=None\):.*?\n\ndef _enviar_via_pywhatkit',
    '''def _enviar_via_webhook(numero, mensagem, delay_ms=None):
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


def _enviar_via_pywhatkit''',
    flags=re.S,
)

# Retorno passa a incluir a categoria da falha. Assim blacklist/número inválido
# não acionam o circuit breaker de infraestrutura.
replace_once(
    "whatsapp/disparar.py",
    '        return False, None\n\n    if esta_na_blacklist(numero):',
    '        return False, None, "numero_invalido"\n\n    if esta_na_blacklist(numero):',
)
replace_once(
    "whatsapp/disparar.py",
    '        logger.info("Número na blacklist: %s — pulando.", numero)\n'
    '        return False, None\n',
    '        logger.info("Número na blacklist: %s — pulando.", numero)\n'
    '        return False, None, "blacklist"\n',
)
replace_once(
    "whatsapp/disparar.py",
    '        registrar_erro_envio(empresa_id, "Fora do horário comercial")\n'
    '        return False, None\n',
    '        registrar_erro_envio(empresa_id, "Fora do horário comercial")\n'
    '        return False, None, "fora_horario"\n',
)
replace_once(
    "whatsapp/disparar.py",
    '        return True, tid_usado\n\n    except Exception as exc:',
    '        return True, tid_usado, None\n\n    except Exception as exc:',
)
replace_once(
    "whatsapp/disparar.py",
    '        registrar_erro_envio(empresa_id, msg_erro)\n'
    '        return False, None\n',
    '        registrar_erro_envio(empresa_id, msg_erro)\n'
    '        return False, None, "api"\n',
)
replace_once(
    "whatsapp/disparar.py",
    '        sucesso, tid = enviar_mensagem_whatsapp(\n'
    '            emp_id, numero, nome, tmpl_id, msg_gemini, ignorar_horario=ignorar_horario)\n\n'
    '        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid})\n\n'
    '        if sucesso:\n'
    '            falhas_consecutivas = 0\n'
    '        else:\n'
    '            falhas_consecutivas += 1\n',
    '        sucesso, tid, falha_tipo = enviar_mensagem_whatsapp(\n'
    '            emp_id, numero, nome, tmpl_id, msg_gemini, ignorar_horario=ignorar_horario)\n\n'
    '        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid, "falha_tipo": falha_tipo})\n\n'
    '        if falha_tipo == "api":\n'
    '            falhas_consecutivas += 1\n'
    '        else:\n'
    '            falhas_consecutivas = 0\n',
)

# Corrige docstring da assinatura nova.
replace_once(
    "whatsapp/disparar.py",
    '    Retorna (sucesso: bool, template_id_usado: int|None)\n',
    '    Retorna (sucesso: bool, template_id_usado: int|None, falha_tipo: str|None)\n',
)

# Preflight da Evolution antes de qualquer contato do lote.
replace_once(
    "whatsapp/disparar.py",
    '    with _DISPARO_LOCK:\n'
    '        filtradas = []\n',
    '    with _DISPARO_LOCK:\n'
    '        if (CONFIG.get("webhook_whatsapp") and CONFIG.get("evolution_api_key") and CONFIG.get("evolution_instance")):\n'
    '            from whatsapp.evolution import EvolutionClient\n'
    '            estado = EvolutionClient().connection_state()\n'
    '            if not estado.get("conectado"):\n'
    '                msg = f"Evolution indisponível antes do lote (state={estado.get(\'state\') or \'?\'}): {estado.get(\'erro\') or \'instância não conectada\'}"\n'
    '                logger.error(msg)\n'
    '                if callback_progresso:\n'
    '                    callback_progresso({\n'
    '                        "atual": 0, "total": len(empresas), "empresa": msg,\n'
    '                        "sucesso": None, "id": None, "template_id": None,\n'
    '                        "interrompido": True, "motivo": "evolution_offline",\n'
    '                    })\n'
    '                return []\n\n'
    '        filtradas = []\n',
)

# Remove comentários que descreviam o mecanismo como evasão de detecção.
replace_once(
    "whatsapp/disparar.py",
    '    # Anti-ban: resolve spintax e injeta variação invisível para que nenhuma\n'
    '    # mensagem saia idêntica a outra (esconde o padrão de disparo em massa).\n'
    '    mensagem = humanizar_mensagem(mensagem)\n',
    '    # Variação editorial explícita do template (spintax); sem caracteres ocultos.\n'
    '    mensagem = humanizar_mensagem(mensagem)\n',
)
replace_once(
    "whatsapp/disparar.py",
    '    # Anti-ban: respeita o teto de envios do dia (limite + rampa de aquecimento).\n',
    '    # Limite operacional diário + rampa conservadora para contas novas.\n',
)

# ---------------------------------------------------------------------------
# app.py: status e chat manual passam pelo mesmo EvolutionClient.
# ---------------------------------------------------------------------------
regex_once(
    "app.py",
    r'@app\.route\("/api/whatsapp/status"\)\ndef api_wa_status\(\):.*?\n\n@app\.route\("/api/whatsapp/qrcode"\)',
    '''@app.route("/api/whatsapp/status")
@app.route("/api/whatsapp/diagnostico")
def api_wa_status():
    """Diagnóstico sem efeito colateral da instância Evolution."""
    from whatsapp.evolution import EvolutionClient
    return jsonify(EvolutionClient().diagnostico())


@app.route("/api/whatsapp/qrcode")''',
    flags=re.S,
)

regex_once(
    "app.py",
    r'def _wa_send_text\(numero, texto, quoted=None\):.*?\n\n@app\.route\("/api/whatsapp/responder"',
    '''def _wa_send_text(numero, texto, quoted=None):
    """Envia texto pelo cliente Evolution central, com fallback genérico."""
    base, instance, api_key = _wa_config()
    if base and instance and api_key:
        from whatsapp.evolution import EvolutionClient
        from whatsapp.humanizar import delay_digitacao
        EvolutionClient(base_url=base, instance=instance, api_key=api_key).send_text(
            numero, texto, delay_ms=delay_digitacao(texto), quoted=quoted,
        )
        return True
    from whatsapp.disparar import _enviar_via_webhook
    return _enviar_via_webhook(numero, texto)


@app.route("/api/whatsapp/responder"''',
    flags=re.S,
)

replace_once(
    "app.py",
    'def _wa_numero_e2(numero):\n'
    '    """Normaliza número para o formato da Evolution (55 + dígitos)."""\n'
    '    dig = _so_digitos(numero)\n'
    '    if dig and not dig.startswith("55"):\n'
    '        dig = "55" + dig\n'
    '    return dig\n',
    'def _wa_numero_e2(numero):\n'
    '    """Normaliza número para o formato da Evolution (55 + dígitos)."""\n'
    '    from whatsapp.evolution import EvolutionClient\n'
    '    return EvolutionClient.normalizar_numero(numero)\n',
)

print("Fase 2 aplicada com sucesso.")
