from prospector.settings import Settings
from prospector.web import create_app
class FakeDB:
    def dashboard(self):return {"total":0}
def test_healthz_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL",raising=False);monkeypatch.delenv("ADMIN_PASSWORD",raising=False);monkeypatch.delenv("SUPABASE_URL",raising=False);monkeypatch.delenv("SUPABASE_ANON_KEY",raising=False);app=create_app(Settings(),db=FakeDB(),scraper_factory=lambda:None);r=app.test_client().get('/healthz');assert r.status_code==200;assert r.json['version']=='2.0.0'
