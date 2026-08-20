from __future__ import annotations
import platform,shutil,sys
def run_diagnostics(settings,db,ai_service=None,messaging_service=None,live:bool=False)->dict:
    result={"python":sys.version.split()[0],"platform":platform.platform(),"database":{"configured":bool(settings.database_url),"ok":False},"chrome":{"binary":shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"),"driver":shutil.which("chromedriver")},"ai":[],"whatsapp":{"provider":settings.wa_provider,"dry_run":settings.wa_dry_run},"config_errors":settings.validate(production=False)}
    if settings.database_url:
        try:result["database"]["ok"]=bool(db.ping())
        except Exception as exc:result["database"]["error"]=str(exc)
    if ai_service:
        for provider in ("groq","openrouter","xai"):
            configured=bool(settings.ai_key(provider)); result["ai"].append(ai_service.test_provider(provider) if live and configured else {"provider":provider,"configured":configured,"model":settings.ai_model(provider),"live_tested":False})
    if messaging_service and live and messaging_service.provider:result["whatsapp"]["test"]=messaging_service.provider.test()
    return result
