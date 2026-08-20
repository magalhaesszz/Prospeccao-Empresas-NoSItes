from prospector.ai import AIService
from prospector.settings import Settings
class Response:
    def __init__(self,ok=True,status=200,body=None,text=""):self.ok=ok;self.status_code=status;self._body=body or {};self.text=text
    def json(self):return self._body
class Session:
    def __init__(self):self.calls=[]
    def post(self,url,headers=None,json=None,timeout=None):
        self.calls.append(url)
        if "api.groq.com" in url:return Response(False,500,text="boom")
        return Response(True,200,{"choices":[{"message":{"content":"OK fallback"}}]})
def settings_for_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER","groq");monkeypatch.setenv("AI_FALLBACK_ORDER","openrouter,xai");monkeypatch.setenv("GROQ_API_KEY","g");monkeypatch.setenv("OPENROUTER_API_KEY","o");monkeypatch.setenv("XAI_API_KEY","");return Settings()
def test_ai_fails_over(monkeypatch):
    s=settings_for_ai(monkeypatch);http=Session();out=AIService(s,session=http).generate("hello");assert out["provider"]=="openrouter";assert out["text"]=="OK fallback";assert len(http.calls)==2
def test_groq_default_model_is_current_replacement(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL",raising=False);assert Settings().groq_model=="openai/gpt-oss-120b"
