from __future__ import annotations

import re
from dataclasses import dataclass

from .identity import normalize_phone

OPTOUT_PATTERNS=(r"\bparar\b",r"\bpare\b",r"\bsair\b",r"\bstop\b",r"\bremover\b",r"\bn[aã]o quero\b",r"\bn[aã]o tenho interesse\b",r"\bdescadastrar\b")

def is_optout(text:str|None)->bool:
    value=(text or "").lower().strip(); return any(re.search(p,value) for p in OPTOUT_PATTERNS)

@dataclass(frozen=True)
class InboundMessage:
    phone:str
    text:str
    external_id:str=""

def parse_evolution(payload:dict)->InboundMessage|None:
    data=payload.get("data") or payload; key=data.get("key") or {}
    if key.get("fromMe"): return None
    jid=key.get("remoteJid") or data.get("remoteJid") or ""
    if "@g.us" in jid or "status@broadcast" in jid: return None
    phone=normalize_phone(jid.split("@",1)[0])
    if not phone: return None
    msg=data.get("message") or {}; text=msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text") or data.get("text") or ""
    if not isinstance(text,str) or not text.strip(): return None
    return InboundMessage(phone=phone,text=text.strip(),external_id=str(key.get("id") or ""))

def parse_meta(payload:dict)->list[InboundMessage]:
    out=[]
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            for msg in (change.get("value") or {}).get("messages") or []:
                if msg.get("type")!="text": continue
                phone=normalize_phone(msg.get("from")); text=(msg.get("text") or {}).get("body") or ""
                if phone and text.strip(): out.append(InboundMessage(phone,text.strip(),str(msg.get("id") or "")))
    return out

def process_inbound(db,message:InboundMessage,provider:str)->dict:
    company=None
    try:
        rows=db.list_companies(q=message.phone,limit=5); company=next((r for r in rows if normalize_phone(r.get("telefone"))==message.phone),None)
    except Exception: company=None
    db.log_wa_event(company_id=company.get("id") if company else None,phone=message.phone,provider=provider,direction="in",status="received",preview=message.text,external_id=message.external_id)
    opted_out=is_optout(message.text)
    if opted_out:
        db.set_permission(message.phone,"opted_out",f"{provider}_inbound",message.text[:300]); db.add_blacklist(message.phone,"opt-out recebido pelo WhatsApp")
    return {"phone":message.phone,"opted_out":opted_out,"company_id":company.get("id") if company else None}
