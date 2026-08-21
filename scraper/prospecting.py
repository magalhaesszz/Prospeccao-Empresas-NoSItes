"""Instala melhorias incrementais preservando o scraper original como fallback."""
from __future__ import annotations

import html
import logging
import re
import time

from config import CONFIG
from scraper.prospect_utils import enhanced_score, has_own_website

logger = logging.getLogger(__name__)

_REVIEW_WORDS = r"(?:avalia(?:ç(?:ão|ões))?|review(?:s)?|coment[aá]rio(?:s)?)"
_REVIEW_UNIT = r"(?:milh(?:ão|ões|oes)|mil|k|m)"


def _parse_review_number(raw):
    """Converte contagens do Maps como 1.234, 1,2 mil e 1.2K em inteiro."""
    text = (raw or "").strip().lower().replace("\xa0", " ")
    unit_match = re.search(r"(milh(?:ão|ões|oes)|mil|k|m)\s*$", text, re.IGNORECASE)
    unit = unit_match.group(1).lower() if unit_match else ""
    number = re.sub(r"[^\d,.]", "", text)
    if not number:
        return None

    if unit:
        if "," in number and "." in number:
            normalized = number.replace(".", "").replace(",", ".")
        elif "," in number:
            normalized = number.replace(",", ".")
        else:
            normalized = number
        try:
            value = float(normalized)
        except ValueError:
            return None
        multiplier = 1_000_000 if unit.startswith("milh") or unit == "m" else 1_000
        return int(round(value * multiplier))

    digits = re.sub(r"\D", "", number)
    return int(digits) if digits else None


def _parse_review_count(raw):
    """Extrai somente a quantidade de avaliações, sem confundir com nota/telefone."""
    text = (raw or "").replace("\xa0", " ").strip()
    if not text:
        return None

    # Formatos explícitos: "123 avaliações", "1,2 mil reviews",
    # "avaliações: 123" etc. São os mais confiáveis.
    patterns = (
        rf"(\d[\d\s.,]*?(?:\s*{_REVIEW_UNIT})?)\s*{_REVIEW_WORDS}\b",
        rf"{_REVIEW_WORDS}\b[^0-9]{{0,24}}(\d[\d\s.,]*?(?:\s*{_REVIEW_UNIT})?)(?:\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _parse_review_number(match.group(1))
            if value is not None:
                return value

    count_expr = rf"(\d[\d\s.,]*(?:\s*{_REVIEW_UNIT})?)"

    # Quando o seletor já aponta exatamente para o contador, o Maps costuma
    # fornecer somente "(123)".
    match = re.fullmatch(rf"\s*\(\s*{count_expr}\s*\)\s*", text, re.IGNORECASE)
    if match:
        return _parse_review_number(match.group(1))

    # Container de rating: "4,8 (123)" / "4.8 · (1.2K)".
    # Exigir a nota antes dos parênteses evita confundir DDD de telefone "(11)".
    match = re.search(
        rf"(?:^|[^\d])(?:[0-5][,.]\d)\s*[^0-9]{{0,20}}\(\s*{count_expr}\s*\)",
        text,
        re.IGNORECASE,
    )
    if match:
        return _parse_review_number(match.group(1))

    return None


def _url_variants(url):
    value = (url or "").strip()
    if not value:
        return ()
    variants = [value.rstrip("/")]
    if "?" in value:
        variants.append(value.split("?", 1)[0].rstrip("/"))
    if "#" in value:
        variants.append(value.split("#", 1)[0].rstrip("/"))
    return tuple(dict.fromkeys(v for v in variants if v))


def _remember_review_hint(review_hints, url, count):
    if count is None:
        return
    for key in _url_variants(url):
        review_hints[key] = count


def _lookup_review_hint(review_hints, url):
    for key in _url_variants(url):
        if key in review_hints:
            return review_hints[key]
    return None


def _collect_feed_review_hints(driver):
    """Lê a contagem diretamente dos cards antes de navegar para cada place."""
    try:
        records = driver.execute_script(
            """
            const feed = document.querySelector('div[role="feed"]');
            if (!feed) return [];

            const out = [];
            const seen = new Set();

            const add = (arr, value) => {
              value = (value || '').trim();
              if (value && !arr.includes(value)) arr.push(value);
            };

            for (const anchor of feed.querySelectorAll('a[href*="/maps/place/"]')) {
              const url = anchor.href || anchor.getAttribute('href') || '';
              if (!url || seen.has(url)) continue;
              seen.add(url);

              const card =
                anchor.closest('div.Nv2PK, div[role="article"], div.UaQhfb') ||
                anchor.parentElement;

              const values = [];
              if (card) {
                card.querySelectorAll(
                  'span.UY7F9, span.e4rVHe, div.F7nice, span.MW4etd, [aria-label]'
                ).forEach((el) => {
                  const label = el.getAttribute && el.getAttribute('aria-label');
                  if (label) {
                    const low = label.toLowerCase();
                    if (
                      low.includes('avalia') ||
                      low.includes('review') ||
                      low.includes('coment') ||
                      el.matches('span.UY7F9, span.e4rVHe, div.F7nice')
                    ) add(values, label);
                  }
                  if (el.matches('span.UY7F9, span.e4rVHe, div.F7nice')) {
                    add(values, el.textContent);
                  }
                });

                add(values, card.textContent);
              }

              out.push({url, values});
            }
            return out;
            """
        ) or []
    except Exception:
        return {}

    hints = {}
    for record in records:
        url = (record or {}).get("url", "")
        for candidate in (record or {}).get("values", []) or []:
            count = _parse_review_count(candidate)
            if count is not None:
                for key in _url_variants(url):
                    hints[key] = count
                break
    return hints


def _detail_review_candidates(driver):
    """Coleta textos de avaliação do painel aberto da empresa."""
    try:
        return driver.execute_script(
            """
            const values = [];
            const seen = new Set();
            const add = (value) => {
              value = (value || '').trim();
              if (value && !seen.has(value)) {
                seen.add(value);
                values.push(value);
              }
            };
            const addElement = (el) => {
              if (!el) return;
              add(el.getAttribute && el.getAttribute('aria-label'));
              add(el.getAttribute && el.getAttribute('title'));
              add(el.textContent);
            };

            document.querySelectorAll(
              'div.F7nice, span.UY7F9, span.e4rVHe, ' +
              'button[jsaction*="rating"], button[jsaction*="review"], ' +
              'a[jsaction*="review"]'
            ).forEach(addElement);

            document.querySelectorAll('[aria-label]').forEach((el) => {
              const label = (el.getAttribute('aria-label') || '').toLowerCase();
              if (
                label.includes('avalia') ||
                label.includes('review') ||
                label.includes('coment')
              ) addElement(el);
            });

            document.querySelectorAll('button, a').forEach((el) => {
              const text = (el.textContent || '').toLowerCase();
              if (
                text.includes('avalia') ||
                text.includes('review') ||
                text.includes('coment')
              ) addElement(el);
            });

            return values;
            """
        ) or []
    except Exception:
        return []


def _extract_review_count_once(driver):
    for candidate in _detail_review_candidates(driver):
        value = _parse_review_count(candidate)
        if value is not None:
            return value

    try:
        source = driver.page_source or ""
    except Exception:
        source = ""

    if source:
        for word in re.finditer(_REVIEW_WORDS, source, re.IGNORECASE):
            snippet = source[max(0, word.start() - 120): min(len(source), word.end() + 120)]
            snippet = html.unescape(snippet)
            snippet = re.sub(r"<[^>]+>", " ", snippet)
            value = _parse_review_count(snippet)
            if value is not None:
                return value
    return None


def _extract_review_count(driver, retries=0, delay=0.4):
    value = _extract_review_count_once(driver)
    if value is not None:
        return value
    for _ in range(max(0, int(retries))):
        time.sleep(delay)
        value = _extract_review_count_once(driver)
        if value is not None:
            return value
    return None


def build_feed_collector(legacy_collect, review_hints):
    def coletar_itens_feed(driver):
        items = legacy_collect(driver)

        review_hints.clear()
        discovered = _collect_feed_review_hints(driver)

        for item in items:
            count = None
            for key in _url_variants(item.get("url", "")):
                if key in discovered:
                    count = discovered[key]
                    break
            if count is not None:
                item["avaliacoes_hint"] = count
                _remember_review_hint(review_hints, item.get("url", ""), count)

        return items

    coletar_itens_feed.__name__ = getattr(legacy_collect, "__name__", "_coletar_itens_feed")
    coletar_itens_feed.__doc__ = legacy_collect.__doc__
    return coletar_itens_feed


def build_review_count_extractor(legacy_extract, review_hints):
    def extrair_de_url(driver, maps_url, nome_hint=""):
        company = legacy_extract(driver, maps_url, nome_hint)
        if not company:
            return company

        # 1) painel da empresa aberta
        count = _extract_review_count_once(driver)

        # 2) card da busca, coletado antes de sair do feed
        if count is None:
            count = _lookup_review_hint(review_hints, maps_url)

        # 3) se existe nota, sabemos que há avaliações; dá uma curta chance extra
        # para o contador terminar o lazy-load do painel.
        if count is None and company.get("nota") is not None:
            count = _extract_review_count(driver, retries=3, delay=0.35)

        if count is not None:
            company["avaliacoes"] = count
        return company

    extrair_de_url.__name__ = getattr(legacy_extract, "__name__", "_extrair_de_url")
    extrair_de_url.__doc__ = legacy_extract.__doc__
    return extrair_de_url


def build_improved_search(gm, legacy_search):
    def buscar_empresas(cidade, categoria, callback_progresso=None, limite=None, stats=None, **_ignored):
        if not CONFIG.get("prospect_coverage_enabled", True):
            return legacy_search(cidade, categoria, callback_progresso, limite, stats)
        stats = stats if stats is not None else {}
        try:
            from scraper.territorial_search import run
            return run(gm, cidade, categoria, callback_progresso, limite, stats)
        except Exception as exc:
            logger.exception("[prospecção] extensão territorial falhou; usando busca antiga: %s", exc)
            stats.clear()
            result = legacy_search(cidade, categoria, callback_progresso, limite, stats)
            stats["modo_cobertura"] = False
            stats["fallback_motivo"] = str(exc)[:250]
            return result

    buscar_empresas.__name__ = getattr(legacy_search, "__name__", "buscar_empresas")
    buscar_empresas.__doc__ = (legacy_search.__doc__ or "") + "\n\nExtensão territorial incremental habilitada."
    return buscar_empresas


def install(gm) -> None:
    if getattr(gm, "_PROSPECT_EXTENSIONS_INSTALLED", False):
        return
    legacy_search = gm.buscar_empresas
    legacy_score = gm._calcular_score
    legacy_extract = getattr(gm, "_extrair_de_url", None)
    legacy_collect = getattr(gm, "_coletar_itens_feed", None)
    review_hints = {}

    gm.buscar_empresas_legado = legacy_search
    gm._calcular_score_legado = legacy_score
    gm.buscar_empresas = build_improved_search(gm, legacy_search)
    gm._calcular_score = lambda company, categoria="": enhanced_score(legacy_score, company, categoria)

    if callable(legacy_collect):
        gm._coletar_itens_feed_legado = legacy_collect
        gm._coletar_itens_feed = build_feed_collector(legacy_collect, review_hints)

    if callable(legacy_extract):
        gm._extrair_de_url_legado = legacy_extract
        gm._extrair_de_url = build_review_count_extractor(legacy_extract, review_hints)

    gm._PROSPECT_EXTENSIONS_INSTALLED = True
    logger.info("[prospecção] cobertura territorial/dedup incremental ativos")


__all__ = ["install", "build_improved_search", "enhanced_score", "has_own_website"]
