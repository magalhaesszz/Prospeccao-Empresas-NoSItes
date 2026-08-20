from prospector.prospecting import ProspectingService
from prospector.settings import Settings
class Center:lat=-16.68;lng=-49.26
class FakeScraper:
    def __init__(self):self.calls=0
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def resolve_city_center(self,city):return Center()
    def search_cell(self,city,category,cell,limit):
        self.calls+=1
        if self.calls==1:return [{"nome":"Old","telefone":"62999990000","endereco":"Rua A 1","tem_site":False}]
        return [{"nome":f"New {self.calls}","telefone":f"62999990{self.calls:03d}","endereco":f"Rua B {self.calls}","tem_site":False}]
class FakeDB:
    def __init__(self):self.saved=0;self.coverage=[]
    def create_run(self,c,cat):return 10
    def coverage_history(self,c,cat):return {}
    def upsert_company(self,company,run_id,city,cat,cell):self.saved+=1;return {"id":self.saved,"is_new":company["nome"].startswith("New"),"matched_by":"new"}
    def record_coverage(self,*args):self.coverage.append(args)
    def finish_run(self,*args):self.finished=args
def test_target_counts_new_not_known(monkeypatch):
    monkeypatch.setenv("MAX_RESULTADOS","10");monkeypatch.setenv("PROSPECT_MAX_CELLS","9");monkeypatch.setenv("PROSPECT_PER_CELL","5");out=ProspectingService(Settings(),FakeDB(),FakeScraper).run("Goiânia","Clínica",2);assert out["new"]==2;assert out["known"]==1;assert out["cells"]==3
