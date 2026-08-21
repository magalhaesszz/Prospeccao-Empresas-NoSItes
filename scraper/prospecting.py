"""Instala melhorias incrementais preservando o scraper original como fallback."""
from __future__ import annotations

import logging
import re

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
    """Extrai somente a quantidade de avaliações, sem confundir com a nota."""
    text = (raw or "").replace("\xa0", " ").strip()
    if not text:
        return None

    patterns = (
        rf"(\d[\d\s.,]*?(?:\s*{_REVIEW_UNIT})?)\s*{_REVIEW_WORDS}\b",
        rf"{_REVIEW_WORDS}\b[^0-9]{{0,20}}(\d[\d\s.,]*?(?:\s*{_REVIEW_UNIT})?)(?:\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _parse_review_number(match.group(1))
            if value is not None:
                return value

    # O container de rating do Maps costuma exibir "4,8 (123)".
    for match in re.finditer(
        rf"\((\s*\d[\d\s.,]*(?:\s*{_REVIEW_UNIT})?\s*)\)",
        text,
        re.IGNORECASE,
    ):
        value = _parse_review_number(match.group(1))
        if value is not None:
            return value
    return None


def _extract_review_count(driver):
    """Lê a contagem no DOM atual do Maps, independente da tag/classe usada."""
    try:
        candidates = driver.execute_script(
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
              add(el.textContent);
            };

            document.querySelectorAll('div.F7nice, span.UY7F9, span.e4rVHe')
              .forEach(addElement);

            document.querySelectorAll('[aria-label]').forEach((el) => {
              const label = (el.getAttribute('aria-label') || '').toLowerCase();
              if (label.includes('avalia') || label.includes('review') || label.includes('coment')) {
                addElement(el);
              }
            });
            return values;
            """
        ) or []
    except Exception:
        return None

    for candidate in candidates:
        value = _parse_review_count(candidate)
        if value is not None:
            return value
    return None


def build_review_count_extractor(legacy_extract):
    def extrair_de_url(driver, maps_url, nome_hint=""):
        company = legacy_extract(driver, maps_url, nome_hint)
        if not company:
            return company

        # Recalcula apenas este campo usando o DOM atual. Mantém todos os outros
        # dados exatamente como o scraper legado extraiu.
        count = _extract_review_count(driver)
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

    gm.buscar_empresas_legado = legacy_search
    gm._calcular_score_legado = legacy_score
    gm.buscar_empresas = build_improved_search(gm, legacy_search)
    gm._calcular_score = lambda company, categoria="": enhanced_score(legacy_score, company, categoria)

    if callable(legacy_extract):
        gm._extrair_de_url_legado = legacy_extract
        gm._extrair_de_url = build_review_count_extractor(legacy_extract)

    gm._PROSPECT_EXTENSIONS_INSTALLED = True
    logger.info("[prospecção] cobertura territorial/dedup incremental ativos")


__all__ = ["install", "build_improved_search", "enhanced_score", "has_own_website"]
