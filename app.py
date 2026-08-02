"""
Servidor Flask — Prospector de Empresas.
Inclui: SSE em tempo real, CRM, Dashboard, Templates, Blacklist, Login.
"""
import os, socket, json, logging, threading, queue, uuid
from flask import (
    Flask, jsonify, request, send_file, render_template,
    session, redirect, url_for, Response, stream_with_context
)

from config import CONFIG
from database.db import (
    inicializar_banco, criar_busca, salvar_empresa, atualizar_contagem_busca,
    marcar_mensagem_enviada, buscar_empresa_por_id, buscar_todas_empresas,
    listar_historico, atualizar_status_empresa,
    listar_templates, criar_template, atualizar_template, deletar_template,
    ativar_template, get_template_ativo, incrementar_enviados_template,
    listar_blacklist, adicionar_blacklist, remover_blacklist,
    listar_notas, adicionar_nota, deletar_nota,
    buscar_empresa_por_telefone, marcar_respondeu,
    criar_agendamento, listar_agendamentos, ativar_agendamento,
    deletar_agendamento, atualizar_ultima_execucao, contagem_enviadas_hoje,
    get_funil_conversao,
    criar_pagina_preview, buscar_pagina_por_slug, registrar_vista_pagina,
    listar_paginas_preview, deletar_pagina_preview,
    limpar_empresas_invalidas,
    criar_job, atualizar_job_ok, atualizar_job_erro, buscar_job, limpar_jobs_antigos,
)
from crm.pipeline import kanban_por_status
from dashboard.metrics import obter_stats
from scraper.google_maps import buscar_empresas
from whatsapp.disparar import disparar_lote
from export.excel import exportar_excel
from export.csv_export import exportar_csv

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="templates",   # Jinja2 templates (HTML das páginas)
    static_folder="frontend",      # CSS, JS estáticos
    static_url_path="",            # servidos na raiz: /style.css, /app.js…
)
_secret = CONFIG.get("secret_key", "")
if not _secret or _secret == "prospector-secret-2024":
    if not _secret:
        raise RuntimeError("SECRET_KEY não definida. Configure a variável de ambiente.")
    logger.warning("SECRET_KEY usa valor padrão inseguro. Defina SECRET_KEY no ambiente de produção.")
app.secret_key = _secret

if not CONFIG.get("app_url", "").strip():
    logger.warning("APP_URL não definida. URLs de preview podem ficar incorretas em produção. Defina APP_URL=https://seu-dominio.com")

# ── Estado global (thread-safe) ───────────────────────────────────────────────
_estado = {
    "scraping":          False,
    "progresso":         0,
    "total":             0,
    "empresa_atual":     "",
    "empresas":          [],
    "erro":              None,
    "busca_id":          None,
    "enviando":          False,
    "envio_progresso":   0,
    "envio_total":       0,
    "enriquecendo":      False,
    "enriq_progresso":   0,
    "enriq_total":       0,
}
_lock = threading.Lock()

# ── SSE — fila de eventos por cliente conectado ───────────────────────────────
_sse_queues: list[queue.Queue] = []
_sse_lock   = threading.Lock()


def _broadcast(evento: dict):
    """Envia evento JSON para todos os clientes SSE conectados."""
    dados = json.dumps(evento, ensure_ascii=False)
    with _sse_lock:
        mortos = []
        for q in _sse_queues:
            try:
                q.put_nowait(dados)
            except queue.Full:
                mortos.append(q)
        for q in mortos:
            _sse_queues.remove(q)


# ── Autenticação ──────────────────────────────────────────────────────────────
@app.before_request
def verificar_auth():
    senha = CONFIG.get("senha_painel", "").strip()
    if not senha:
        return  # sem senha = sem proteção
    rotas_publicas = {"login_page", "api_login", "static", "preview_pagina", "api_wa_webhook", "api_test_gemini", "api_status"}
    if request.endpoint in rotas_publicas:
        return
    if not session.get("autenticado"):
        return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}
    if dados.get("senha") == CONFIG.get("senha_painel"):
        session["autenticado"] = True
        return jsonify({"ok": True})
    return jsonify({"erro": "Senha incorreta"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ── Páginas HTML ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", page="busca")


@app.route("/crm")
def crm():
    return render_template("crm.html", page="crm")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", page="dashboard")


@app.route("/templates")
def templates_page():
    return render_template("templates_page.html", page="templates")


@app.route("/blacklist")
def blacklist_page():
    return render_template("blacklist.html", page="blacklist")


@app.route("/whatsapp")
def whatsapp_page():
    return render_template("whatsapp.html", page="whatsapp")


@app.route("/gemini")
def gemini_page():
    return render_template("gemini.html", page="gemini")


# ── SSE ───────────────────────────────────────────────────────────────────────
@app.route("/api/events")
def api_events():
    """Stream SSE — o frontend conecta uma vez e recebe atualizações em push."""
    def gerar():
        q = queue.Queue(maxsize=100)
        with _sse_lock:
            _sse_queues.append(q)
        try:
            # Estado inicial imediato
            with _lock:
                inicial = {k: v for k, v in _estado.items()}
            yield f"data: {json.dumps({'tipo': 'estado_inicial', **inicial}, ensure_ascii=False)}\n\n"

            while True:
                try:
                    dados = q.get(timeout=25)
                    yield f"data: {dados}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"  # heartbeat keepalive
        finally:
            with _sse_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return Response(
        stream_with_context(gerar()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Status (polling fallback) ─────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    with _lock:
        dados = {k: v for k, v in _estado.items()}
    dados["senha_configurada"] = bool(CONFIG.get("senha_painel", "").strip())
    return jsonify(dados)


# ── Busca ─────────────────────────────────────────────────────────────────────
@app.route("/api/buscar", methods=["POST"])
def api_buscar():
    with _lock:
        if _estado["scraping"]:
            return jsonify({"erro": "Busca já em andamento."}), 400

    dados      = request.get_json(silent=True) or {}
    cidade     = (dados.get("cidade")    or "").strip()
    categoria  = (dados.get("categoria") or "").strip()
    quantidade = int(dados.get("quantidade") or CONFIG.get("max_resultados", 50))
    quantidade = max(5, min(quantidade, 200))  # limita entre 5 e 200

    if not cidade or not categoria:
        return jsonify({"erro": "Cidade e categoria são obrigatórios."}), 400

    threading.Thread(target=_executar_busca, args=(cidade, categoria, quantidade), daemon=True).start()
    return jsonify({"mensagem": f"Busca iniciada: {categoria} em {cidade} ({quantidade} empresas)"})


def _executar_busca(cidade, categoria, quantidade=None):
    if quantidade is None:
        quantidade = CONFIG.get("max_resultados", 50)
    with _lock:
        _estado.update({
            "scraping": True, "progresso": 0, "total": 0,
            "empresa_atual": "Iniciando Chrome...", "empresas": [], "erro": None,
        })

    _broadcast({"tipo": "scraping_inicio", "cidade": cidade, "categoria": categoria})

    try:
        busca_id = criar_busca(cidade, categoria)
        with _lock:
            _estado["busca_id"] = busca_id

        def _cb(info):
            with _lock:
                _estado["progresso"]     = info["atual"]
                _estado["total"]         = info["total"]
                _estado["empresa_atual"] = info["empresa"]
            _broadcast({"tipo": "progresso", **info})

        empresas = buscar_empresas(cidade, categoria, _cb, limite=quantidade)

        # ── Validação real: confirma via HTTP quem tem/não tem site ──────────
        from scraper.verificar_site import validar_flags_site
        from scraper.google_maps import _calcular_score

        with _lock:
            _estado["empresa_atual"] = "Validando sites (verificação real)..."
        _broadcast({"tipo": "validando_inicio", "total": len(empresas)})

        def _cb_val(info):
            with _lock:
                _estado["empresa_atual"] = f"Validando site {info['atual']}/{info['total']}..."
            _broadcast({"tipo": "validando_progresso", **info})

        res_val = validar_flags_site(empresas, _cb_val)

        # Recalcula score após correção do flag de site
        for emp in empresas:
            emp["score"] = _calcular_score(emp, categoria)

        sem_site = 0
        for emp in empresas:
            emp["id"] = salvar_empresa(emp, busca_id)
            if not emp.get("tem_site"):
                sem_site += 1

        atualizar_contagem_busca(busca_id, len(empresas), sem_site)

        # IDs prontos pra disparo: sem site + com telefone + não enviados ainda
        prontos = [
            emp["id"] for emp in empresas
            if not emp.get("tem_site") and emp.get("telefone") and not emp.get("mensagem_enviada")
        ]

        with _lock:
            _estado.update({
                "empresas":      empresas,
                "scraping":      False,
                "empresa_atual": f"Concluído! {len(empresas)} empresas ({sem_site} sem site, "
                                 f"{res_val['reclassificadas']} reclassificadas).",
            })

        _broadcast({
            "tipo": "scraping_fim",
            "total": len(empresas),
            "sem_site": sem_site,
            "reclassificadas": res_val["reclassificadas"],
            "prontos_disparo": prontos,
            "empresas": empresas,
            "busca_id": busca_id,
        })
        logger.info("Busca OK: %d empresas, %d sem site.", len(empresas), sem_site)

    except Exception as exc:
        logger.error("Erro na busca: %s", exc)
        with _lock:
            _estado.update({"erro": str(exc), "scraping": False})
        _broadcast({"tipo": "erro", "mensagem": str(exc)})


# ── WhatsApp ──────────────────────────────────────────────────────────────────
@app.route("/api/enviar", methods=["POST"])
def api_enviar():
    with _lock:
        if _estado["enviando"]:
            return jsonify({"erro": "Envio já em andamento."}), 400

    dados = request.get_json(silent=True) or {}
    ids   = dados.get("ids", [])
    if not ids:
        return jsonify({"erro": "Nenhuma empresa selecionada."}), 400

    empresas = []
    for eid in ids:
        emp = buscar_empresa_por_id(eid)
        if emp and emp.get("telefone") and not emp.get("mensagem_enviada"):
            empresas.append(emp)

    if not empresas:
        return jsonify({"erro": "Nenhuma empresa válida (sem telefone ou já enviada)."}), 400

    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()
    return jsonify({"mensagem": f"Envio iniciado para {len(empresas)} empresa(s)."})


def _executar_envio(empresas):
    with _lock:
        _estado.update({"enviando": True, "envio_progresso": 0, "envio_total": len(empresas)})
    _broadcast({"tipo": "envio_inicio", "total": len(empresas)})

    try:
        def _cb(info):
            with _lock:
                _estado["envio_progresso"] = info["atual"]
            _broadcast({"tipo": "envio_progresso", **info})

            if info.get("sucesso") and info.get("id"):
                tid = info.get("template_id")
                marcar_mensagem_enviada(info["id"], tid)
                if tid:
                    incrementar_enviados_template(tid)

        disparar_lote(empresas, _cb)

    except Exception as exc:
        logger.error("Erro no envio: %s", exc)

    finally:
        busca_id = None
        with _lock:
            busca_id = _estado.get("busca_id")

        if busca_id:
            atualizadas = buscar_todas_empresas(busca_id=busca_id)
            with _lock:
                _estado["empresas"] = atualizadas

        with _lock:
            _estado["enviando"] = False

        _broadcast({"tipo": "envio_fim"})


# ── Export ────────────────────────────────────────────────────────────────────
@app.route("/api/exportar")
def api_exportar():
    try:
        busca_id_raw   = request.args.get("busca_id")
        apenas_sem_msg = request.args.get("apenas_sem_mensagem") == "true"
        fmt            = request.args.get("formato", "xlsx")
        busca_id       = int(busca_id_raw) if busca_id_raw else None

        empresas = buscar_todas_empresas(busca_id=busca_id, apenas_sem_mensagem=apenas_sem_msg)
        if not empresas:
            return jsonify({"erro": "Nenhuma empresa para exportar."}), 404

        # Adiciona preview_url em cada empresa que tiver slug gerado
        base = _app_base_url()
        for emp in empresas:
            slug = emp.get("gemini_pagina_slug")
            emp["preview_url"] = f"{base}/p/{slug}" if slug else ""

        if fmt == "csv":
            caminho = exportar_csv(empresas)
            mimetype = "text/csv"
        else:
            caminho = exportar_excel(empresas)
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return send_file(caminho, as_attachment=True,
                         download_name=os.path.basename(caminho), mimetype=mimetype)
    except Exception as exc:
        logger.error("Erro ao exportar: %s", exc)
        return jsonify({"erro": str(exc)}), 500


# ── Histórico / Empresas ──────────────────────────────────────────────────────
@app.route("/api/historico")
def api_historico():
    return jsonify(listar_historico())


@app.route("/api/empresas")
def api_empresas():
    busca_id_raw   = request.args.get("busca_id")
    apenas_sem_msg = request.args.get("apenas_sem_mensagem") == "true"
    status         = request.args.get("status")
    busca_id       = int(busca_id_raw) if busca_id_raw else None
    return jsonify(buscar_todas_empresas(busca_id=busca_id, apenas_sem_mensagem=apenas_sem_msg, status=status))


# ── CRM ───────────────────────────────────────────────────────────────────────
@app.route("/api/crm/kanban")
def api_crm_kanban():
    return jsonify(kanban_por_status())


@app.route("/api/crm/empresa/<int:empresa_id>", methods=["PATCH"])
def api_crm_atualizar(empresa_id):
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get("status")
    if novo_status:
        atualizar_status_empresa(empresa_id, novo_status)
    return jsonify({"ok": True})


@app.route("/api/crm/notas/<int:empresa_id>", methods=["GET"])
def api_crm_notas_get(empresa_id):
    return jsonify(listar_notas(empresa_id))


@app.route("/api/crm/notas/<int:empresa_id>", methods=["POST"])
def api_crm_notas_post(empresa_id):
    dados = request.get_json(silent=True) or {}
    texto = (dados.get("texto") or "").strip()
    if not texto:
        return jsonify({"erro": "Texto vazio."}), 400
    nid = adicionar_nota(empresa_id, texto)
    return jsonify({"id": nid, "ok": True})


@app.route("/api/crm/notas/item/<int:nota_id>", methods=["DELETE"])
def api_crm_nota_deletar(nota_id):
    deletar_nota(nota_id)
    return jsonify({"ok": True})


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/api/dashboard/stats")
def api_dashboard_stats():
    return jsonify(obter_stats())


# ── Templates ─────────────────────────────────────────────────────────────────
@app.route("/api/templates", methods=["GET"])
def api_templates_get():
    return jsonify(listar_templates())


@app.route("/api/templates", methods=["POST"])
def api_templates_post():
    dados = request.get_json(silent=True) or {}
    nome  = (dados.get("nome") or "").strip()
    msg   = (dados.get("mensagem") or "").strip()
    if not nome or not msg:
        return jsonify({"erro": "Nome e mensagem obrigatórios."}), 400
    tid = criar_template(nome, msg)
    return jsonify({"id": tid, "ok": True})


@app.route("/api/templates/<int:tid>", methods=["PUT"])
def api_templates_put(tid):
    dados = request.get_json(silent=True) or {}
    nome  = (dados.get("nome") or "").strip()
    msg   = (dados.get("mensagem") or "").strip()
    if not nome or not msg:
        return jsonify({"erro": "Nome e mensagem obrigatórios."}), 400
    atualizar_template(tid, nome, msg)
    return jsonify({"ok": True})


@app.route("/api/templates/<int:tid>", methods=["DELETE"])
def api_templates_delete(tid):
    deletar_template(tid)
    return jsonify({"ok": True})


@app.route("/api/templates/<int:tid>/ativar", methods=["POST"])
def api_templates_ativar(tid):
    ativar_template(tid)
    return jsonify({"ok": True})


# ── WhatsApp Management ───────────────────────────────────────────────────────
@app.route("/api/whatsapp/status")
def api_wa_status():
    """Checa estado da conexão com a Evolution API."""
    import requests as req
    webhook = CONFIG.get("webhook_whatsapp", "").strip()
    instance = CONFIG.get("evolution_instance", "").strip()
    api_key  = CONFIG.get("evolution_api_key",  "").strip()

    cfg = {
        "webhook_url":   webhook or None,
        "instance":      instance or None,
        "api_key_mask":  (api_key[:4] + "****" + api_key[-2:]) if len(api_key) > 6 else ("****" if api_key else None),
    }

    if not (webhook and instance and api_key):
        return jsonify({"configurado": False, "conectado": False, "config": cfg})

    try:
        r = req.get(
            f"{webhook.rstrip('/')}/instance/connectionState/{instance}",
            headers={"apikey": api_key},
            timeout=8,
        )
        data   = r.json()
        state  = (data.get("instance", {}).get("state") or
                  data.get("state") or "").lower()
        numero = data.get("instance", {}).get("profilePictureUrl") and data.get("instance", {}).get("profileName")
        conectado = state in ("open", "connected")
        return jsonify({
            "configurado": True,
            "conectado":   conectado,
            "state":       state,
            "numero":      data.get("instance", {}).get("profileName") or "",
            "config":      cfg,
        })
    except Exception as e:
        return jsonify({"configurado": True, "conectado": False, "erro": str(e), "config": cfg})


@app.route("/api/whatsapp/qrcode")
def api_wa_qrcode():
    """Obtém QR Code para conectar WhatsApp."""
    import requests as req
    webhook  = CONFIG.get("webhook_whatsapp", "").strip()
    instance = CONFIG.get("evolution_instance", "").strip()
    api_key  = CONFIG.get("evolution_api_key",  "").strip()

    if not (webhook and instance and api_key):
        return jsonify({"erro": "Evolution API não configurada."})

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    base_url = webhook.rstrip("/")

    try:
        cr = req.post(
            f"{base_url}/instance/create",
            headers=headers,
            json={"instanceName": instance, "qrcode": True, "integration": "WHATSAPP-BAILEYS"},
            timeout=15,
        )
        cr_data = cr.json()
        # 409 = já existe, tudo bem. Outro erro = retorna pro usuário
        if not cr.ok and cr.status_code not in (409, 403):
            return jsonify({"erro": f"Erro ao criar instância: {str(cr_data)[:300]}"})
    except Exception as e:
        return jsonify({"erro": f"Não conseguiu conectar na Evolution API: {str(e)}"})

    try:
        r = req.get(
            f"{base_url}/instance/connect/{instance}",
            headers={"apikey": api_key},
            timeout=15,
        )
        data = r.json()
        state = (data.get("instance", {}).get("state") or data.get("state") or "").lower()
        if state in ("open", "connected"):
            return jsonify({"conectado": True})
        b64 = data.get("base64") or data.get("qrcode", {}).get("base64") or data.get("code")
        if b64:
            if not b64.startswith("data:"):
                b64 = "data:image/png;base64," + b64
            return jsonify({"base64": b64})
        return jsonify({"erro": f"QR não disponível. Resposta: {str(data)[:300]}"})
    except Exception as e:
        return jsonify({"erro": str(e)})


@app.route("/api/whatsapp/desconectar", methods=["POST"])
def api_wa_desconectar():
    """Desconecta a instância do WhatsApp."""
    import requests as req
    webhook  = CONFIG.get("webhook_whatsapp", "").strip()
    instance = CONFIG.get("evolution_instance", "").strip()
    api_key  = CONFIG.get("evolution_api_key",  "").strip()

    if not (webhook and instance and api_key):
        return jsonify({"ok": False, "erro": "Não configurado."})

    try:
        # Logout primeiro (ignora erros — instância pode já estar desconectada)
        req.delete(
            f"{webhook.rstrip('/')}/instance/logout/{instance}",
            headers={"apikey": api_key},
            timeout=10,
        )
        # Deleta a instância para limpar histórico (evita dados de sessão anterior)
        r = req.delete(
            f"{webhook.rstrip('/')}/instance/delete/{instance}",
            headers={"apikey": api_key},
            timeout=10,
        )
        if r.ok:
            return jsonify({"ok": True})
        corpo = ""
        try:
            corpo = str(r.json())
        except Exception:
            corpo = r.text[:200]
        # "not found" significa instância já não existe — sucesso
        if "not" in corpo.lower() and ("found" in corpo.lower() or "exist" in corpo.lower()):
            return jsonify({"ok": True})
        return jsonify({"ok": False, "erro": f"HTTP {r.status_code}: {corpo[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/api/whatsapp/teste", methods=["POST"])
def api_wa_teste():
    """Envia mensagem de teste."""
    from whatsapp.disparar import _enviar_via_webhook
    dados    = request.get_json(silent=True) or {}
    numero   = (dados.get("numero") or "").strip()
    mensagem = (dados.get("mensagem") or "Olá! Teste do Prospector. 🚀").strip()

    if not numero:
        return jsonify({"ok": False, "erro": "Número obrigatório."})

    try:
        _enviar_via_webhook(numero, mensagem)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


@app.route("/api/whatsapp/stats")
def api_wa_stats():
    """Stats de disparos WhatsApp."""
    from database.db import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM empresas WHERE mensagem_enviada=1")
        total = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM empresas
            WHERE mensagem_enviada=1
              AND ultimo_contato::date = CURRENT_DATE
        """)
        hoje = c.fetchone()[0] or 0

        c.execute("SELECT COUNT(*) FROM empresas WHERE erro_envio IS NOT NULL AND erro_envio != ''")
        erros = c.fetchone()[0] or 0

        c.execute("""
            SELECT COUNT(*) FROM empresas
            WHERE mensagem_enviada=0
              AND tem_site=0
              AND telefone IS NOT NULL
              AND telefone != ''
        """)
        pendentes = c.fetchone()[0] or 0
    finally:
        conn.close()
    return jsonify({"total_enviadas": total, "enviadas_hoje": hoje, "com_erro": erros, "pendentes": pendentes})


# ── Conversas WhatsApp (Evolution API) ─────────────────────────────────────────

def _wa_config():
    return (
        CONFIG.get("webhook_whatsapp", "").strip().rstrip("/"),
        CONFIG.get("evolution_instance", "").strip(),
        CONFIG.get("evolution_api_key",  "").strip(),
    )


def _so_digitos(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _mapa_nomes_empresas():
    """Mapa sufixo-de-8-dígitos -> nome da empresa prospectada (do nosso banco)."""
    from database.db import get_connection
    mapa = {}
    try:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT telefone, nome FROM empresas WHERE telefone IS NOT NULL AND telefone != ''")
            for tel, nome in c.fetchall():
                dig = _so_digitos(tel)
                if len(dig) >= 8:
                    mapa[dig[-8:]] = nome
        finally:
            conn.close()
    except Exception:
        pass
    return mapa


def _parse_msg(conteudo):
    """
    Analisa o conteúdo de uma mensagem Evolution/Baileys.
    Retorna dict: {tipo, texto, url, mimetype}
    tipos: texto | imagem | audio | video | figurinha | documento | localizacao | contato
    """
    if not isinstance(conteudo, dict):
        return {"tipo": "texto", "texto": "", "url": "", "mimetype": ""}

    if conteudo.get("conversation"):
        return {"tipo": "texto", "texto": conteudo["conversation"], "url": "", "mimetype": ""}
    if conteudo.get("extendedTextMessage", {}).get("text"):
        return {"tipo": "texto", "texto": conteudo["extendedTextMessage"]["text"], "url": "", "mimetype": ""}

    mapa = {
        "imageMessage":    "imagem",
        "videoMessage":    "video",
        "audioMessage":    "audio",
        "pttMessage":      "audio",   # push-to-talk (áudio gravado)
        "stickerMessage":  "figurinha",
        "documentMessage": "documento",
        "locationMessage": "localizacao",
        "contactMessage":  "contato",
    }
    for chave, tipo in mapa.items():
        sub = conteudo.get(chave)
        if sub and isinstance(sub, dict):
            url      = sub.get("url") or sub.get("mediaUrl") or sub.get("jpegThumbnail") or ""
            texto    = sub.get("caption") or sub.get("fileName") or sub.get("name") or ""
            mimetype = sub.get("mimetype") or ""
            # Para localização
            if tipo == "localizacao":
                lat = sub.get("degreesLatitude", "")
                lon = sub.get("degreesLongitude", "")
                texto = f"📍 {sub.get('name','Localização')} ({lat},{lon})"
            # Para contato
            if tipo == "contato":
                texto = sub.get("displayName") or "Contato"
            return {"tipo": tipo, "texto": texto, "url": url, "mimetype": mimetype}

    return {"tipo": "texto", "texto": "[mensagem não suportada]", "url": "", "mimetype": ""}


@app.route("/api/whatsapp/conversas")
def api_wa_conversas():
    """Lista as conversas com nomes resolvidos (contato > empresa do banco > número)."""
    import requests as req
    base, instance, api_key = _wa_config()
    if not (base and instance and api_key):
        return jsonify({"erro": "Evolution API não configurada.", "conversas": []})

    headers = {"apikey": api_key, "Content-Type": "application/json"}

    # Mapa de contatos do WhatsApp (jid/numero -> pushName)
    nomes_contato = {}
    try:
        rc = req.post(f"{base}/chat/findContacts/{instance}", headers=headers, json={}, timeout=20)
        if rc.ok:
            cont = rc.json()
            cont = cont if isinstance(cont, list) else cont.get("contacts", cont.get("data", []))
            for ct in cont:
                cjid = ct.get("remoteJid") or ct.get("id") or ct.get("jid") or ""
                nome = ct.get("pushName") or ct.get("name") or ct.get("verifiedName") or ""
                if cjid and nome:
                    nomes_contato[_so_digitos(cjid)[-8:]] = nome
    except Exception:
        pass

    nomes_empresa = _mapa_nomes_empresas()

    try:
        r = req.post(f"{base}/chat/findChats/{instance}", headers=headers, json={}, timeout=25)
        if not r.ok:
            return jsonify({"erro": f"HTTP {r.status_code}: {r.text[:200]}", "conversas": []})
        dados = r.json()
        chats = dados if isinstance(dados, list) else dados.get("chats", dados.get("data", []))

        conversas = []
        for ch in chats:
            jid = ch.get("remoteJid") or ch.get("id") or ch.get("jid") or ""
            if not jid or jid.endswith("@g.us") or "status@broadcast" in jid or "@lid" in jid:
                continue  # pula grupos, status e listas
            numero = jid.split("@")[0]
            suf = _so_digitos(numero)[-8:]

            # Resolução de nome por prioridade
            nome = (ch.get("pushName") or ch.get("name")
                    or nomes_contato.get(suf)
                    or nomes_empresa.get(suf)
                    or ("+" + numero if numero.isdigit() else numero))

            ultima = ""
            lm = ch.get("lastMessage")
            if isinstance(lm, dict):
                p = _parse_msg(lm.get("message", {}))
                ultima = p["texto"] or p["tipo"]

            conversas.append({
                "jid":        jid,
                "numero":     numero,
                "nome":       nome,
                "cliente":    suf in nomes_empresa,   # é empresa que prospectamos
                "foto":       ch.get("profilePicUrl") or ch.get("profilePictureUrl") or "",
                "ultima_msg": ultima,
                "timestamp":  ch.get("updatedAt") or ch.get("lastMsgTimestamp") or 0,
                "nao_lidas":  ch.get("unreadCount") or ch.get("unreadMessages") or 0,
            })

        # Ordena por atividade mais recente
        def _ts(c):
            t = c["timestamp"]
            try: return float(t)
            except Exception: return 0
        conversas.sort(key=_ts, reverse=True)

        return jsonify({"conversas": conversas, "total": len(conversas)})
    except Exception as e:
        return jsonify({"erro": str(e), "conversas": []})


@app.route("/api/whatsapp/mensagens")
def api_wa_mensagens():
    """Mensagens de uma conversa. Retorna histórico completo ordenado."""
    import requests as req
    base, instance, api_key = _wa_config()
    jid = (request.args.get("jid") or "").strip()
    if not (base and instance and api_key):
        return jsonify({"erro": "Não configurado.", "mensagens": []})
    if not jid:
        return jsonify({"erro": "jid obrigatório.", "mensagens": []})

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    limite  = min(int(request.args.get("limit", 500)), 1000)
    corpo   = {"where": {"key": {"remoteJid": jid}}, "limit": limite}
    try:
        r = req.post(f"{base}/chat/findMessages/{instance}", headers=headers, json=corpo, timeout=30)
        if not r.ok:
            return jsonify({"erro": f"HTTP {r.status_code}: {r.text[:200]}", "mensagens": []})
        dados = r.json()
        if isinstance(dados, dict):
            msgs = dados.get("messages", dados.get("data", []))
            if isinstance(msgs, dict):
                msgs = msgs.get("records", msgs.get("data", []))
        else:
            msgs = dados

        TIPOS_MIDIA = {"imagem", "audio", "video", "figurinha", "documento"}
        mensagens = []
        for m in msgs:
            key  = m.get("key", {})
            p    = _parse_msg(m.get("message", {}) or {})
            item = {
                "de_mim":    bool(key.get("fromMe")),
                "tipo":      p["tipo"],
                "texto":     p["texto"],
                "url":       p["url"],
                "mimetype":  p["mimetype"],
                "timestamp": m.get("messageTimestamp") or 0,
                "status":    m.get("status") or "",
            }
            # Para mídia: inclui o objeto completo pra que o front possa buscar base64 via proxy
            if p["tipo"] in TIPOS_MIDIA:
                item["raw_msg"] = m.get("message", {})
            mensagens.append(item)

        mensagens.sort(key=lambda x: x["timestamp"] or 0)
        return jsonify({"mensagens": mensagens, "total": len(mensagens)})
    except Exception as e:
        return jsonify({"erro": str(e), "mensagens": []})


@app.route("/api/whatsapp/media", methods=["POST"])
def api_wa_media():
    """
    Proxy: busca base64 de uma mensagem de mídia da Evolution API.
    Body: {"message": <raw_message_object>}
    Retorna: {"base64": "data:audio/ogg;base64,...", "mimetype": "..."}
    """
    import requests as req
    base, instance, api_key = _wa_config()
    dados = request.get_json(silent=True) or {}
    raw_msg = dados.get("message")
    if not raw_msg:
        return jsonify({"erro": "message obrigatório."}), 400
    if not (base and instance and api_key):
        return jsonify({"erro": "Não configurado."}), 400

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    try:
        r = req.post(
            f"{base}/chat/getBase64FromMediaMessage/{instance}",
            headers=headers,
            json={"message": raw_msg, "convertToMp4": False},
            timeout=30,
        )
        if not r.ok:
            return jsonify({"erro": f"HTTP {r.status_code}"}), 400
        d = r.json()
        b64  = d.get("base64") or d.get("data") or ""
        mime = d.get("mimetype") or ""
        if b64 and not b64.startswith("data:"):
            b64 = f"data:{mime};base64,{b64}"
        return jsonify({"base64": b64, "mimetype": mime})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route("/api/whatsapp/pendentes")
def api_wa_pendentes():
    """Conta empresas prontas pra disparo: sem site, com telefone, não enviadas."""
    from database.db import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM empresas
            WHERE mensagem_enviada=0 AND tem_site=0
              AND telefone IS NOT NULL AND telefone != ''
        """)
        n = c.fetchone()[0] or 0
    finally:
        conn.close()
    return jsonify({"pendentes": n})


@app.route("/api/whatsapp/disparar-pendentes", methods=["POST"])
def api_wa_disparar_pendentes():
    """Dispara para TODAS as empresas pendentes (sem site, com tel, não enviadas)."""
    with _lock:
        if _estado["enviando"]:
            return jsonify({"erro": "Envio já em andamento."}), 400

    dados = request.get_json(silent=True) or {}
    limite = dados.get("limite")  # opcional: máximo de disparos nesta rodada

    from database.db import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        query = """
            SELECT * FROM empresas
            WHERE mensagem_enviada=0 AND tem_site=0
              AND telefone IS NOT NULL AND telefone != ''
            ORDER BY score DESC, data_prospeccao DESC
        """
        if isinstance(limite, int) and limite > 0:
            query += f" LIMIT {int(limite)}"
        c.execute(query)
        cols = [d[0] for d in c.description]
        empresas = [dict(zip(cols, r)) for r in c.fetchall()]
    finally:
        conn.close()

    if not empresas:
        return jsonify({"erro": "Nenhuma empresa pendente."}), 400

    threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()
    return jsonify({"mensagem": f"Disparo iniciado para {len(empresas)} empresa(s) pendente(s)."})


@app.route("/api/whatsapp/responder", methods=["POST"])
def api_wa_responder():
    """Envia resposta manual dentro de uma conversa."""
    from whatsapp.disparar import _enviar_via_webhook
    dados  = request.get_json(silent=True) or {}
    numero = (dados.get("numero") or "").strip()
    texto  = (dados.get("texto") or "").strip()
    if not numero or not texto:
        return jsonify({"ok": False, "erro": "Número e texto obrigatórios."})
    try:
        _enviar_via_webhook(numero, texto)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


# ── Enriquecimento Gemini — pipeline completo ─────────────────────────────────

def _app_base_url_bg():
    """App URL para threads de background (sem contexto de request)."""
    return (CONFIG.get("app_url") or CONFIG.get("_detected_app_url") or "").strip().rstrip("/")


def _executar_enriquecimento(empresas, api_key, criar_pagina, app_url=""):
    from ai.enricher import enriquecer
    from database.db import get_connection

    with _lock:
        _estado.update({"enriquecendo": True, "enriq_progresso": 0, "enriq_total": len(empresas)})

    _broadcast({"tipo": "enriquecimento_inicio", "total": len(empresas)})
    if not app_url:
        app_url = _app_base_url_bg()  # fallback para env APP_URL

    falhas = 0
    for i, emp in enumerate(empresas):
        nome = emp.get("nome", "")
        try:
            resultado = enriquecer(emp, api_key, app_url, criar_pagina)

            conn = get_connection()
            try:
                c = conn.cursor()
                if resultado.get("slug") and resultado.get("html"):
                    criar_pagina_preview(emp["id"], nome, resultado["slug"], resultado["html"])
                    c.execute("UPDATE empresas SET gemini_pagina_slug=%s WHERE id=%s",
                              (resultado["slug"], emp["id"]))
                if resultado.get("mensagem"):
                    c.execute("UPDATE empresas SET gemini_mensagem=%s WHERE id=%s",
                              (resultado["mensagem"], emp["id"]))
                conn.commit()
            finally:
                conn.close()

        except Exception as e:
            falhas += 1
            logger.error("[enriq] '%s': %s", nome, e)

        with _lock:
            _estado["enriq_progresso"] = i + 1

        _broadcast({
            "tipo":    "enriquecimento_progresso",
            "atual":   i + 1,
            "total":   len(empresas),
            "empresa": nome,
        })

    with _lock:
        _estado["enriquecendo"] = False

    _broadcast({"tipo": "enriquecimento_fim", "total": len(empresas), "falhas": falhas})
    logger.info("[enriq] Concluído: %d empresas processadas, %d falhas.", len(empresas), falhas)


@app.route("/api/gemini/enriquecer", methods=["POST"])
def api_gemini_enriquecer():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada no Railway (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    with _lock:
        if _estado.get("enriquecendo"):
            return jsonify({"erro": "Enriquecimento já em andamento."}), 400

    dados        = request.get_json(silent=True) or {}
    busca_id     = dados.get("busca_id")
    criar_pagina = dados.get("criar_pagina", True)
    limite       = min(int(dados.get("limite", 30)), 50)

    from database.db import get_connection
    conn = get_connection()
    c    = conn.cursor()
    # Quando criar_pagina=True: inclui empresas sem página mesmo que já tenham mensagem.
    # Evita que empresas com mensagem mas sem site gerado sejam ignoradas.
    cond_ia = "(e.gemini_mensagem IS NULL OR e.gemini_pagina_slug IS NULL)" if criar_pagina else "e.gemini_mensagem IS NULL"
    query = f"""
        SELECT e.*, b.cidade, b.categoria
        FROM empresas e
        LEFT JOIN buscas b ON e.busca_id = b.id
        WHERE e.tem_site=0
          AND e.telefone IS NOT NULL AND e.telefone != ''
          AND {cond_ia}
    """
    params = []
    if busca_id:
        query += " AND e.busca_id=%s"
        params.append(busca_id)
    query += f" ORDER BY e.score DESC LIMIT {limite}"
    c.execute(query, params)
    cols     = [d[0] for d in c.description]
    empresas = [dict(zip(cols, r)) for r in c.fetchall()]
    conn.close()

    if not empresas:
        return jsonify({"erro": "Nenhuma empresa pendente de enriquecimento."}), 400

    # Captura URL aqui (contexto de request) antes de spawnar thread background.
    # _executar_enriquecimento roda sem contexto Flask e não pode usar request.host_url.
    app_url_capturado = _app_base_url()

    threading.Thread(
        target=_executar_enriquecimento,
        args=(empresas, api_key, criar_pagina, app_url_capturado),
        daemon=True,
    ).start()

    return jsonify({"mensagem": f"Enriquecimento iniciado para {len(empresas)} empresa(s).", "total": len(empresas)})


@app.route("/api/gemini/enriquecer-empresa", methods=["POST"])
def api_gemini_enriquecer_empresa():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada no Railway (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados      = request.get_json(silent=True) or {}
    empresa_id = dados.get("empresa_id")
    if not empresa_id:
        return jsonify({"erro": "empresa_id obrigatório."}), 400

    emp = buscar_empresa_por_id(empresa_id)
    if not emp:
        return jsonify({"erro": "Empresa não encontrada."}), 404

    from ai.enricher import enriquecer
    from database.db import get_connection

    app_url  = _app_base_url()  # em request context — usa fallback correto
    resultado = enriquecer(emp, api_key, app_url, criar_pagina=True)

    conn = get_connection()
    try:
        c = conn.cursor()
        if resultado.get("slug") and resultado.get("html"):
            criar_pagina_preview(emp["id"], emp.get("nome", ""), resultado["slug"], resultado["html"])
            c.execute("UPDATE empresas SET gemini_pagina_slug=%s WHERE id=%s",
                      (resultado["slug"], emp["id"]))
        if resultado.get("mensagem"):
            c.execute("UPDATE empresas SET gemini_mensagem=%s WHERE id=%s",
                      (resultado["mensagem"], emp["id"]))
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "ok":          True,
        "slug":        resultado.get("slug"),
        "preview_url": resultado.get("preview_url"),
        "mensagem":    resultado.get("mensagem"),
    })


@app.route("/api/gemini/responder-conversa", methods=["POST"])
def api_gemini_responder_conversa():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados = request.get_json(silent=True) or {}
    ultima_msg = (dados.get("ultima_msg") or "").strip()
    if not ultima_msg:
        return jsonify({"erro": "ultima_msg obrigatório."}), 400

    nome      = dados.get("nome", "prospect")
    historico = (dados.get("historico_resumo") or "").strip()
    hist_part = f"\nHistórico recente:\n{historico}" if historico else ""

    prompt = f"""Você é um assistente de vendas B2B especialista em fechar negócios pelo WhatsApp.
Você vende: criação de site profissional + automação de processos para pequenas empresas.
Política: cobra APENAS após a entrega finalizada.

Cliente: {nome}{hist_part}

Última mensagem recebida:
"{ultima_msg}"

Gere uma resposta profissional, empática e focada em avançar a venda.
- Português brasileiro, tom natural e amigável
- Máximo 120 palavras
- Se perguntou sobre preço: reforce "só paga após a entrega", proponha ver uma prévia
- Se demonstrou interesse: proponha próximo passo concreto
- Se expressou dúvida: esclareça com tranquilidade
- Use *negrito* com moderação
- Máximo 1 emoji

Retorne APENAS a mensagem de resposta."""

    try:
        return jsonify({"mensagem": _ai_gerar(prompt), "ok": True})
    except Exception as e:
        logger.error("[Gemini conversa] %s", e)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/gemini/crm-followup", methods=["POST"])
def api_gemini_crm_followup():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados      = request.get_json(silent=True) or {}
    empresa_id = dados.get("empresa_id")
    if not empresa_id:
        return jsonify({"erro": "empresa_id obrigatório."}), 400

    emp = buscar_empresa_por_id(empresa_id)
    if not emp:
        return jsonify({"erro": "Empresa não encontrada."}), 404

    notas = listar_notas(empresa_id)
    notas_txt = "\n".join(f"- {n['texto']}" for n in notas) if notas else "Nenhuma nota registrada"

    status_desc = {
        "novo":        "empresa foi prospectada, ainda sem resposta",
        "contatado":   "empresa foi contatada, aguardando retorno",
        "interessado": "empresa demonstrou interesse no serviço",
        "fechado":     "negócio fechado com sucesso",
        "perdido":     "negócio não avançou",
    }.get(emp.get("status", "novo"), "status desconhecido")

    prompt = f"""Você é especialista em follow-up de vendas B2B via WhatsApp.
Serviço: criação de site + automação (cobra após entrega).

EMPRESA: {emp.get('nome', '')}
SEGMENTO: {emp.get('descricao_google') or emp.get('categoria', '') or 'não informado'}
CIDADE: {emp.get('cidade', '') or 'não informada'}
STATUS CRM: {status_desc}
NOTAS REGISTRADAS:
{notas_txt}

Crie uma mensagem de follow-up personalizada e contextualizada.
- Português brasileiro, tom amigável
- Máximo 150 palavras
- Referencie o histórico de forma natural
- CTA claro e simples
- *Negrito* com moderação
- Máximo 2 emojis

Retorne APENAS a mensagem."""

    try:
        return jsonify({"mensagem": _ai_gerar(prompt), "ok": True})
    except Exception as e:
        logger.error("[Gemini followup] %s", e)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/gemini/gerar-template", methods=["POST"])
def api_gemini_gerar_template():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados     = request.get_json(silent=True) or {}
    descricao = (dados.get("descricao") or "").strip()
    if not descricao:
        return jsonify({"erro": "descricao obrigatório."}), 400

    prompt = f"""Você é especialista em copywriting para prospecção B2B via WhatsApp.
Crie um template de mensagem de prospecção profissional.

DESCRIÇÃO DO TEMPLATE: {descricao}

REGRAS OBRIGATÓRIAS:
- Use {{NOME_DA_EMPRESA}} onde mencionar o nome da empresa (será substituído automaticamente)
- Português brasileiro, tom amigável e direto
- Máximo 200 palavras
- Mencione: identificou que não têm presença digital, oferece site + automação, cobra após entrega
- *Negrito* para pontos-chave
- Máximo 3 emojis estratégicos
- CTA claro no final

Retorne APENAS a mensagem do template."""

    try:
        return jsonify({"template": _ai_gerar(prompt), "ok": True})
    except Exception as e:
        logger.error("[Gemini template] %s", e)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/gemini/gerar-mensagem-empresa", methods=["POST"])
def api_gemini_gerar_mensagem_empresa():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados = request.get_json(silent=True) or {}
    empresa_id = dados.get("empresa_id")
    if not empresa_id:
        return jsonify({"erro": "empresa_id obrigatório."}), 400

    emp = buscar_empresa_por_id(empresa_id)
    if not emp:
        return jsonify({"erro": "Empresa não encontrada."}), 404

    from ai.enricher import gerar_mensagem
    try:
        mensagem = gerar_mensagem(emp, api_key)
    except Exception as e:
        logger.error("[Gemini msg empresa] %s", e)
        return jsonify({"erro": str(e)}), 500

    from database.db import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE empresas SET gemini_mensagem=%s WHERE id=%s", (mensagem, empresa_id))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"mensagem": mensagem, "ok": True})


@app.route("/api/gemini/status-enriquecimento")
def api_gemini_status_enriq():
    with _lock:
        return jsonify({
            "enriquecendo":    _estado.get("enriquecendo", False),
            "enriq_progresso": _estado.get("enriq_progresso", 0),
            "enriq_total":     _estado.get("enriq_total", 0),
        })


# ── Preview de Landing Page (público — sem auth) ──────────────────────────────
@app.route("/p/<slug>")
def preview_pagina(slug):
    pagina = buscar_pagina_por_slug(slug)
    if not pagina:
        return "<h1 style='font-family:sans-serif;text-align:center;margin-top:20%'>Página não encontrada.</h1>", 404
    registrar_vista_pagina(slug)
    return pagina["html"], 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/gemini/analisar-prospects", methods=["POST"])
def api_gemini_analisar_prospects():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados    = request.get_json(silent=True) or {}
    empresas = dados.get("empresas", [])
    if not empresas:
        return jsonify({"analise": "", "ok": True})

    linhas = []
    for i, emp in enumerate(empresas[:25]):
        tel  = "✓ tel" if emp.get("telefone") else "✗ sem tel"
        site = "tem site" if emp.get("tem_site") else "SEM SITE"
        nota = f"{emp.get('nota','?')}★ ({emp.get('avaliacoes','?')} avaliações)"
        sc   = emp.get("score", 0)
        linhas.append(f"{i+1}. {emp.get('nome','')} [{site}] [{tel}] [score:{sc}] [{nota}]")

    prompt = f"""Você é consultor especializado em prospecção B2B de sites e automação para negócios locais.

Analise {len(empresas)} negócios locais e identifique os melhores prospects para vender criação de site/presença digital:

{chr(10).join(linhas)}

Critérios: SEM SITE = máxima prioridade | com telefone = contato direto | score alto = calculado pelo sistema | alta avaliação = negócio ativo.

Responda EXATAMENTE neste formato (português brasileiro, direto):

🎯 TOP 5 PROSPECTS:
1. [Nome] — [motivo em 1 frase curta]
2. [Nome] — [motivo em 1 frase curta]
3. [Nome] — [motivo em 1 frase curta]
4. [Nome] — [motivo em 1 frase curta]
5. [Nome] — [motivo em 1 frase curta]

💡 DICA: [1 frase com estratégia de abordagem para este nicho]"""

    try:
        analise = _ai_gerar(prompt)
        return jsonify({"analise": analise, "ok": True})
    except Exception as e:
        logger.error("[Gemini prospects] %s", e)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/admin/limpar-lixo", methods=["POST"])
def api_admin_limpar_lixo():
    deleted = limpar_empresas_invalidas()
    return jsonify({"ok": True, "deletados": deleted})


# ── AI Hub (Groq / OpenRouter) ────────────────────────────────────────────────

def _ai_api_key():
    provider = CONFIG.get("ai_provider", "groq").lower()
    if provider == "openrouter":
        return CONFIG.get("openrouter_api_key", "").strip()
    return CONFIG.get("groq_api_key", "").strip()


def _ai_gerar(prompt):
    provider = CONFIG.get("ai_provider", "groq").lower()
    api_key  = _ai_api_key()
    if not api_key:
        raise ValueError(f"API key não configurada para provider '{provider}'.")

    if provider == "openrouter":
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        resp = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()
    else:
        from groq import Groq
        client = Groq(api_key=api_key, timeout=90.0, max_retries=0)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()


# Job store para geração assíncrona de páginas (in-memory, TTL simples por tamanho)
_jobs_pagina: dict = {}
_JOBS_MAX = 200  # descarta jobs mais antigos quando ultrapassar


def _app_base_url():
    app_url = CONFIG.get("app_url", "").strip().rstrip("/")
    if app_url:
        return app_url
    detected = request.host_url.rstrip("/")
    # Armazena para threads de background usarem via _app_base_url_bg()
    if detected and "localhost" not in detected:
        CONFIG["_detected_app_url"] = detected
    return detected


@app.route("/api/gemini/test")
def api_test_gemini():
    """Testa conexão IA com prompt mínimo. Retorna ok/erro, provider e latência em ms."""
    import time
    provider = CONFIG.get("ai_provider", "groq").lower()
    api_key  = _ai_api_key()
    if not api_key:
        return jsonify({"ok": False, "erro": f"API key não configurada para '{provider}'.", "provider": provider})
    t0 = time.time()
    try:
        resposta = _ai_gerar("Diga apenas: OK")
        ms = int((time.time() - t0) * 1000)
        return jsonify({"ok": True, "resposta": resposta, "ms": ms, "provider": provider})
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return jsonify({"ok": False, "erro": str(e), "ms": ms, "provider": provider})


@app.route("/api/gemini/status")
def api_gemini_status():
    provider    = CONFIG.get("ai_provider", "groq").lower()
    configurado = bool(_ai_api_key())
    return jsonify({"configurado": configurado, "provider": provider})


@app.route("/api/gemini/gerar-pagina", methods=["POST"])
def api_gemini_gerar_pagina():
    """Inicia geração de página em background. Retorna job_id para polling."""
    from ai.enricher import gerar_pagina as _enr_gerar_pagina

    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada no Railway (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados      = request.get_json(silent=True) or {}
    nome       = (dados.get("nome")       or "").strip()
    categoria  = (dados.get("categoria")  or "Negócio Local").strip()
    cidade     = (dados.get("cidade")     or "Brasil").strip()
    empresa_id = dados.get("empresa_id")

    if not nome:
        return jsonify({"erro": "Nome da empresa é obrigatório."}), 400

    job_id = uuid.uuid4().hex[:10]
    _jobs_pagina[job_id] = {"status": "gerando"}
    criar_job(job_id)

    # Descarta jobs antigos para não vazar memória
    if len(_jobs_pagina) > _JOBS_MAX:
        chave_mais_velha = next(iter(_jobs_pagina))
        _jobs_pagina.pop(chave_mais_velha, None)

    base_url = _app_base_url()

    def _bg():
        try:
            empresa = {
                "nome":             nome,
                "categoria":        categoria,
                "descricao_google": categoria,
                "cidade":           cidade,
                "endereco":         "",
                "telefone":         "",
                "nota":             None,
                "avaliacoes":       None,
                "foto_url":         "",
                "fotos_urls":       "[]",
                "maps_url":         "",
            }
            slug, html = _enr_gerar_pagina(empresa, api_key)
            pid  = criar_pagina_preview(empresa_id, nome, slug, html)
            url  = f"{base_url}/p/{slug}"
            logger.info("[Gemini] Página gerada para '%s' → %s", nome, url)
            resultado = {"status": "ok", "id": pid, "slug": slug, "url": url}
            _jobs_pagina[job_id] = resultado
            atualizar_job_ok(job_id, slug, url)
        except Exception as e:
            logger.error("[Geminigerar-pagina] %s", e)
            resultado = {"status": "erro", "erro": str(e)}
            _jobs_pagina[job_id] = resultado
            atualizar_job_erro(job_id, str(e))

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/gemini/gerar-pagina/status/<job_id>")
def api_gemini_pagina_status(job_id):
    """Polling de status do job de geração de página."""
    job = _jobs_pagina.get(job_id)
    if not job:
        # Servidor pode ter reiniciado — busca no DB
        db_job = buscar_job(job_id)
        if not db_job:
            return jsonify({"erro": "Job não encontrado."}), 404
        job = {"status": db_job["status"], "slug": db_job.get("slug"), "url": db_job.get("url"), "erro": db_job.get("erro")}
        if job["status"] == "ok":
            _jobs_pagina[job_id] = job  # restaura em memória
    return jsonify(job)


@app.route("/api/gemini/gerar-mensagem", methods=["POST"])
def api_gemini_gerar_mensagem():
    dados      = request.get_json(silent=True) or {}
    nome       = (dados.get("nome")       or "").strip()
    categoria  = (dados.get("categoria")  or "").strip()
    cidade     = (dados.get("cidade")     or "").strip()
    link       = (dados.get("link")       or "").strip()

    if not nome:
        return jsonify({"erro": "Nome da empresa é obrigatório."}), 400

    parte_link = (
        f"\n- Link da prévia do site criado especialmente para eles: {link}"
        if link else ""
    )

    prompt = f"""Você é especialista em vendas B2B via WhatsApp. Crie uma mensagem de prospecção profissional.

DADOS:
- Empresa: {nome}
- Segmento: {categoria or 'não informado'}
- Cidade: {cidade or 'não informada'}{parte_link}

REGRAS:
- Português brasileiro, tom amigável e profissional, direto ao ponto
- Máximo 180 palavras
- Mencione que identificou que a empresa não tem site/presença digital
- Ofereça: criação de site profissional + automação de processos
- Destaque: cobra apenas após entrega finalizada
{"- Mencione o link da prévia do site que criou especificamente para eles (isso é diferencial poderoso)" if link else ""}
- Formatação WhatsApp: *negrito* para pontos importantes
- Máximo 2-3 emojis estratégicos
- CTA claro pedindo resposta

Retorne APENAS a mensagem, sem prefácio ou explicações."""

    try:
        mensagem = _ai_gerar(prompt)
        return jsonify({"mensagem": mensagem})
    except Exception as e:
        logger.error("[Geminimsg] %s", e)
        return jsonify({"erro": str(e)}), 500


@app.route("/api/gemini/paginas", methods=["GET"])
def api_gemini_paginas_get():
    paginas = listar_paginas_preview()
    base    = _app_base_url()
    for p in paginas:
        p["url"]      = f"{base}/p/{p['slug']}"
        p["criado_em"] = str(p.get("criado_em") or "")
    return jsonify(paginas)


@app.route("/api/gemini/paginas/<int:pid>", methods=["DELETE"])
def api_gemini_paginas_delete(pid):
    deletar_pagina_preview(pid)
    return jsonify({"ok": True})


# ── Webhook Evolution API (rastreamento de respostas) ─────────────────────────
@app.route("/api/whatsapp/webhook", methods=["GET", "POST"])
def api_wa_webhook():
    if request.method == "GET":
        return jsonify({"ok": True, "webhook": "prospector"})

    dados  = request.get_json(silent=True) or {}
    evento = dados.get("event", "")

    if evento in ("messages.upsert", "message.upsert"):
        data = dados.get("data", {})
        if isinstance(data, list):
            data = data[0] if data else {}
        key     = data.get("key", {})
        if key.get("fromMe"):
            return jsonify({"ok": True})

        jid     = key.get("remoteJid", "")
        numero  = jid.split("@")[0] if "@" in jid else jid
        empresa = buscar_empresa_por_telefone(numero)

        if empresa and empresa.get("mensagem_enviada"):
            marcar_respondeu(empresa["id"])
            _broadcast({
                "tipo":       "prospect_respondeu",
                "empresa_id": empresa["id"],
                "nome":       empresa.get("nome", ""),
                "numero":     numero,
            })
            logger.info("[webhook] Resposta recebida de %s (%s)", empresa.get("nome"), numero)

    return jsonify({"ok": True})


# ── IA — Gerar mensagem personalizada ─────────────────────────────────────────
@app.route("/api/whatsapp/gerar-mensagem", methods=["POST"])
def api_wa_gerar_mensagem():
    api_key = _ai_api_key()
    if not api_key:
        return jsonify({"erro": "API key de IA não configurada no Railway (GROQ_API_KEY ou OPENROUTER_API_KEY)."}), 400

    dados     = request.get_json(silent=True) or {}
    nome      = (dados.get("nome")      or "").strip()
    categoria = (dados.get("categoria") or "").strip()
    cidade    = (dados.get("cidade")    or "").strip()

    if not nome:
        return jsonify({"erro": "Nome da empresa é obrigatório."}), 400

    contexto = f"Empresa: {nome}"
    if categoria: contexto += f" | Segmento: {categoria}"
    if cidade:    contexto += f" | Cidade: {cidade}"

    prompt = (
        f"Crie uma mensagem de WhatsApp profissional e personalizada para prospectar "
        f"a seguinte empresa: {contexto}.\n"
        "Regras:\n"
        "- Português brasileiro, tom amigável e direto\n"
        "- Mencione que a empresa não tem presença digital (site)\n"
        "- Ofereça criação de site profissional e automação de processos\n"
        "- Mencione que só cobra após entrega finalizada\n"
        "- Incentive o prospecto a responder\n"
        "- Use formatação WhatsApp (*negrito*)\n"
        "- Máximo 200 palavras\n"
        "Escreva APENAS a mensagem, sem comentários."
    )

    try:
        mensagem = _ai_gerar(prompt)
        return jsonify({"mensagem": mensagem})
    except Exception as e:
        logger.error("[IA] %s", e)
        return jsonify({"erro": str(e)}), 500


# ── Agendamentos de disparo ────────────────────────────────────────────────────
@app.route("/api/agendamentos", methods=["GET"])
def api_agendamentos_get():
    return jsonify(listar_agendamentos())


@app.route("/api/agendamentos", methods=["POST"])
def api_agendamentos_post():
    dados   = request.get_json(silent=True) or {}
    nome    = (dados.get("nome") or "Agendamento").strip()
    h_ini   = max(0, min(23, int(dados.get("hora_inicio", 9))))
    h_fim   = max(0, min(23, int(dados.get("hora_fim",   18))))
    limite  = max(1, int(dados.get("limite_dia", 20)))
    dias    = (dados.get("dias_semana") or "1,2,3,4,5").strip()
    custom  = (dados.get("mensagem_custom") or "").strip() or None
    ag_id   = criar_agendamento(nome, h_ini, h_fim, limite, dias, custom)
    return jsonify({"id": ag_id, "ok": True})


@app.route("/api/agendamentos/<int:ag_id>", methods=["PUT"])
def api_agendamentos_put(ag_id):
    dados = request.get_json(silent=True) or {}
    ativar_agendamento(ag_id, dados.get("ativo", True))
    return jsonify({"ok": True})


@app.route("/api/agendamentos/<int:ag_id>", methods=["DELETE"])
def api_agendamentos_delete(ag_id):
    deletar_agendamento(ag_id)
    return jsonify({"ok": True})


# ── Funil de conversão ────────────────────────────────────────────────────────
@app.route("/api/dashboard/funil")
def api_dashboard_funil():
    return jsonify(get_funil_conversao())


# ── Blacklist ──────────────────────────────────────────────────────────────────
@app.route("/api/blacklist", methods=["GET"])
def api_blacklist_get():
    return jsonify(listar_blacklist())


@app.route("/api/blacklist", methods=["POST"])
def api_blacklist_post():
    dados    = request.get_json(silent=True) or {}
    telefone = (dados.get("telefone") or "").strip()
    motivo   = (dados.get("motivo")   or "").strip()
    if not telefone:
        return jsonify({"erro": "Telefone obrigatório."}), 400
    ok = adicionar_blacklist(telefone, motivo)
    return jsonify({"ok": ok, "duplicado": not ok})


@app.route("/api/blacklist/<int:bid>", methods=["DELETE"])
def api_blacklist_delete(bid):
    remover_blacklist(bid)
    return jsonify({"ok": True})


# ── Threads de background ─────────────────────────────────────────────────────

def _keepalive():
    import time as _t, requests as _req
    _t.sleep(30)  # aguarda app estabilizar
    while True:
        try:
            base, instance, api_key = _wa_config()
            if base and instance and api_key:
                _req.get(
                    f"{base}/instance/connectionState/{instance}",
                    headers={"apikey": api_key},
                    timeout=10,
                )
                logger.info("[keepalive] ping Evolution API OK")
        except Exception as e:
            logger.warning("[keepalive] %s", e)
        _t.sleep(300)  # a cada 5 min


def _verificar_agendamentos():
    from datetime import datetime as _dt
    from database.db import get_connection

    agora      = _dt.now()
    dia_semana = agora.weekday() + 1  # 1=Seg ... 7=Dom

    enviados_hoje = contagem_enviadas_hoje()

    for ag in listar_agendamentos():
        if not ag.get("ativo"):
            continue
        if not (ag["hora_inicio"] <= agora.hour < ag["hora_fim"]):
            continue
        dias = [int(d.strip()) for d in str(ag.get("dias_semana", "1,2,3,4,5")).split(",")
                if d.strip().isdigit()]
        if dia_semana not in dias:
            continue

        with _lock:
            if _estado["enviando"]:
                continue

        restantes = ag["limite_dia"] - enviados_hoje
        if restantes <= 0:
            continue

        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM empresas
                WHERE mensagem_enviada=0 AND tem_site=0
                  AND telefone IS NOT NULL AND telefone != ''
                ORDER BY score DESC, data_prospeccao DESC
                LIMIT %s
            """, (restantes,))
            cols    = [d[0] for d in c.description]
            empresas = [dict(zip(cols, r)) for r in c.fetchall()]
        finally:
            conn.close()

        if not empresas:
            continue

        atualizar_ultima_execucao(ag["id"], enviados_hoje + len(empresas))
        logger.info("[agendador] Agendamento '%s': %d empresas para disparar", ag["nome"], len(empresas))
        threading.Thread(target=_executar_envio, args=(empresas,), daemon=True).start()
        break  # uma rodada por minuto


def _agendador():
    import time as _t
    _t.sleep(60)
    while True:
        try:
            _verificar_agendamentos()
        except Exception as e:
            logger.error("[agendador] %s", e)
        _t.sleep(60)


def _limpeza_periodica():
    import time as _t
    _t.sleep(3600)  # primeira limpeza após 1h
    while True:
        try:
            limpar_jobs_antigos()
        except Exception as e:
            logger.warning("[limpeza] %s", e)
        _t.sleep(3600)


threading.Thread(target=_keepalive,        daemon=True).start()
threading.Thread(target=_agendador,        daemon=True).start()
threading.Thread(target=_limpeza_periodica, daemon=True).start()


# ── Inicialização ─────────────────────────────────────────────────────────────
def _ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.x.x"


if __name__ == "__main__":
    inicializar_banco()
    ip, porta = _ip_local(), CONFIG["porta"]
    print(f"""
╔═══════════════════════════════════════════════╗
║     PROSPECTOR DE EMPRESAS — GOOGLE MAPS      ║
╠═══════════════════════════════════════════════╣
║  PC      → http://localhost:{porta}            ║
║  Celular → http://{ip}:{porta}           ║
╠═══════════════════════════════════════════════╣
║  /          Busca + Resultados                ║
║  /crm       CRM Kanban                        ║
║  /dashboard Métricas e Gráficos               ║
║  /templates Templates de Mensagem             ║
║  /blacklist Números Bloqueados                ║
╚═══════════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=porta, debug=False, threaded=True)
