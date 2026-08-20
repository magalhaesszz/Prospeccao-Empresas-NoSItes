from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests

from .identity import normalize_phone
from .settings import Settings


@dataclass(frozen=True)
class Eligibility:
    allowed: bool
    reason: str


class OutboundPolicy:
    """Compliance-first outbound policy. Cold scraped leads are not auto-eligible."""
    def __init__(self, settings: Settings, now_fn=None):
        self.settings = settings
        self.now_fn = now_fn or datetime.now

    def evaluate(self, *, phone: str | None, permission: dict | None, daily_count: int, last_outbound: datetime | None, manual_reply: bool = False) -> Eligibility:
        normalized = normalize_phone(phone)
        if not normalized:
            return Eligibility(False, "telefone inválido")
        if self.settings.wa_provider == "disabled":
            return Eligibility(False, "WhatsApp desativado")
        now = self.now_fn()
        if not manual_reply:
            if not permission or permission.get("status") != "opted_in":
                return Eligibility(False, "sem consentimento/opt-in registrado")
            if self.settings.wa_daily_limit and daily_count >= self.settings.wa_daily_limit:
                return Eligibility(False, "limite diário atingido")
            if not (self.settings.wa_business_start_hour <= now.hour < self.settings.wa_business_end_hour):
                return Eligibility(False, "fora do horário configurado")
            if last_outbound:
                try:
                    if last_outbound.tzinfo is not None and now.tzinfo is None:
                        last_outbound = last_outbound.replace(tzinfo=None)
                except Exception:
                    pass
                if now - last_outbound < timedelta(hours=self.settings.wa_contact_cooldown_hours):
                    return Eligibility(False, "contato em cooldown")
        return Eligibility(True, "ok")


class WhatsAppProvider:
    name = "base"
    def send_text(self, phone: str, text: str, *, template: bool = False) -> dict: raise NotImplementedError
    def test(self) -> dict: raise NotImplementedError


class EvolutionProvider(WhatsAppProvider):
    name = "evolution"
    def __init__(self, settings: Settings, session=None): self.settings=settings; self.session=session or requests.Session()
    def _configured(self) -> bool: return bool(self.settings.evolution_url and self.settings.evolution_instance and self.settings.evolution_api_key)
    def send_text(self, phone: str, text: str, *, template: bool = False) -> dict:
        if not self._configured(): raise RuntimeError("Evolution API não configurada")
        digits=(normalize_phone(phone) or "").lstrip("+")
        response=self.session.post(f"{self.settings.evolution_url}/message/sendText/{self.settings.evolution_instance}",headers={"apikey":self.settings.evolution_api_key,"Content-Type":"application/json"},json={"number":digits,"text":text},timeout=30)
        if not response.ok: raise RuntimeError(f"Evolution HTTP {response.status_code}: {response.text[:300]}")
        body=response.json() if response.text else {}; key=body.get("key") or {}
        return {"ok":True,"external_id":key.get("id") or body.get("id") or ""}
    def test(self) -> dict:
        if not self._configured(): return {"provider":self.name,"configured":False,"ok":False,"error":"variáveis ausentes"}
        try:
            r=self.session.get(f"{self.settings.evolution_url}/instance/connectionState/{self.settings.evolution_instance}",headers={"apikey":self.settings.evolution_api_key},timeout=15)
            return {"provider":self.name,"configured":True,"ok":r.ok,"status_code":r.status_code,"state":(r.json() if r.ok else r.text[:200])}
        except Exception as exc: return {"provider":self.name,"configured":True,"ok":False,"error":str(exc)}


class MetaCloudProvider(WhatsAppProvider):
    name="meta"
    def __init__(self, settings: Settings, session=None): self.settings=settings; self.session=session or requests.Session()
    def _configured(self)->bool: return bool(self.settings.meta_access_token and self.settings.meta_phone_number_id)
    def send_text(self, phone: str, text: str, *, template: bool=False)->dict:
        if not self._configured(): raise RuntimeError("Meta WhatsApp Cloud API não configurada")
        number=(normalize_phone(phone) or "").lstrip("+")
        url=f"https://graph.facebook.com/{self.settings.meta_graph_version}/{self.settings.meta_phone_number_id}/messages"
        headers={"Authorization":f"Bearer {self.settings.meta_access_token}","Content-Type":"application/json"}
        if template:
            if not self.settings.meta_template_name: raise RuntimeError("META_TEMPLATE_NAME não configurado")
            payload:dict[str,Any]={"messaging_product":"whatsapp","to":number,"type":"template","template":{"name":self.settings.meta_template_name,"language":{"code":self.settings.meta_template_language}}}
        else:
            payload={"messaging_product":"whatsapp","to":number,"type":"text","text":{"preview_url":True,"body":text}}
        r=self.session.post(url,headers=headers,json=payload,timeout=30)
        if not r.ok: raise RuntimeError(f"Meta HTTP {r.status_code}: {r.text[:300]}")
        data=r.json(); messages=data.get("messages") or []
        return {"ok":True,"external_id":(messages[0].get("id") if messages else "")}
    def test(self)->dict:
        if not self._configured(): return {"provider":self.name,"configured":False,"ok":False,"error":"variáveis ausentes"}
        try:
            r=self.session.get(f"https://graph.facebook.com/{self.settings.meta_graph_version}/{self.settings.meta_phone_number_id}",headers={"Authorization":f"Bearer {self.settings.meta_access_token}"},timeout=15)
            return {"provider":self.name,"configured":True,"ok":r.ok,"status_code":r.status_code}
        except Exception as exc: return {"provider":self.name,"configured":True,"ok":False,"error":str(exc)}


class MessagingService:
    def __init__(self, settings: Settings, db, provider: WhatsAppProvider | None=None):
        self.settings=settings; self.db=db; self.policy=OutboundPolicy(settings)
        if provider is not None: self.provider=provider
        elif settings.wa_provider=="meta": self.provider=MetaCloudProvider(settings)
        elif settings.wa_provider=="evolution": self.provider=EvolutionProvider(settings)
        else: self.provider=None

    def preview_eligibility(self, company:dict, *, manual_reply:bool=False)->Eligibility:
        if hasattr(self.db,"is_blacklisted") and self.db.is_blacklisted(company.get("telefone")): return Eligibility(False,"telefone em blacklist")
        return self.policy.evaluate(phone=company.get("telefone"),permission=self.db.get_permission(company.get("telefone")),daily_count=self.db.outbound_count_today(),last_outbound=self.db.last_outbound_for_phone(company.get("telefone") or ""),manual_reply=manual_reply)

    def send(self, company:dict, text:str, *, dry_run:bool|None=None, manual_reply:bool=False, template:bool=False)->dict:
        dry_run=self.settings.wa_dry_run if dry_run is None else bool(dry_run)
        eligibility=self.preview_eligibility(company,manual_reply=manual_reply)
        if not eligibility.allowed:
            self.db.log_wa_event(company_id=company.get("id"),phone=company.get("telefone"),provider=self.settings.wa_provider,direction="out",status="blocked",preview=text,error=eligibility.reason)
            return {"ok":False,"blocked":True,"reason":eligibility.reason}
        if dry_run:
            self.db.log_wa_event(company_id=company.get("id"),phone=company.get("telefone"),provider=self.settings.wa_provider,direction="out",status="dry_run",preview=text)
            return {"ok":True,"dry_run":True}
        if not self.provider: return {"ok":False,"blocked":True,"reason":"provider desativado"}
        try:
            sent=self.provider.send_text(company.get("telefone") or "",text,template=template)
            self.db.log_wa_event(company_id=company.get("id"),phone=company.get("telefone"),provider=self.provider.name,direction="out",status="sent",preview=text,external_id=sent.get("external_id", ""))
            return {"ok":True,"provider":self.provider.name,**sent}
        except Exception as exc:
            self.db.log_wa_event(company_id=company.get("id"),phone=company.get("telefone"),provider=self.settings.wa_provider,direction="out",status="error",preview=text,error=str(exc))
            return {"ok":False,"error":str(exc)}

    def send_many(self, companies:list[dict], messages:dict[int,str], *, dry_run:bool|None=None)->dict:
        results=[]
        for company in companies:
            text=messages.get(company.get("id")) or ""
            if not text.strip(): results.append({"id":company.get("id"),"ok":False,"reason":"mensagem vazia"}); continue
            results.append({"id":company.get("id"),**self.send(company,text.strip(),dry_run=dry_run)})
        return {"results":results,"sent":sum(1 for r in results if r.get("ok") and not r.get("dry_run")),"dry_run":sum(1 for r in results if r.get("dry_run")),"blocked":sum(1 for r in results if r.get("blocked")),"errors":sum(1 for r in results if not r.get("ok") and not r.get("blocked"))}
