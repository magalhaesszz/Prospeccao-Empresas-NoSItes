"""Scraper legado com extensões incrementais e reversíveis.

Nada do ``google_maps.py`` original é removido: ele é carregado primeiro e só
então recebe wrappers que preservam as funções originais como ``*_legado``.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from . import google_maps as _google_maps
    from .prospecting import install as _install_prospecting
    _install_prospecting(_google_maps)
except Exception as _exc:
    # Importar o pacote jamais pode impedir o scraper legado de subir.
    logger.warning("Extensões de prospecção não carregadas; legado preservado: %s", _exc)
