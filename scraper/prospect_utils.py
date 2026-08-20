"""Utilitários da camada territorial que reutiliza o scraper legado."""
from __future__ import annotations

import re
import time
from urllib.parse import quote_plus, urlparse

SOCIAL_HOSTS = {
    "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com",
    "fb.com", "www.fb.com", "tiktok.com", "www.tiktok.com", "x.com", "www.x.com",
    "twitter.com", "www.twitter.com", "linkedin.com", "www.linkedin.com",
    "youtube.com", "www.youtube.com", "youtu.be", "wa.me", "whatsapp.com",
    "linktr.ee", "www.linktr.ee", "linktree.com", "www.linktree.com",
}


def has_own_website(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return bool(host) and not any(host == social or host.endswith("." + social) for social in SOCIAL_HOSTS)


def enhanced_score(original_score, company: dict, categoria: str = "") -> int:
    """Preserva o score legado e só acrescenta sinais positivos de atividade."""
    base = int(original_score(company, categoria))
    try:
        rating = float(company.get("nota") or 0)
    except (TypeError, ValueError):
        rating = 0
    try:
        reviews = int(company.get("avaliacoes") or 0)
    except (TypeError, ValueError):
        reviews = 0
    extra = (5 if rating >= 4.3 else 0) + (5 if reviews >= 20 else 0) + (5 if reviews >= 100 else 0)
    return max(0, min(100, base + extra))


def coords_from_url(url: str):
    match = re.search(r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", url or "")
    return (float(match.group(1)), float(match.group(2))) if match else None


def resolve_city_center(driver, cidade: str):
    driver.get(f"https://www.google.com/maps/search/{quote_plus(cidade)}?hl=pt-BR&gl=BR")
    deadline = time.time() + 18
    while time.time() < deadline:
        coords = coords_from_url(driver.current_url)
        if coords:
            return coords
        time.sleep(0.5)
    raise RuntimeError(f"não foi possível resolver o centro de {cidade}")


def seed_consent(driver):
    try:
        driver.get("https://www.google.com/")
        time.sleep(0.6)
        for dom in (".google.com", ".google.com.br"):
            try:
                driver.add_cookie({"name": "CONSENT", "value": "YES+cb.20210328-17-p0.en+FX+000", "domain": dom})
            except Exception:
                pass
    except Exception:
        pass


def search_cell(gm, driver, cidade: str, categoria: str, cell, limit: int):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    query = quote_plus(f"{categoria} em {cidade}")
    driver.get(f"https://www.google.com/maps/search/{query}/@{cell.lat},{cell.lng},15z?hl=pt-BR&gl=BR")
    time.sleep(2.0)
    gm._fechar_consentimento(driver)
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]')))
    except Exception:
        pass
    gm._rolar_feed(driver, max(limit, 5))
    items = gm._coletar_itens_feed(driver)
    return items[: max(limit * 2, limit)]
