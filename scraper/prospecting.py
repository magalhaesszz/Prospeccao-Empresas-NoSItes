"""Instala melhorias incrementais preservando o scraper original como fallback."""
from __future__ import annotations

import logging

from config import CONFIG
from scraper.prospect_utils import enhanced_score, has_own_website

logger = logging.getLogger(__name__)


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
    gm.buscar_empresas_legado = legacy_search
    gm._calcular_score_legado = legacy_score
    gm.buscar_empresas = build_improved_search(gm, legacy_search)
    gm._calcular_score = lambda company, categoria="": enhanced_score(legacy_score, company, categoria)
    gm._PROSPECT_EXTENSIONS_INSTALLED = True
    logger.info("[prospecção] cobertura territorial/dedup incremental ativos")


__all__ = ["install", "build_improved_search", "enhanced_score", "has_own_website"]
