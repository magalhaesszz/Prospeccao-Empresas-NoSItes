from __future__ import annotations
import csv,io,logging,os,threading
from datetime import timedelta
from .ai import AIService
from .auth import AuthService
from .db import Database
from .diagnostics import run_diagnostics
from .jobs import JobRegistry
from .inbound import parse_evolution,parse_meta,process_inbound
from .landing import build_preview
from .messaging import MessagingService
from .prospecting import ProspectingService
from .settings import Settings
logger=logging.getLogger(__name__)

def create_app(settings:Settings|None=None,db:Database|None=None,scraper_factory=None):
    from flask import Flask,Response,jsonify,redirect,render_template,request,session,url_for
    settings=settings or Settings();root=os.path.dirname(os.path.dirname(__file__))
    app=Flask(__name__,template_folder=os.path.join(root,"templates"),static_folder=os.path.join(root,"frontend"),static_url_path="/assets");app.secret_key=settings.secret_key or "dev-only-change-me";app.permanent_session_lifetime=timedelta(hours=12);app.config.update(JSON_SORT_KEYS=False,MAX_CONTENT_LENGTH=2*1024*1024)
    db=db or Database(settings.database_url)
    if settings.database_url:db.init_schema()
    auth=AuthService(settings);ai=AIService(settings,db=db);messaging=MessagingService(settings,db);jobs=JobRegistry()
    if scraper_factory is None:
        from scraper.google_maps import GoogleMapsScraper
        scraper_factory=GoogleMapsScraper
    prospecting=ProspectingService(settings,db,scraper_factory);app.extensions["prospector"]={"settings":settings,"db":db,"auth":auth,"ai":ai,"messaging":messaging,"jobs":jobs,"prospecting":prospecting}
    def logged_in()->bool:return (not auth.enabled) or bool(session.get("authenticated"))
    @app.before_request
    def guard():
        public={"healthz","login","preview","static","evolution_webhook","meta_webhook"}
        if request.endpoint in public or logged_in():return None
        if request.path.startswith("/api/"):return jsonify({"error":"not_authenticated"}),401
        return redirect(url_for("login"))
    @app.get("/healthz")
    def healthz():return jsonify({"ok":True,"version":"2.0.0"})
    @app.route("/login",methods=["GET","POST"])
    def login():
        if request.method=="GET":return render_template("login.html",auth_enabled=auth.enabled,supabase_enabled=auth.supabase_enabled)
        data=request.get_json(silent=True) or request.form;ok,identity=auth.authenticate(str(data.get("email") or ""),str(data.get("password") or ""))
        if ok:
            session.permanent=True;session["authenticated"]=True;session["identity"]=identity
            return jsonify({"ok":True,"identity":identity}) if request.is_json else redirect(url_for("home"))
        return (jsonify({"error":identity}),401) if request.is_json else (render_template("login.html",auth_enabled=True,supabase_enabled=auth.supabase_enabled,error=identity),401)
    @app.post("/api/logout")
    def logout():session.clear();return jsonify({"ok":True})
    @app.route("/")
    @app.route("/crm")
    @app.route("/dashboard")
    @app.route("/whatsapp")
    @app.route("/gemini")
    @app.route("/templates")
    @app.route("/blacklist")
    def home():return render_template("index.html",page=request.path.strip("/") or "dashboard")
    @app.get("/api/dashboard")
    def dashboard():return jsonify(db.dashboard())
    @app.post("/api/prospecting/start")
    def start_prospecting():
        data=request.get_json(silent=True) or {};city=str(data.get("city") or data.get("cidade") or "").strip();category=str(data.get("category") or data.get("categoria") or "").strip()
        try:target=int(data.get("target") or data.get("quantidade") or settings.max_results)
        except (TypeError,ValueError):return jsonify({"error":"invalid_target"}),400
        if not city or not category:return jsonify({"error":"city_and_category_required"}),400
        target=max(1,min(target,settings.max_results));job_id=jobs.create("prospecting",{"city":city,"category":category,"target":target})
        def work():
            jobs.update(job_id,status="running")
            try:jobs.finish(job_id,prospecting.run(city,category,target,progress=lambda payload:jobs.progress(job_id,payload)))
            except Exception as exc:logger.exception("Prospecting job failed");jobs.fail(job_id,str(exc))
        threading.Thread(target=work,daemon=True,name=f"prospecting-{job_id[:8]}").start();return jsonify({"ok":True,"job_id":job_id}),202
    @app.get("/api/jobs/<job_id>")
    def job_status(job_id):
        job=jobs.get(job_id);return (jsonify(job),200) if job else (jsonify({"error":"job_not_found"}),404)
    @app.get("/api/prospecting/runs/<int:run_id>")
    def run_summary(run_id):return jsonify(db.run_summary(run_id))
    @app.get("/api/prospecting/runs/<int:run_id>/results")
    def run_results(run_id):return jsonify(db.run_results(run_id,include_known=request.args.get("include_known","0")=="1"))
    @app.get("/api/prospecting/runs")
    def list_runs():return jsonify(db.list_runs(int(request.args.get("limit",30))))
    @app.get("/api/companies")
    def companies():return jsonify(db.list_companies(q=request.args.get("q",""),status=request.args.get("status",""),city=request.args.get("city",""),eligible=request.args.get("eligible",""),limit=int(request.args.get("limit",100)),offset=int(request.args.get("offset",0))))
    @app.get("/api/companies/<int:company_id>")
    def company(company_id):
        item=db.get_company(company_id);return (jsonify(item),200) if item else (jsonify({"error":"not_found"}),404)
    @app.patch("/api/companies/<int:company_id>")
    def patch_company(company_id):
        data=request.get_json(silent=True) or {}
        if "status" in data:
            try:db.update_company_status(company_id,data["status"])
            except ValueError as exc:return jsonify({"error":str(exc)}),400
        item=db.get_company(company_id);return (jsonify(item),200) if item else (jsonify({"error":"not_found"}),404)
    @app.post("/api/companies/<int:company_id>/permission")
    def permission(company_id):
        item=db.get_company(company_id)
        if not item:return jsonify({"error":"not_found"}),404
        data=request.get_json(silent=True) or {}
        try:db.set_permission(item.get("telefone"),data.get("status","unknown"),str(data.get("source") or "manual"),str(data.get("evidence") or ""))
        except ValueError as exc:return jsonify({"error":str(exc)}),400
        return jsonify({"ok":True,"permission":db.get_permission(item.get("telefone"))})
    @app.post("/api/companies/<int:company_id>/ai-message")
    def ai_message(company_id):
        item=db.get_company(company_id)
        if not item:return jsonify({"error":"not_found"}),404
        try:return jsonify({"ok":True,**ai.sales_message(item,str((request.get_json(silent=True) or {}).get("preview_url") or ""))})
        except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),502
    @app.post("/api/companies/<int:company_id>/analyze")
    def analyze(company_id):
        item=db.get_company(company_id)
        if not item:return jsonify({"error":"not_found"}),404
        try:return jsonify({"ok":True,**ai.analyze_company(item)})
        except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),502
    @app.get("/api/companies/<int:company_id>/notes")
    def notes(company_id):return jsonify(db.list_notes(company_id))
    @app.post("/api/companies/<int:company_id>/notes")
    def add_note(company_id):
        data=request.get_json(silent=True) or {}
        try:return jsonify({"ok":True,"id":db.add_note(company_id,str(data.get("text") or ""))})
        except ValueError as exc:return jsonify({"error":str(exc)}),400
    @app.post("/api/messages/send")
    def send_messages():
        data=request.get_json(silent=True) or {};ids=[int(x) for x in (data.get("ids") or [])];messages={int(k):str(v) for k,v in (data.get("messages") or {}).items()};selected=[x for x in (db.get_company(i) for i in ids) if x];return jsonify(messaging.send_many(selected,messages,dry_run=data.get("dry_run")))
    @app.get("/api/ai/providers")
    def ai_providers():return jsonify([{"provider":p,"configured":bool(settings.ai_key(p)),"model":settings.ai_model(p),"primary":p==settings.ai_provider} for p in ("groq","openrouter","xai")])
    @app.post("/api/ai/test")
    def ai_test():
        provider=str((request.get_json(silent=True) or {}).get("provider") or settings.ai_provider).lower()
        if provider not in {"groq","openrouter","xai"}:return jsonify({"error":"invalid_provider"}),400
        return jsonify(ai.test_provider(provider))
    @app.post("/api/landing/<int:company_id>")
    def landing(company_id):
        item=db.get_company(company_id)
        if not item:return jsonify({"error":"not_found"}),404
        copy=""
        if request.args.get("ai","1")=="1" and settings.configured_ai_providers():
            try:copy=ai.generate(f"Escreva uma frase hero de até 30 palavras para um site de {item.get('nome')}, segmento {item.get('descricao_google') or 'negócio local'}. Tom profissional, sem inventar serviços.",purpose="landing_copy",company_id=company_id,max_tokens=90,temperature=.5)["text"]
            except Exception:logger.exception("AI landing copy failed; using fallback")
        slug,markup=build_preview(item,copy);db.save_preview(company_id,item.get("nome") or "Empresa",slug,markup);base=settings.app_url or request.host_url.rstrip("/");return jsonify({"ok":True,"slug":slug,"url":f"{base}/p/{slug}"})
    @app.get("/p/<slug>")
    def preview(slug):
        item=db.get_preview(slug)
        if not item:return "Página não encontrada",404
        return Response(item["html"],content_type="text/html; charset=utf-8")
    @app.get("/api/templates")
    def list_templates():return jsonify(db.list_templates())
    @app.post("/api/templates")
    def create_template():
        data=request.get_json(silent=True) or {}
        try:return jsonify({"ok":True,"id":db.save_template(str(data.get("name") or ""),str(data.get("message") or ""),bool(data.get("active")))})
        except ValueError as exc:return jsonify({"error":str(exc)}),400
    @app.delete("/api/templates/<int:template_id>")
    def remove_template(template_id):return jsonify({"ok":db.delete_template(template_id)})
    @app.get("/api/blacklist")
    def blacklist():return jsonify(db.list_blacklist())
    @app.post("/api/blacklist")
    def blacklist_add():
        data=request.get_json(silent=True) or {}
        try:db.add_blacklist(str(data.get("phone") or ""),str(data.get("reason") or "manual"));return jsonify({"ok":True})
        except ValueError as exc:return jsonify({"error":str(exc)}),400
    @app.get("/api/inbox")
    def inbox():return jsonify(db.recent_wa_events(int(request.args.get("limit",100))))
    @app.post("/api/webhooks/evolution")
    def evolution_webhook():
        if settings.evolution_webhook_secret and (request.headers.get("X-Webhook-Secret") or request.args.get("secret",""))!=settings.evolution_webhook_secret:return jsonify({"error":"unauthorized"}),401
        message=parse_evolution(request.get_json(silent=True) or {})
        if not message:return jsonify({"ok":True,"ignored":True})
        return jsonify({"ok":True,**process_inbound(db,message,"evolution")})
    @app.route("/api/webhooks/meta",methods=["GET","POST"])
    def meta_webhook():
        if request.method=="GET":
            if request.args.get("hub.mode")=="subscribe" and settings.meta_verify_token and request.args.get("hub.verify_token")==settings.meta_verify_token:return request.args.get("hub.challenge",""),200
            return "forbidden",403
        return jsonify({"ok":True,"processed":[process_inbound(db,m,"meta") for m in parse_meta(request.get_json(silent=True) or {})]})
    @app.post("/api/admin/deduplicate")
    def deduplicate():return jsonify({"ok":True,"removed":db.deduplicate()})
    @app.get("/api/diagnostics")
    def diagnostics():return jsonify(run_diagnostics(settings,db,ai,messaging,live=request.args.get("live","0")=="1"))
    @app.get("/api/export.csv")
    def export_csv():
        rows=list(db.export_companies());output=io.StringIO();fields=["id","nome","telefone","endereco","descricao_google","tem_site","site_url","score","status","wa_eligible","data_prospeccao"];writer=csv.DictWriter(output,fieldnames=fields,extrasaction="ignore");writer.writeheader();writer.writerows(rows);return Response(output.getvalue(),content_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=prospector-leads.csv"})
    return app
