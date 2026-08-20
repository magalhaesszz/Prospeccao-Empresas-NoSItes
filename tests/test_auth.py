from prospector.auth import AuthService
from prospector.settings import Settings
class Resp:
    status_code=200
    def json(self):return {"user":{"email":"admin@example.com"}}
class HTTP:
    def post(self,*a,**kw):return Resp()
def test_admin_password_fallback(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL",raising=False);monkeypatch.delenv("SUPABASE_ANON_KEY",raising=False);monkeypatch.setenv("ADMIN_PASSWORD","abc123");a=AuthService(Settings());assert a.authenticate("","abc123")[0] is True;assert a.authenticate("","no")[0] is False
def test_supabase_has_priority(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.supabase.co");monkeypatch.setenv("SUPABASE_ANON_KEY","anon");monkeypatch.setenv("ADMIN_PASSWORD","abc123");ok,user=AuthService(Settings(),session=HTTP()).authenticate("admin@example.com","pw");assert ok and user=="admin@example.com"
