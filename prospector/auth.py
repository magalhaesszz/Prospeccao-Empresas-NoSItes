from __future__ import annotations
import hmac,requests
from .settings import Settings
class AuthService:
    def __init__(self,settings:Settings,session=None):self.settings=settings;self.http=session or requests.Session()
    @property
    def supabase_enabled(self)->bool:return bool(self.settings.supabase_url and self.settings.supabase_anon_key)
    @property
    def enabled(self)->bool:return self.supabase_enabled or bool(self.settings.admin_password)
    def verify_password(self,password:str)->bool:
        if not self.settings.admin_password:return not self.supabase_enabled
        return hmac.compare_digest(password or "",self.settings.admin_password)
    def verify_supabase(self,email:str,password:str)->tuple[bool,str]:
        if not self.supabase_enabled:return False,"Supabase Auth não configurado"
        if not email or not password:return False,"Informe e-mail e senha"
        try:r=self.http.post(f"{self.settings.supabase_url}/auth/v1/token?grant_type=password",headers={"apikey":self.settings.supabase_anon_key,"Authorization":f"Bearer {self.settings.supabase_anon_key}","Content-Type":"application/json"},json={"email":email.strip().lower(),"password":password},timeout=15)
        except Exception as exc:return False,f"Falha ao conectar no Supabase: {exc}"
        if r.status_code==200:
            try:user=(r.json().get("user") or {}).get("email") or email
            except Exception:user=email
            return True,user
        try:
            body=r.json(); detail=body.get("error_description") or body.get("msg") or body.get("message") or body.get("error")
        except Exception:detail=None
        return False,detail or "E-mail ou senha incorretos"
    def authenticate(self,email:str,password:str)->tuple[bool,str]:
        if self.supabase_enabled:return self.verify_supabase(email,password)
        if self.verify_password(password):return True,email or "admin"
        return False,"Senha inválida"
