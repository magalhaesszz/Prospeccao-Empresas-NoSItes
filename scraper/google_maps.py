"""Google Maps prospecting scraper with geographic coverage."""
from __future__ import annotations
import logging,re,time
from dataclasses import dataclass
from urllib.parse import quote_plus
from prospector.identity import maps_place_id
from prospector.scoring import has_own_website,lead_score
from prospector.settings import settings
logger=logging.getLogger(__name__)
@dataclass(frozen=True)
class MapCenter: lat:float; lng:float
class GoogleMapsScraper:
    def __init__(self,headless:bool|None=None):self.headless=settings.headless if headless is None else headless;self.driver=None
    def __enter__(self):self.driver=self._create_driver();return self
    def __exit__(self,exc_type,exc,tb):self.close()
    def close(self):
        if self.driver:
            try:self.driver.quit()
            except Exception:pass
            self.driver=None
    def _create_driver(self):
        import shutil
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        options=Options();args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1280,900","--lang=pt-BR,pt","--disable-extensions","--disable-background-networking","--disable-default-apps","--disable-sync","--blink-settings=imagesEnabled=false"]
        if self.headless:args.append("--headless=new")
        for arg in args:options.add_argument(arg)
        chrome=shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome");driver_path=shutil.which("chromedriver")
        if chrome:options.binary_location=chrome
        if driver_path:return webdriver.Chrome(service=Service(driver_path),options=options)
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            return webdriver.Chrome(service=Service(ChromeDriverManager().install()),options=options)
        except Exception as exc:raise RuntimeError(f"ChromeDriver indisponível: {exc}") from exc
    def _ensure(self):
        if not self.driver:self.driver=self._create_driver()
        return self.driver
    @staticmethod
    def _coords_from_url(url:str)->MapCenter|None:
        m=re.search(r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",url or "");return MapCenter(float(m.group(1)),float(m.group(2))) if m else None
    def resolve_city_center(self,city:str)->MapCenter:
        d=self._ensure();d.get(f"https://www.google.com/maps/search/{quote_plus(city)}?hl=pt-BR&gl=BR");deadline=time.time()+15
        while time.time()<deadline:
            center=self._coords_from_url(d.current_url)
            if center:return center
            time.sleep(.5)
        raise RuntimeError(f"não foi possível resolver o centro de {city}")
    def search_cell(self,city:str,category:str,cell,limit:int=20)->list[dict]:
        d=self._ensure();query=quote_plus(f"{category} em {city}");d.get(f"https://www.google.com/maps/search/{query}/@{cell.lat},{cell.lng},15z?hl=pt-BR&gl=BR");self._accept_consent();self._wait_feed();self._scroll_feed(limit);links=self._collect_place_links(limit*2);results=[];seen=set()
        for link in links:
            key=maps_place_id(link) or link.split("?",1)[0]
            if key in seen:continue
            seen.add(key)
            try:item=self._extract_place(link)
            except Exception as exc:logger.warning("Falha ao extrair %s: %s",link[:80],exc);continue
            if item:results.append(item)
            if len(results)>=limit:break
        return results
    def _accept_consent(self):
        from selenium.webdriver.common.by import By
        for button in self._ensure().find_elements(By.CSS_SELECTOR,"button"):
            try:
                text=(button.text or button.get_attribute("aria-label") or "").strip().lower()
                if text in {"aceitar tudo","accept all","concordo","aceitar"}:button.click();time.sleep(1);return
            except Exception:pass
    def _wait_feed(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:WebDriverWait(self._ensure(),12).until(EC.presence_of_element_located((By.CSS_SELECTOR,'div[role="feed"]')))
        except Exception:pass
    def _scroll_feed(self,target:int):
        from selenium.webdriver.common.by import By
        d=self._ensure();stable=0;last=0
        for _ in range(24):
            try:
                feed=d.find_element(By.CSS_SELECTOR,'div[role="feed"]');links=feed.find_elements(By.XPATH,".//a[contains(@href,'/maps/place/')]");count=len({x.get_attribute("href") for x in links if x.get_attribute("href")})
                if count>=target:return
                stable=stable+1 if count==last else 0;last=count
                if stable>=5:return
                d.execute_script("arguments[0].scrollTop=arguments[0].scrollHeight",feed)
                if links:d.execute_script("arguments[0].scrollIntoView(false)",links[-1])
                time.sleep(1.2)
            except Exception:return
    def _collect_place_links(self,limit:int)->list[str]:
        from selenium.webdriver.common.by import By
        d=self._ensure()
        try:feed=d.find_element(By.CSS_SELECTOR,'div[role="feed"]');elements=feed.find_elements(By.XPATH,".//a[contains(@href,'/maps/place/')]")
        except Exception:elements=d.find_elements(By.XPATH,"//a[contains(@href,'/maps/place/')]")
        out=[];seen=set()
        for el in elements:
            href=el.get_attribute("href") or ""
            if href and href not in seen:seen.add(href);out.append(href)
            if len(out)>=limit:break
        return out
    @staticmethod
    def _first_text(driver,selectors:list[str])->str:
        from selenium.webdriver.common.by import By
        for selector in selectors:
            try:
                text=(driver.find_element(By.CSS_SELECTOR,selector).text or "").strip()
                if text:return text
            except Exception:pass
        return ""
    def _extract_place(self,url:str)->dict|None:
        from selenium.webdriver.common.by import By
        d=self._ensure();d.get(url);time.sleep(1.1);name=self._first_text(d,["h1.DUwDvf","h1"])
        if not name or name.lower() in {"results","google maps","google"}:return None
        address="";phone=None;site_url=""
        try:el=d.find_element(By.CSS_SELECTOR,'button[data-item-id="address"]');address=self._first_text(el,[".Io6YTe","div","span"])
        except Exception:pass
        try:el=d.find_element(By.CSS_SELECTOR,'button[data-item-id^="phone:tel:"]');phone=(el.get_attribute("data-item-id") or "").replace("phone:tel:","").strip()
        except Exception:pass
        try:site_url=d.find_element(By.CSS_SELECTOR,'a[data-item-id="authority"]').get_attribute("href") or ""
        except Exception:pass
        category=self._first_text(d,["button.DkEaL",".DkEaL","button[jsaction*='category']"]);rating=None;reviews=0
        for selector in ["span.MW4etd",'span[aria-label*="estrela"]','span[aria-label*="star"]']:
            try:
                el=d.find_element(By.CSS_SELECTOR,selector);raw=el.get_attribute("aria-label") or el.text or "";m=re.search(r"(\d)[,.](\d)",raw)
                if m:rating=float(f"{m.group(1)}.{m.group(2)}");break
            except Exception:pass
        try:
            for el in d.find_elements(By.CSS_SELECTOR,'span[aria-label*="avalia"], button[aria-label*="avalia"], span[aria-label*="review"]'):
                raw=el.get_attribute("aria-label") or el.text or "";m=re.search(r"([\d\.]+)\s*(?:avalia|review)",raw.lower())
                if m:reviews=int(m.group(1).replace(".",""));break
        except Exception:pass
        item={"nome":name,"telefone":phone,"endereco":address,"email":None,"tem_site":has_own_website(site_url),"site_url":site_url,"descricao_google":category,"nota":rating,"avaliacoes":reviews,"maps_url":url,"foto_url":"","fotos_urls":"[]"};item["score"]=lead_score(item);return item

def buscar_empresas(cidade,categoria,callback_progresso=None,limite=None,stats=None):
    from prospector.coverage import CoveragePlanner
    target=limite or settings.max_results;stats=stats if stats is not None else {}
    with GoogleMapsScraper() as scraper:
        center=scraper.resolve_city_center(cidade);planner=CoveragePlanner(settings.coverage_spacing_km,min(settings.max_coverage_cells,9));results=[];seen=set()
        for cell in planner.plan(center.lat,center.lng):
            for company in scraper.search_cell(cidade,categoria,cell,min(settings.per_cell_results,target)):
                key=maps_place_id(company.get("maps_url")) or (company.get("telefone"),company.get("nome"),company.get("endereco"))
                if key in seen:continue
                seen.add(key);results.append(company)
                if callback_progresso:callback_progresso({"atual":len(results),"total":target,"empresa":company.get("nome","")})
                if len(results)>=target:stats.update({"pedidas":target,"extraidas":len(results),"celulas":planner.max_cells});return results
        stats.update({"pedidas":target,"extraidas":len(results),"celulas":planner.max_cells});return results
