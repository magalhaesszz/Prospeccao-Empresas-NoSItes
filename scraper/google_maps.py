"""
Scraping do Google Maps via Selenium / undetected-chromedriver.
Extrai nome, telefone, endereço, site e calcula score de oportunidade.
Inclui retry automático e múltiplos seletores CSS como fallback.
"""
import os, sys, time, logging, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
)

logger = logging.getLogger(__name__)


# ── Driver ────────────────────────────────────────────────────────────────────

def criar_driver():
    """Cria driver Chrome.
    - Servidor (Replit/Railway): usa chromium + chromedriver do sistema (nix/apt).
    - Local com undetected habilitado: tenta undetected-chromedriver.
    - Local fallback: webdriver-manager faz download automático.
    """
    import shutil

    opcoes_args = [
        "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        "--window-size=1280,900", "--lang=pt-BR,pt",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions", "--disable-infobars",
    ]

    if CONFIG.get("headless"):
        opcoes_args.append("--headless=new")

    # Detecta chromedriver do sistema (nix no Replit, apt no Railway)
    chromedriver_sistema = shutil.which("chromedriver")
    chromium_sistema     = shutil.which("chromium") or shutil.which("chromium-browser")

    if chromedriver_sistema:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service

        opcoes = Options()
        for arg in opcoes_args:
            opcoes.add_argument(arg)
        if chromium_sistema:
            opcoes.binary_location = chromium_sistema

        service = Service(executable_path=chromedriver_sistema)
        driver  = webdriver.Chrome(service=service, options=opcoes)
        logger.info("Driver: chromedriver do sistema (%s)", chromedriver_sistema)
        return driver

    # Local: tenta undetected-chromedriver
    if CONFIG.get("usar_undetected", True):
        try:
            import undetected_chromedriver as uc
            opcoes = uc.ChromeOptions()
            for arg in opcoes_args:
                opcoes.add_argument(arg)
            driver = uc.Chrome(options=opcoes, version_main=None)
            logger.info("Driver: undetected-chromedriver")
            return driver
        except Exception as e:
            logger.warning("undetected-chromedriver falhou (%s) — usando selenium padrão.", e)

    # Local fallback: webdriver-manager baixa o chromedriver
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opcoes = Options()
    for arg in opcoes_args:
        opcoes.add_argument(arg)
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
    opcoes.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opcoes
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    logger.info("Driver: selenium padrão + webdriver-manager")
    return driver


# ── Busca principal ───────────────────────────────────────────────────────────

def buscar_empresas(cidade, categoria, callback_progresso=None):
    """
    Ponto de entrada público.
    Retorna lista de dicts: nome, telefone, endereco, email, tem_site, site_url, score.
    """
    driver = None
    empresas = []

    try:
        logger.info("Buscando '%s' em '%s'", categoria, cidade)
        driver = criar_driver()

        query = f"{categoria} em {cidade}"
        url   = "https://www.google.com/maps/search/" + query.replace(" ", "+")
        driver.get(url)
        time.sleep(3)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
            )
        except TimeoutException:
            logger.warning("Feed demorou — continuando.")

        total = _rolar_feed(driver, CONFIG["max_resultados"])
        logger.info("%d cards no feed.", total)

        limite = min(total, CONFIG["max_resultados"])
        for i in range(limite):
            try:
                emp = _extrair_com_retry(driver, i, tentativas=2)
                if emp:
                    emp["score"] = _calcular_score(emp, categoria)
                    empresas.append(emp)
                    logger.info("[%d/%d] %s | Tel:%s Site:%s Score:%d",
                        i + 1, limite, emp["nome"],
                        emp["telefone"] or "—",
                        "S" if emp["tem_site"] else "N",
                        emp["score"])
                    if callback_progresso:
                        callback_progresso({"atual": i + 1, "total": limite, "empresa": emp["nome"]})
            except Exception as exc:
                logger.error("Erro item %d: %s", i, exc)

    except Exception as exc:
        logger.error("Erro geral: %s", exc)
        raise

    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Driver encerrado.")
            except Exception:
                pass

    logger.info("Concluído: %d empresas.", len(empresas))
    return empresas


# ── Funções internas ──────────────────────────────────────────────────────────

def _rolar_feed(driver, max_itens):
    sem_mudanca = 0
    ultima = 0
    while sem_mudanca < 5:
        try:
            feed  = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            cards = feed.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
            n = len(cards)
            if n >= max_itens:
                break
            if n == ultima:
                sem_mudanca += 1
            else:
                sem_mudanca = 0
                ultima = n
                logger.info("Feed: %d cards...", n)
            driver.execute_script("arguments[0].scrollTop=arguments[0].scrollHeight", feed)
            time.sleep(2)
        except NoSuchElementException:
            break
        except Exception as exc:
            logger.error("Erro rolagem: %s", exc)
            sem_mudanca += 1
    try:
        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        return len(feed.find_elements(By.CSS_SELECTOR, "div.Nv2PK"))
    except Exception:
        return ultima


def _extrair_com_retry(driver, indice, tentativas=2):
    """Tenta extrair item N vezes antes de desistir."""
    for t in range(tentativas):
        try:
            return _extrair_item(driver, indice)
        except StaleElementReferenceException:
            if t < tentativas - 1:
                time.sleep(1)
        except Exception as exc:
            logger.debug("Tentativa %d falhou: %s", t + 1, exc)
            if t < tentativas - 1:
                time.sleep(1)
    return None


def _extrair_item(driver, indice):
    feed  = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
    cards = feed.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
    if indice >= len(cards):
        return None

    card = cards[indice]
    driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'smooth'})", card)
    time.sleep(0.4)
    driver.execute_script("arguments[0].click()", card)
    time.sleep(2.5)

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except TimeoutException:
        pass

    # Nome
    nome = _primeiro_texto(driver, ["h1.DUwDvf", "h1[jsan]", "h1"])
    if not nome:
        return None

    # Endereço
    endereco = None
    try:
        btn = driver.find_element(By.CSS_SELECTOR, 'button[data-item-id="address"]')
        endereco = _primeiro_texto_em(btn, [".Io6YTe", "div", "span"])
    except NoSuchElementException:
        pass

    # Telefone (embutido no data-item-id: "phone:tel:+55...")
    telefone = None
    try:
        btn_tel = driver.find_element(By.CSS_SELECTOR, 'button[data-item-id^="phone:tel:"]')
        raw = (btn_tel.get_attribute("data-item-id") or "").replace("phone:tel:", "").strip()
        telefone = _formatar_tel(raw)
    except NoSuchElementException:
        pass

    # Email (aparece em alguns perfis do Google Business)
    email = None
    try:
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href^="mailto:"]')
        if links:
            email = links[0].get_attribute("href").replace("mailto:", "").strip()
    except Exception:
        pass

    # Site
    tem_site = False
    site_url  = None
    try:
        link = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]')
        site_url  = link.get_attribute("href") or None
        tem_site  = bool(site_url)
    except NoSuchElementException:
        pass

    # Categoria/descrição do Google Maps
    descricao_google = None
    for sel in ["button.DkEaL", ".DkEaL", "button[jsaction*='category']", "span.mgr77e"]:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            txt = el.text.strip()
            if txt:
                descricao_google = txt
                break
        except Exception:
            pass

    # Nota (estrelas)
    nota = None
    try:
        # aria-label="4,8 estrelas" ou "4.8 stars"
        for sel in ['span[aria-label*="estrela"]', 'span[aria-label*="star"]',
                    'div[aria-label*="estrela"]', 'span.MW4etd', 'span.ceNzKf']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                label = el.get_attribute("aria-label") or el.text or ""
                m = re.search(r'(\d)[,\.](\d)', label)
                if m:
                    nota = float(f"{m.group(1)}.{m.group(2)}")
                    break
                m2 = re.search(r'(\d+[,\.]\d+)', label)
                if m2:
                    nota = float(m2.group(1).replace(',', '.'))
                    break
            except Exception:
                pass
    except Exception:
        pass

    # Avaliações (número de reviews)
    avaliacoes = None
    try:
        for sel in ['span[aria-label*="avalia"]', 'button[aria-label*="avalia"]',
                    'span.UY7F9', 'span.e4rVHe']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                label = el.get_attribute("aria-label") or el.text or ""
                m = re.search(r'(\d[\d\.]+)', label.replace('.', ''))
                if m:
                    avaliacoes = int(m.group(1))
                    break
            except Exception:
                pass
    except Exception:
        pass

    return {
        "nome":             nome,
        "telefone":         telefone,
        "endereco":         endereco or "",
        "email":            email,
        "tem_site":         tem_site,
        "site_url":         site_url or "",
        "descricao_google": descricao_google,
        "nota":             nota,
        "avaliacoes":       avaliacoes,
    }


def _primeiro_texto(driver, seletores):
    for sel in seletores:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            txt = el.text.strip()
            if txt:
                return txt
        except Exception:
            pass
    return None


def _primeiro_texto_em(pai, seletores):
    for sel in seletores:
        try:
            el = pai.find_element(By.CSS_SELECTOR, sel)
            txt = el.text.strip()
            if txt:
                return txt
        except Exception:
            pass
    return None


def _formatar_tel(raw):
    if not raw:
        return None
    if raw.startswith("+"):
        digitos = "+" + re.sub(r"\D", "", raw)
        return digitos if len(digitos) >= 12 else None
    digitos = re.sub(r"\D", "", raw)
    if len(digitos) < 10:
        return None
    if digitos.startswith("55") and len(digitos) >= 12:
        return f"+{digitos}"
    return f"+55{digitos}"


def _calcular_score(emp, categoria=""):
    """
    Score de 0-100 indicando potencial de prospecção.
    Maior = mais oportunidade.
    """
    score = 0

    # Principal: não tem site
    if not emp.get("tem_site"):
        score += 40
    else:
        score -= 15

    # Tem telefone celular (13 dígitos com +55)
    tel = "".join(filter(str.isdigit, emp.get("telefone") or ""))
    if len(tel) == 13:      # +55 + 11 dígitos (celular)
        score += 15
    elif len(tel) == 12:    # +55 + 10 dígitos (fixo)
        score += 5

    # Não tem email — menos presença digital
    if not emp.get("email"):
        score += 10

    # Categoria de alto valor
    cat_lower = categoria.lower()
    for cat_av in CONFIG.get("categorias_alto_valor", []):
        if cat_av in cat_lower or cat_av in emp.get("nome", "").lower():
            score += 20
            break

    return max(0, min(100, score))
