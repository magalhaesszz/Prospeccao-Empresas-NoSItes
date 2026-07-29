"""
Servidor Flask — Prospector de Empresas.
Inclui: SSE em tempo real, CRM, Dashboard, Templates, Blacklist, Login.
"""
import os, socket, json, logging, threading, queue
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
app.secret_key = CONFIG.get("secret_key", "prospector-secret-2024")

# ── Estado global (thread-safe) ───────────────────────────────────────────────
_estado = {
    "scraping":        False,
    "progresso":       0,
    "total":           0,
    "empresa_atual":   "",
    "empresas":        [],
    "erro":            None,
    "busca_id":        None,
    "enviando":        False,
    "envio_progresso": 0,
    "envio_total":     0,
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
    rotas_publicas = {"login_page", "api_login", "static"}
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

    dados     = request.get_json(silent=True) or {}
    cidade    = (dados.get("cidade")    or "").strip()
    categoria = (dados.get("categoria") or "").strip()

    if not cidade or not categoria:
        return jsonify({"erro": "Cidade e categoria são obrigatórios."}), 400

    threading.Thread(target=_executar_busca, args=(cidade, categoria), daemon=True).start()
    return jsonify({"mensagem": f"Busca iniciada: {categoria} em {cidade}"})


def _executar_busca(cidade, categoria):
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

        empresas = buscar_empresas(cidade, categoria, _cb)

        sem_site = 0
        for emp in empresas:
            emp["id"] = salvar_empresa(emp, busca_id)
            if not emp.get("tem_site"):
                sem_site += 1

        atualizar_contagem_busca(busca_id, len(empresas), sem_site)

        with _lock:
            _estado.update({
                "empresas":      empresas,
                "scraping":      False,
                "empresa_atual": f"Concluído! {len(empresas)} empresas ({sem_site} sem site).",
            })

        _broadcast({"tipo": "scraping_fim", "total": len(empresas), "sem_site": sem_site})
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
        # Garante que a instância existe
        req.post(
            f"{base_url}/instance/create",
            headers=headers,
            json={"instanceName": instance, "qrcode": True, "integration": "WHATSAPP-BAILEYS"},
            timeout=15,
        )
    except Exception:
        pass  # ignora erro caso já exista

    try:
        r = req.get(
            f"{base_url}/instance/connect/{instance}",
            headers={"apikey": api_key},
            timeout=15,
        )
        data = r.json()
        # Já conectado
        state = (data.get("instance", {}).get("state") or data.get("state") or "").lower()
        if state in ("open", "connected"):
            return jsonify({"conectado": True})
        # Retorna base64
        b64 = data.get("base64") or data.get("qrcode", {}).get("base64") or data.get("code")
        if b64:
            if not b64.startswith("data:"):
                b64 = "data:image/png;base64," + b64
            return jsonify({"base64": b64})
        return jsonify({"erro": f"QR não disponível. Resposta: {str(data)[:200]}"})
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
        r = req.delete(
            f"{webhook.rstrip('/')}/instance/logout/{instance}",
            headers={"apikey": api_key},
            timeout=10,
        )
        return jsonify({"ok": r.ok})
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

    conn.close()
    return jsonify({"total_enviadas": total, "enviadas_hoje": hoje, "com_erro": erros, "pendentes": pendentes})


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
