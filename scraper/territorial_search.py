"""Execução da busca territorial usando as funções maduras do google_maps legado."""
from __future__ import annotations

import logging

from config import CONFIG
from scraper.coverage import CoveragePlanner
from scraper.prospect_utils import enhanced_score, has_own_website, resolve_city_center, search_cell, seed_consent
from utils.identity import company_identity

logger = logging.getLogger(__name__)


def run(gm, cidade: str, categoria: str, callback_progresso=None, limite=None, stats=None):
    from database.prospecting_meta import adapt_known_company, coverage_history, find_existing, load_identity_index, record_coverage

    target_new = max(1, int(limite or CONFIG.get("max_resultados", 50)))
    stats = stats if stats is not None else {}
    index = load_identity_index()
    history = coverage_history(cidade, categoria)
    planner = CoveragePlanner(float(CONFIG.get("prospect_cell_spacing_km", 3.5)), int(CONFIG.get("prospect_max_cells", 25)))
    per_cell = max(5, int(CONFIG.get("prospect_per_cell", 18)))
    max_returned = target_new + max(target_new, 20)

    results, seen = [], set()
    new_count = known_count = total_cards = total_urls = none_count = duplicate_run = cells_scanned = 0
    driver = None
    try:
        driver = gm.criar_driver()
        seed_consent(driver)
        center_lat, center_lng = resolve_city_center(driver, cidade)
        cells = planner.plan(center_lat, center_lng, history)

        for cell_index, cell in enumerate(cells, start=1):
            if new_count >= target_new:
                break
            try:
                items = search_cell(gm, driver, cidade, categoria, cell, per_cell)
            except Exception as exc:
                if not gm._driver_morto(exc):
                    raise
                logger.warning("[prospecção] Chrome caiu na célula %s; recriando.", cell.key)
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = gm.criar_driver()
                seed_consent(driver)
                items = search_cell(gm, driver, cidade, categoria, cell, per_cell)

            total_cards += len(items)
            total_urls += len(items)
            cell_results = 0
            places_since_restart = 0

            for item in items:
                if new_count >= target_new:
                    break
                if places_since_restart >= 6:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = gm.criar_driver()
                    seed_consent(driver)
                    places_since_restart = 0

                company = None
                for attempt in range(2):
                    try:
                        company = gm._extrair_de_url(driver, item.get("url", ""), item.get("nome_hint", ""))
                        break
                    except Exception as exc:
                        if attempt == 0 and gm._driver_morto(exc):
                            try:
                                driver.quit()
                            except Exception:
                                pass
                            driver = gm.criar_driver()
                            seed_consent(driver)
                            places_since_restart = 0
                            continue
                        logger.warning("[prospecção] Falha ao extrair place: %s", exc)
                        break
                places_since_restart += 1
                if not company:
                    none_count += 1
                    continue

                if company.get("site_url"):
                    company["tem_site"] = has_own_website(company.get("site_url"))

                ident = company_identity(company)
                keys = tuple(v for v in (ident.get("phone"), ident.get("place_id"), ident.get("fingerprint")) if v)
                if not keys:
                    keys = ((company.get("nome"), company.get("endereco"), company.get("maps_url")),)
                if any(key in seen for key in keys):
                    duplicate_run += 1
                    continue
                seen.update(keys)

                existing = find_existing(company, index)
                is_new = existing is None
                if existing is None:
                    new_count += 1
                else:
                    known_count += 1
                    adapt_known_company(company, existing)

                company["score"] = enhanced_score(gm._calcular_score_legado, company, categoria)
                company["_prospect_new"] = is_new
                company["_coverage_cell"] = cell.key
                cell_results += 1
                if len(results) < max_returned or is_new:
                    results.append(company)
                if callback_progresso:
                    callback_progresso({"atual": new_count, "total": target_new, "empresa": company.get("nome", "")})

            record_coverage(cidade, categoria, cell.key, cell_results)
            cells_scanned += 1
            logger.info(
                "[prospecção] célula %d/%d %s: %d resultados | novas=%d conhecidas=%d",
                cell_index, len(cells), cell.key, cell_results, new_count, known_count,
            )
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    stats.update({
        "pedidas": target_new, "cards": total_cards, "urls": total_urls, "extraidas": len(results),
        "sem_dados": none_count, "dup_tel": duplicate_run, "novas": new_count,
        "conhecidas": known_count, "celulas": cells_scanned, "modo_cobertura": True,
    })
    return results
