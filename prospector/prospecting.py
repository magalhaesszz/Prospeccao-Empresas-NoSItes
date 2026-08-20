from __future__ import annotations

import logging
from dataclasses import asdict

from .coverage import CoveragePlanner
from .scoring import lead_score
from .settings import Settings

logger = logging.getLogger(__name__)


class ProspectingService:
    def __init__(self, settings: Settings, db, scraper_factory):
        self.settings=settings; self.db=db; self.scraper_factory=scraper_factory

    def run(self, city:str, category:str, target_new:int, progress=None)->dict:
        target_new=max(1,min(int(target_new),self.settings.max_results)); run_id=self.db.create_run(city,category)
        stats={"run_id":run_id,"candidates":0,"new":0,"known":0,"invalid":0,"cells":0,"without_site":0}
        history=self.db.coverage_history(city,category); planner=CoveragePlanner(self.settings.coverage_spacing_km,self.settings.max_coverage_cells)
        with self.scraper_factory() as scraper:
            center=scraper.resolve_city_center(city); cells=planner.plan(center.lat,center.lng,history)
            for index,cell in enumerate(cells,start=1):
                if progress: progress({"type":"cell_start","run_id":run_id,"cell":asdict(cell),"cell_index":index,"cell_total":len(cells),**stats})
                batch=scraper.search_cell(city,category,cell,self.settings.per_cell_results); cell_new=0
                for company in batch:
                    stats["candidates"]+=1; company["score"]=lead_score(company); saved=self.db.upsert_company(company,run_id,city,category,cell.key)
                    if not saved.get("id"): stats["invalid"]+=1; continue
                    if saved["is_new"]:
                        stats["new"]+=1; cell_new+=1
                        if not company.get("tem_site"): stats["without_site"]+=1
                    else: stats["known"]+=1
                    if progress: progress({"type":"candidate","run_id":run_id,"company":company.get("nome"),"is_new":saved["is_new"],**stats})
                    if stats["new"]>=target_new: break
                stats["cells"]+=1; self.db.record_coverage(city,category,cell,len(batch),cell_new)
                if stats["new"]>=target_new: break
        self.db.finish_run(run_id,stats["new"]+stats["known"],stats["without_site"])
        if progress: progress({"type":"done",**stats})
        return stats
