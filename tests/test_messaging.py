from prospector.messaging import MessagingService,WhatsAppProvider
from prospector.settings import Settings
class FakeDB:
    def __init__(self,permission=None,daily=0,last=None):self.permission=permission;self.daily=daily;self.last=last;self.events=[]
    def get_permission(self,p):return self.permission
    def outbound_count_today(self):return self.daily
    def last_outbound_for_phone(self,p):return self.last
    def log_wa_event(self,**kw):self.events.append(kw);return len(self.events)
class FakeProvider(WhatsAppProvider):
    name="fake"
    def send_text(self,phone,text,template=False):return {"ok":True,"external_id":"abc"}
    def test(self):return {"ok":True}
def make_settings(monkeypatch):
    monkeypatch.setenv("WA_PROVIDER","evolution");monkeypatch.setenv("WA_DRY_RUN","false");monkeypatch.setenv("WA_HORA_INICIO","0");monkeypatch.setenv("WA_HORA_FIM","24");monkeypatch.setenv("WA_DAILY_LIMIT","10");monkeypatch.setenv("WA_CONTACT_COOLDOWN_HOURS","72");return Settings()
def test_scraped_lead_without_optin_is_blocked(monkeypatch):
    out=MessagingService(make_settings(monkeypatch),FakeDB(permission=None),provider=FakeProvider()).send({"id":1,"telefone":"62999991234"},"oi",dry_run=False);assert out["blocked"] is True;assert "opt-in" in out["reason"]
def test_opted_in_contact_can_dry_run(monkeypatch):
    out=MessagingService(make_settings(monkeypatch),FakeDB(permission={"status":"opted_in"}),provider=FakeProvider()).send({"id":1,"telefone":"62999991234"},"oi",dry_run=True);assert out=={"ok":True,"dry_run":True}
def test_daily_limit_blocks(monkeypatch):
    out=MessagingService(make_settings(monkeypatch),FakeDB(permission={"status":"opted_in"},daily=10),provider=FakeProvider()).send({"id":1,"telefone":"62999991234"},"oi",dry_run=False);assert out["blocked"] is True;assert "limite diário" in out["reason"]
