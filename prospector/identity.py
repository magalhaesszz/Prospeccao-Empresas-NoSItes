from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse


def _ascii(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c))


def normalize_text(value: str | None) -> str:
    value = _ascii(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_phone(value: str | None, default_country_code: str = "55") -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits.startswith(default_country_code) and len(digits) in (10, 11):
        digits = default_country_code + digits
    if len(digits) not in (12, 13):
        return None
    return "+" + digits


def maps_place_id(url: str | None) -> str | None:
    if not url:
        return None
    decoded = unquote(url)
    try:
        parsed = urlparse(decoded)
        query = parse_qs(parsed.query)
        for key in ("query_place_id", "ftid", "cid"):
            if query.get(key) and query[key][0]:
                return f"{key}:{query[key][0]}"
    except Exception:
        pass
    for pattern in (
        r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)",
        r"!1s(ChI[A-Za-z0-9_-]+)",
        r"place_id[:=](ChI[A-Za-z0-9_-]+)",
    ):
        m = re.search(pattern, decoded)
        if m:
            return m.group(1)
    return None


def company_fingerprint(name: str | None, address: str | None) -> str | None:
    n = normalize_text(name)
    a = normalize_text(address)
    if len(n) < 3 or len(a) < 6:
        return None
    raw = f"{n}|{a}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def company_identity(company: dict) -> dict[str, str | None]:
    phone = normalize_phone(company.get("telefone"))
    place = maps_place_id(company.get("maps_url"))
    fingerprint = company_fingerprint(company.get("nome"), company.get("endereco"))
    return {"phone": phone, "place_id": place, "fingerprint": fingerprint}


def canonical_company(company: dict) -> dict:
    data = dict(company)
    identity = company_identity(data)
    data["telefone"] = identity["phone"]
    data["place_id"] = identity["place_id"]
    data["fingerprint"] = identity["fingerprint"]
    data["nome"] = (data.get("nome") or "").strip()
    data["endereco"] = (data.get("endereco") or "").strip()
    return data
