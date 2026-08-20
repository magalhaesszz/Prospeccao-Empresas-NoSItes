from __future__ import annotations

from urllib.parse import urlparse

SOCIAL_HOSTS = {"instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com", "tiktok.com", "www.tiktok.com", "linktr.ee", "wa.me"}
HIGH_VALUE = ("advoc", "clinic", "clínic", "dent", "imobili", "contab", "veterin", "arquitet", "engenh", "academia")


def has_own_website(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return False
    return bool(host and host not in SOCIAL_HOSTS)


def lead_score(company: dict) -> int:
    score = 0
    if not company.get("tem_site"):
        score += 35
    if company.get("telefone"):
        score += 20
    rating = company.get("nota") or 0
    reviews = company.get("avaliacoes") or 0
    if rating >= 4.3:
        score += 10
    if reviews >= 20:
        score += 10
    if reviews >= 100:
        score += 5
    category = (company.get("descricao_google") or company.get("categoria") or "").lower()
    if any(x in category for x in HIGH_VALUE):
        score += 15
    if company.get("email"):
        score += 5
    return max(0, min(100, score))
