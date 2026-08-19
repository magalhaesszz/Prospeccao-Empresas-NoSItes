"""Aplica a primeira reorganização do Prospector de forma determinística.

O script é intencionalmente conservador: cada alteração exige que o trecho
esperado exista exatamente uma vez. Se o código divergir, falha sem gravar uma
substituição ambígua.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = _read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: esperado 1 trecho, encontrado {count}: {old[:100]!r}")
    _write(path, text.replace(old, new, 1))


def regex_once(path, pattern, repl, flags=0):
    text = _read(path)
    new, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{path}: regex não encontrou exatamente um trecho: {pattern[:120]!r}")
    _write(path, new)


# ---------------------------------------------------------------------------
# 1) Configuração: modelos deixam de ficar hardcoded em múltiplos arquivos.
# ---------------------------------------------------------------------------
replace_once(
    "config.py",
    '    "groq_api_key":       os.environ.get("GROQ_API_KEY",       ""),\n'
    '    "openrouter_api_key": os.environ.get("OPENROUTER_API_KEY", ""),\n',
    '    "groq_api_key":       os.environ.get("GROQ_API_KEY",       ""),\n'
    '    "openrouter_api_key": os.environ.get("OPENROUTER_API_KEY", ""),\n'
    '    "groq_model":         os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),\n'
    '    "openrouter_model":   os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),\n',
)

# ---------------------------------------------------------------------------
# 2) Enricher passa a usar o cliente central de IA.
# ---------------------------------------------------------------------------
regex_once(
    "ai/enricher.py",
    r'_MODELO_GROQ\s*=.*?\n\n\ndef _strip_markdown',
    'from ai.provider import gerar_texto as _provider_gerar\n\n\n'
    'def _gerar(prompt, api_key, max_tokens=4096, timeout=90.0, temperature=0.7, system=None):\n'
    '    return _provider_gerar(\n'
    '        prompt, api_key=api_key, max_tokens=max_tokens, timeout=timeout,\n'
    '        temperature=temperature, system=system,\n'
    '    )\n\n\n'
    'def _strip_markdown',
    flags=re.S,
)

# ---------------------------------------------------------------------------
# 3) app.py usa o mesmo cliente; remove segundo hardcode de modelo.
# ---------------------------------------------------------------------------
replace_once(
    "app.py",
    'from export.csv_export import exportar_csv\n',
    'from export.csv_export import exportar_csv\n'
    'from ai.provider import get_api_key as _provider_api_key, gerar_texto as _provider_gerar\n',
)

regex_once(
    "app.py",
    r'def _ai_api_key\(\):.*?\n\n# Job store para geração assíncrona de páginas',
    'def _ai_api_key():\n'
    '    return _provider_api_key()\n\n\n'
    'def _ai_gerar(prompt):\n'
    '    return _provider_gerar(prompt)\n\n\n'
    '# Job store para geração assíncrona de páginas',
    flags=re.S,
)

# Corrige contagem: eventos de pausa/limite usam sucesso=None e não são falhas.
replace_once(
    "app.py",
    '            elif not info.get("sucesso"):\n',
    '            elif info.get("sucesso") is False:\n',
)

# Reserva a busca de forma atômica antes de iniciar a thread. O check inicial
# continua servindo para detectar timeout; este segundo check fecha a race window.
replace_once(
    "app.py",
    '    if not cidade or not categoria:\n'
    '        return jsonify({"erro": "Cidade e categoria são obrigatórios."}), 400\n\n'
    '    threading.Thread(target=_executar_busca, args=(cidade, categoria, quantidade), daemon=True).start()\n',
    '    if not cidade or not categoria:\n'
    '        return jsonify({"erro": "Cidade e categoria são obrigatórios."}), 400\n\n'
    '    with _lock:\n'
    '        if _estado["scraping"]:\n'
    '            return jsonify({"erro": "Busca já em andamento."}), 400\n'
    '        _estado["scraping"] = True\n'
    '        _estado["scraping_inicio"] = time.time()\n\n'
    '    threading.Thread(target=_executar_busca, args=(cidade, categoria, quantidade), daemon=True).start()\n',
)

# Remove IDs repetidos antes de construir um lote manual.
replace_once(
    "app.py",
    '    empresas = []\n'
    '    for eid in ids:\n'
    '        emp = buscar_empresa_por_id(eid)\n',
    '    empresas = []\n'
    '    ids_vistos = set()\n'
    '    for eid in ids:\n'
    '        chave_id = str(eid)\n'
    '        if chave_id in ids_vistos:\n'
    '            continue\n'
    '        ids_vistos.add(chave_id)\n'
    '        emp = buscar_empresa_por_id(eid)\n',
)

# Reserva envio antes da thread para dois cliques/retries não passarem juntos.
replace_once(
    "app.py",
    '    if not empresas:\n'
    '        return jsonify({"erro": "Nenhuma empresa válida (sem telefone ou já enviada)."}), 400\n\n'
    '    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n',
    '    if not empresas:\n'
    '        return jsonify({"erro": "Nenhuma empresa válida (sem telefone ou já enviada)."}), 400\n\n'
    '    with _lock:\n'
    '        if _estado["enviando"]:\n'
    '            return jsonify({"erro": "Envio já em andamento."}), 400\n'
    '        _estado.update({"enviando": True, "envio_progresso": 0, "envio_total": len(empresas)})\n\n'
    '    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n',
)

# Mesmo fechamento da race para o botão "disparar pendentes".
replace_once(
    "app.py",
    '    if not empresas:\n'
    '        return jsonify({"erro": "Nenhuma empresa pendente."}), 400\n\n'
    '    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n'
    '    return jsonify({"mensagem": f"Disparo iniciado para {len(empresas)} empresa(s) pendente(s)."})\n',
    '    if not empresas:\n'
    '        return jsonify({"erro": "Nenhuma empresa pendente."}), 400\n\n'
    '    with _lock:\n'
    '        if _estado["enviando"]:\n'
    '            return jsonify({"erro": "Envio já em andamento."}), 400\n'
    '        _estado.update({"enviando": True, "envio_progresso": 0, "envio_total": len(empresas)})\n\n'
    '    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n'
    '    return jsonify({"mensagem": f"Disparo iniciado para {len(empresas)} empresa(s) pendente(s)."})\n',
)

# Agendador também reserva o envio atomicamente antes de criar a thread.
replace_once(
    "app.py",
    '        atualizar_ultima_execucao(ag["id"], enviados_hoje + len(empresas))\n'
    '        logger.info("[agendador] Agendamento \'%s\': %d empresas para disparar", ag["nome"], len(empresas))\n'
    '        threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n'
    '        break  # uma rodada por minuto\n',
    '        with _lock:\n'
    '            if _estado["enviando"]:\n'
    '                continue\n'
    '            _estado.update({"enviando": True, "envio_progresso": 0, "envio_total": len(empresas)})\n\n'
    '        atualizar_ultima_execucao(ag["id"], enviados_hoje + len(empresas))\n'
    '        logger.info("[agendador] Agendamento \'%s\': %d empresas para disparar", ag["nome"], len(empresas))\n'
    '        threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()\n'
    '        break  # uma rodada por minuto\n',
)

# ---------------------------------------------------------------------------
# 4) Disparos: serialização, dedupe, rechecagem no banco e circuit breaker.
# ---------------------------------------------------------------------------
replace_once(
    "whatsapp/disparar.py",
    'import os, re, sys, time, random, logging\n',
    'import os, re, sys, time, random, logging, threading\n',
)

# Ordem de envio deixa de ser embaralhada. Segurança passa a vir de limites,
# consentimento/blacklist e idempotência, não de tentativa de esconder padrão.
replace_once(
    "whatsapp/disparar.py",
    '    # Anti-ban: embaralha a ordem para não enviar numa sequência previsível.\n'
    '    empresas = list(empresas)\n'
    '    random.shuffle(empresas)\n\n',
    '    empresas = list(empresas)\n\n',
)

replace_once(
    "whatsapp/disparar.py",
    '    pausa_cada, pausa_seg = cfg["pausa_cada"], cfg["pausa_seg"]\n\n'
    '    empresas = list(empresas)\n',
    '    pausa_cada, pausa_seg = cfg["pausa_cada"], cfg["pausa_seg"]\n'
    '    falhas_consecutivas = 0\n\n'
    '    empresas = list(empresas)\n',
)

replace_once(
    "whatsapp/disparar.py",
    '        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid})\n\n'
    '        if callback_progresso:\n',
    '        resultados.append({"id": emp_id, "nome": nome, "sucesso": sucesso, "template_id": tid})\n\n'
    '        if sucesso:\n'
    '            falhas_consecutivas = 0\n'
    '        else:\n'
    '            falhas_consecutivas += 1\n\n'
    '        if callback_progresso:\n',
)

# Para depois de duas falhas consecutivas de envio. Isso evita continuar um lote
# quando a instância/API está quebrada ou desconectada.
replace_once(
    "whatsapp/disparar.py",
    '        if i < total - 1:  # nada após o último\n',
    '        if falhas_consecutivas >= 2:\n'
    '            logger.error("Circuit breaker: %d falhas consecutivas; lote interrompido.", falhas_consecutivas)\n'
    '            if callback_progresso:\n'
    '                callback_progresso({\n'
    '                    "atual": i + 1, "total": total,\n'
    '                    "empresa": "Lote interrompido após falhas consecutivas. Verifique a conexão/API.",\n'
    '                    "sucesso": None, "id": None, "template_id": None, "interrompido": True,\n'
    '                })\n'
    '            break\n\n'
    '        if i < total - 1:  # nada após o último\n',
)

# Wrapper idempotente: mesmo que duas threads escapem do app, somente um lote
# executa por vez e cada empresa é revalidada no banco imediatamente antes.
disparar_path = ROOT / "whatsapp/disparar.py"
disparar_text = disparar_path.read_text(encoding="utf-8")
marker = "# ── Guard de idempotência de lote ──"
if marker in disparar_text:
    raise RuntimeError("whatsapp/disparar.py: guard já aplicado")
disparar_text += '''\n\n# ── Guard de idempotência de lote ─────────────────────────────────────────────\n_DISPARO_LOCK = threading.Lock()\n_disparar_lote_base = disparar_lote\n\n\ndef _chave_empresa_lote(emp):\n    if emp.get("id") is not None:\n        return ("id", str(emp.get("id")))\n    digitos = re.sub(r"\\D", "", emp.get("telefone") or "")\n    return ("telefone", digitos) if digitos else ("obj", id(emp))\n\n\ndef disparar_lote(empresas, callback_progresso=None, ignorar_horario=False):\n    """Serializa lotes e remove/revalida duplicatas antes de qualquer envio."""\n    from database.db import buscar_empresa_por_id\n\n    with _DISPARO_LOCK:\n        filtradas = []\n        vistos = set()\n        for original in empresas:\n            chave = _chave_empresa_lote(original)\n            if chave in vistos:\n                logger.warning("Lote: duplicata ignorada (%s).", chave)\n                continue\n            vistos.add(chave)\n\n            emp_id = original.get("id")\n            if emp_id is not None:\n                atual = buscar_empresa_por_id(emp_id)\n                if not atual:\n                    logger.warning("Lote: empresa id=%s não existe mais; ignorando.", emp_id)\n                    continue\n                if atual.get("mensagem_enviada"):\n                    logger.info("Lote: empresa id=%s já enviada; ignorando re-disparo.", emp_id)\n                    continue\n                # Preserva overrides da chamada atual (mensagem/template manual).\n                if original.get("gemini_mensagem"):\n                    atual["gemini_mensagem"] = original["gemini_mensagem"]\n                if original.get("template_id") is not None:\n                    atual["template_id"] = original["template_id"]\n                filtradas.append(atual)\n            else:\n                filtradas.append(original)\n\n        if not filtradas:\n            logger.info("Lote sem empresas elegíveis após deduplicação/revalidação.")\n            return []\n\n        return _disparar_lote_base(\n            filtradas, callback_progresso=callback_progresso,\n            ignorar_horario=ignorar_horario,\n        )\n'''
disparar_path.write_text(disparar_text, encoding="utf-8")

# ---------------------------------------------------------------------------
# 5) Humanização: remove caracteres invisíveis usados para alterar assinatura.
# Spintax fica como simples recurso editorial; delay continua apenas como UX.
# ---------------------------------------------------------------------------
(ROOT / "whatsapp/humanizar.py").write_text('''"""Utilidades de variação editorial e tempo de digitação do WhatsApp.

Não altera a assinatura da mensagem com caracteres invisíveis. Variações de
texto devem ser explícitas no template via spintax `{a|b|c}`.
"""
import random
import re

_SPINTAX_RE = re.compile(r"\\{([^{}]*)\\}")


def expandir_spintax(texto):
    """Resolve `{a|b|c}` escolhendo uma opção aleatória."""
    if not texto or "{" not in texto:
        return texto or ""

    def _troca(m):
        return random.choice(m.group(1).split("|"))

    atual = texto
    for _ in range(20):
        if "{" not in atual:
            break
        novo = _SPINTAX_RE.sub(_troca, atual)
        if novo == atual:
            break
        atual = novo
    return atual


def humanizar_mensagem(texto, variar_invisivel=False):
    """Compatibilidade: aplica somente spintax; não injeta caracteres ocultos."""
    return expandir_spintax(texto)


def delay_digitacao(texto):
    """Delay visual de digitação, limitado, para respostas/conversas."""
    n = len(texto or "")
    base = min(5000, max(800, int(n * 30)))
    return max(600, base + random.randint(-250, 500))
''', encoding="utf-8")

# ---------------------------------------------------------------------------
# 6) Scraper: dedupe por telefone + URL canônica + nome/endereço.
# ---------------------------------------------------------------------------
replace_once(
    "scraper/google_maps.py",
    '        telefones_vistos = set()\n',
    '        telefones_vistos = set()\n'
    '        places_vistos = set()\n'
    '        fingerprints_vistos = set()\n',
)

replace_once(
    "scraper/google_maps.py",
    '            emp["score"] = _calcular_score(emp, categoria)\n'
    '            tel = emp.get("telefone")\n'
    '            if tel and tel in telefones_vistos:\n'
    '                n_dedup += 1\n'
    '                logger.info("[%d/%d] %s — telefone duplicado, ignorada.", i + 1, total_urls, emp["nome"])\n'
    '                continue\n'
    '            if tel:\n'
    '                telefones_vistos.add(tel)\n'
    '            empresas.append(emp)\n',
    '            emp["score"] = _calcular_score(emp, categoria)\n'
    '            tel = emp.get("telefone")\n'
    '            maps_key = (emp.get("maps_url") or "").split("?", 1)[0].rstrip("/").lower()\n'
    '            fp_nome = re.sub(r"\\W+", "", (emp.get("nome") or "").lower(), flags=re.UNICODE)\n'
    '            fp_end = re.sub(r"\\W+", "", (emp.get("endereco") or "").lower(), flags=re.UNICODE)\n'
    '            fingerprint = f"{fp_nome}|{fp_end}" if fp_nome and fp_end else ""\n\n'
    '            duplicada = (\n'
    '                (tel and tel in telefones_vistos)\n'
    '                or (maps_key and maps_key in places_vistos)\n'
    '                or (fingerprint and fingerprint in fingerprints_vistos)\n'
    '            )\n'
    '            if duplicada:\n'
    '                n_dedup += 1\n'
    '                logger.info("[%d/%d] %s — place duplicado, ignorado.", i + 1, total_urls, emp["nome"])\n'
    '                continue\n'
    '            if tel:\n'
    '                telefones_vistos.add(tel)\n'
    '            if maps_key:\n'
    '                places_vistos.add(maps_key)\n'
    '            if fingerprint:\n'
    '                fingerprints_vistos.add(fingerprint)\n'
    '            empresas.append(emp)\n',
)

replace_once(
    "scraper/google_maps.py",
    '        "maps_url":         maps_url,  # URL específica do card (Fase 1) — não usa current_url que pode redirecionar\n',
    '        "maps_url":         (maps_url or "").split("?", 1)[0].rstrip("/"),  # canônica para dedupe\n',
)

# Banco também compara a forma canônica contra registros antigos com querystring.
replace_once(
    "database/db.py",
    '    if maps_url:\n'
    '        c.execute("SELECT id, mensagem_enviada, status FROM empresas WHERE maps_url=%s", (maps_url,))\n'
    '        row = c.fetchone()\n'
    '        if row:\n'
    '            return row\n',
    '    if maps_url:\n'
    '        c.execute(\n'
    '            "SELECT id, mensagem_enviada, status FROM empresas "\n'
    '            "WHERE maps_url=%s OR split_part(maps_url, \'?\', 1)=split_part(%s, \'?\', 1) "\n'
    '            "ORDER BY id LIMIT 1",\n'
    '            (maps_url, maps_url),\n'
    '        )\n'
    '        row = c.fetchone()\n'
    '        if row:\n'
    '            return row\n',
)

# ---------------------------------------------------------------------------
# 7) .env.example deixa de documentar SQLite e passa a refletir o app atual.
# ---------------------------------------------------------------------------
replace_once(
    ".env.example",
    '# ── Banco de dados ───────────────────────────────────────────────────────────\n'
    '# No Railway: monte um volume em /data e use este path\n'
    'DB_PATH=/data/prospector.db\n',
    '# ── Banco de dados / Auth ────────────────────────────────────────────────────\n'
    'DATABASE_URL=postgresql://usuario:senha@host:5432/postgres\n'
    'SUPABASE_URL=https://seu-projeto.supabase.co\n'
    'SUPABASE_ANON_KEY=sua-chave-anon\n',
)

append_env = '''\n# ── IA ─────────────────────────────────────────────────────────────────────────\nAI_PROVIDER=groq\nGROQ_API_KEY=sua-chave-groq\nGROQ_MODEL=openai/gpt-oss-120b\nOPENROUTER_API_KEY=sua-chave-openrouter\nOPENROUTER_MODEL=google/gemini-2.5-flash-lite\nAPP_URL=https://seu-prospector.up.railway.app\n'''
env_path = ROOT / ".env.example"
env_text = env_path.read_text(encoding="utf-8")
if "GROQ_MODEL=" in env_text:
    raise RuntimeError(".env.example: bloco de IA já aplicado")
env_path.write_text(env_text.rstrip() + "\n" + append_env, encoding="utf-8")

print("Fase 1 aplicada com sucesso.")
