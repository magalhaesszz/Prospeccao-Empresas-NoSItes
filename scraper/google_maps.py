"""
Scraping do Google Maps via Selenium / undetected-chromedriver.
Extrai nome, telefone, endereço, site e calcula score de oportunidade.
Inclui retry automático e múltiplos seletores CSS como fallback.
"""
import os, sys, time, logging, re, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
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
        # Reduz uso de memória — evita "tab crashed" (renderer OOM) no Railway.
        "--single-process", "--no-zygote",
        "--disable-dev-tools", "--disable-application-cache",
        "--disable-background-networking", "--disable-default-apps",
        "--disable-sync", "--memory-pressure-off",
        "--js-flags=--max-old-space-size=256",
        "--blink-settings=imagesEnabled=false",
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

def _driver_morto(exc):
    """True se a exceção indica que o Chrome/aba morreu e o driver ficou inutilizável."""
    s = str(exc).lower()
    return any(k in s for k in (
        "tab crashed", "target crashed", "session deleted", "invalid session id",
        "disconnected", "not connected to devtools", "chrome not reachable",
        "no such window", "web view not found", "unable to receive message from renderer",
    ))


def _fechar_consentimento(driver):
    """Google Maps headless às vezes abre um muro de consentimento de cookies
    que impede o feed de carregar. Tenta aceitar/fechar para liberar os resultados."""
    textos = ("aceitar tudo", "aceito tudo", "accept all", "concordo",
              "i agree", "aceitar", "reject all", "rejeitar tudo")
    try:
        botoes = driver.find_elements(By.CSS_SELECTOR, "button, form [role='button'], div[role='button']")
        for b in botoes:
            try:
                t = (b.text or b.get_attribute("aria-label") or "").strip().lower()
                if t and any(x in t for x in textos):
                    b.click()
                    logger.info("Consentimento fechado (botão '%s').", t[:30])
                    time.sleep(2)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def buscar_empresas(cidade, categoria, callback_progresso=None, limite=None, stats=None):
    """
    Ponto de entrada público.
    Usa estratégia em 2 fases:
      Fase 1 — coleta URLs de todos os cards SEM clicar (lê atributos DOM)
      Fase 2 — navega diretamente a cada URL com driver.get() e extrai dados reais
    Isso evita o bug onde click no headless Railway não muda a URL e o scraper
    lê dados genéricos ("Results") da página de busca.
    stats: dict opcional preenchido com o funil (cards, urls, extraidas, etc.).
    """
    driver = None
    empresas = []
    if stats is None:
        stats = {}

    try:
        logger.info("Buscando '%s' em '%s'", categoria, cidade)
        driver = criar_driver()

        # Planta o cookie de consentimento ANTES de abrir o Maps — pula o muro de
        # cookies do Google (que em servidor/headless trunca os resultados a poucos).
        try:
            driver.get("https://www.google.com/")
            time.sleep(1)
            for dom in (".google.com", ".google.com.br"):
                try:
                    driver.add_cookie({
                        "name": "CONSENT",
                        "value": "YES+cb.20210328-17-p0.en+FX+000",
                        "domain": dom,
                    })
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Não consegui plantar cookie de consentimento: %s", e)

        query = f"{categoria} em {cidade}"
        # hl/gl força PT-BR e resultados do Brasil (evita layout reduzido).
        driver.get("https://www.google.com/maps/search/" + query.replace(" ", "+") + "?hl=pt-BR&gl=BR")
        time.sleep(3)

        # Rede de segurança: se ainda houver muro visível, tenta clicar/aceitar.
        _fechar_consentimento(driver)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
            )
        except TimeoutException:
            logger.warning("Feed demorou — continuando.")

        max_itens = limite or CONFIG["max_resultados"]
        cards_final = _rolar_feed(driver, max_itens)

        # ── Fase 1: coleta URLs e nomes do feed sem clicar ────────────────────
        itens_feed = _coletar_itens_feed(driver)
        logger.info("Fase 1 concluída: %d places coletados.", len(itens_feed))

        # ── Fase 2: navega direto a cada URL e extrai dados reais ─────────────
        telefones_vistos = set()
        places_vistos = set()
        fingerprints_vistos = set()
        total_urls = len(itens_feed)
        n_none = 0
        n_dedup = 0
        logger.info("Fase 2: processando até %d URLs para obter %d empresas.", total_urls, max_itens)

        PLACES_POR_DRIVER = 6  # recicla o Chrome a cada N páginas (evita crash de memória)
        desde_reinicio = 0

        for i, item in enumerate(itens_feed):
            if len(empresas) >= max_itens:
                break

            # Reciclagem proativa: fecha e reabre o Chrome antes de acumular memória.
            if desde_reinicio >= PLACES_POR_DRIVER:
                logger.info("Reciclando Chrome após %d páginas.", desde_reinicio)
                try: driver.quit()
                except Exception: pass
                driver = criar_driver()
                desde_reinicio = 0

            emp = None
            for tentativa in range(2):
                try:
                    emp = _extrair_de_url(driver, item["url"], item["nome_hint"])
                    break
                except Exception as exc:
                    if _driver_morto(exc) and tentativa == 0:
                        logger.warning("[%d/%d] aba crashou — recriando Chrome e tentando de novo.", i + 1, total_urls)
                        try: driver.quit()
                        except Exception: pass
                        driver = criar_driver()
                        desde_reinicio = 0
                        continue
                    logger.error("Erro item %d (%s): %s", i, item.get("url", "?")[:60], exc)
                    break
            desde_reinicio += 1

            if not emp:
                n_none += 1
                logger.warning("[%d/%d] extração retornou None — URL ignorada.", i + 1, total_urls)
                continue
            emp["score"] = _calcular_score(emp, categoria)
            tel = emp.get("telefone")
            maps_key = (emp.get("maps_url") or "").split("?", 1)[0].rstrip("/").lower()
            fp_nome = re.sub(r"\W+", "", (emp.get("nome") or "").lower(), flags=re.UNICODE)
            fp_end = re.sub(r"\W+", "", (emp.get("endereco") or "").lower(), flags=re.UNICODE)
            fingerprint = f"{fp_nome}|{fp_end}" if fp_nome and fp_end else ""

            duplicada = (
                (tel and tel in telefones_vistos)
                or (maps_key and maps_key in places_vistos)
                or (fingerprint and fingerprint in fingerprints_vistos)
            )
            if duplicada:
                n_dedup += 1
                logger.info("[%d/%d] %s — place duplicado, ignorado.", i + 1, total_urls, emp["nome"])
                continue
            if tel:
                telefones_vistos.add(tel)
            if maps_key:
                places_vistos.add(maps_key)
            if fingerprint:
                fingerprints_vistos.add(fingerprint)
            empresas.append(emp)
            logger.info("[%d/%d] %s | Tel:%s Site:%s Score:%d",
                len(empresas), max_itens, emp["nome"],
                emp["telefone"] or "—",
                "S" if emp["tem_site"] else "N",
                emp["score"])
            if callback_progresso:
                callback_progresso({"atual": len(empresas), "total": max_itens, "empresa": emp["nome"]})

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

    stats.update({
        "pedidas":   (limite or CONFIG["max_resultados"]),
        "cards":     locals().get("cards_final", 0),
        "urls":      locals().get("total_urls", 0),
        "extraidas": len(empresas),
        "sem_dados": locals().get("n_none", 0),
        "dup_tel":   locals().get("n_dedup", 0),
    })
    logger.info("Funil: pedidas=%s cards=%s urls=%s extraidas=%s sem_dados=%s dup_tel=%s",
                stats["pedidas"], stats["cards"], stats["urls"],
                stats["extraidas"], stats["sem_dados"], stats["dup_tel"])
    return empresas


# ── Funções internas ──────────────────────────────────────────────────────────

_FIM_LISTA_SELETORES = [
    'div.lXJj5c', 'p.qjESne', 'div.HlvSq',
    'span.HlvSq', 'div[class*="noResults"]',
]
_FIM_LISTA_TEXTOS = [
    "fim dos resultados", "end of results",
    "você chegou ao fim", "you've reached the end",
    "didn't find what you're looking for",
    "não encontrou o que procurava",
]


def _fim_de_lista(driver):
    """Retorna True se Google Maps sinalizou que não há mais resultados.
    Só considera fim quando o TEXTO bate com um marcador conhecido — antes bastava
    ter qualquer texto no seletor, o que parava o scroll cedo (30 vinham 3)."""
    try:
        for sel in _FIM_LISTA_SELETORES:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                txt = (el.text or "").lower()
                if txt and any(m in txt for m in _FIM_LISTA_TEXTOS):
                    return True
    except Exception:
        pass
    try:
        body = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        txt = (body.text or "").lower()
        for marcador in _FIM_LISTA_TEXTOS:
            if marcador in txt:
                return True
    except Exception:
        pass
    return False


def _contar_cards(feed):
    """Conta cards do feed tentando seletor principal e fallback de links."""
    # Testa múltiplos seletores de card pois Google Maps muda classes com frequência
    for sel in ("div.Nv2PK", "div[role='article']", "div.UaQhfb"):
        cards = feed.find_elements(By.CSS_SELECTOR, sel)
        if cards:
            return len(cards), cards
    links = feed.find_elements(By.XPATH, ".//a[contains(@href,'/maps/place/')]")
    return len(links), links


def _rolar_feed(driver, max_itens):
    # 30 tentativas × 4s = 120s máximo sem novos cards — necessário em Railway (rede lenta).
    sem_mudanca = 0
    ultima = 0
    while sem_mudanca < 30:
        try:
            feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            n, elementos = _contar_cards(feed)
            if n >= max_itens:
                logger.info("Feed: atingiu %d/%d cards — parando scroll.", n, max_itens)
                break
            if _fim_de_lista(driver):
                logger.info("Feed: Google Maps sinalizou fim de lista com %d cards.", n)
                break
            if n == ultima:
                sem_mudanca += 1
            else:
                sem_mudanca = 0
                ultima = n
                logger.info("Feed: %d cards...", n)
            # Scroll triplo: scrollTop + scrollIntoView do último card
            # + JS dispara evento scroll manual para forçar lazy-load do Maps.
            driver.execute_script("arguments[0].scrollTop=arguments[0].scrollHeight", feed)
            if elementos:
                driver.execute_script("arguments[0].scrollIntoView(false)", elementos[-1])
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('scroll', {bubbles:true}))", feed
            )
            time.sleep(4)
        except NoSuchElementException:
            break
        except Exception as exc:
            logger.error("Erro rolagem: %s", exc)
            sem_mudanca += 1
    try:
        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        n, _ = _contar_cards(feed)
        logger.info("Feed final: %d cards após rolagem.", n)
        return n
    except Exception:
        return ultima


def _coletar_itens_feed(driver):
    """
    Fase 1 — lê o feed SEM clicar em nada.
    Estratégia 1: itera cards (múltiplos seletores) e pega link /maps/place/.
    Estratégia 2: varre todos os <a href*=/maps/place/> direto no feed (sempre roda, merge).
    """
    itens = []
    seen  = set()

    _CARD_SELETORES = ["div.Nv2PK", "div[role='article']", "div.UaQhfb"]

    try:
        feed = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')

        # Estratégia 1: itera cards por seletores conhecidos
        cards_encontrados = []
        for sel in _CARD_SELETORES:
            cards = feed.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                logger.info("Feed: %d cards (%s).", len(cards), sel)
                cards_encontrados = cards
                break

        if not cards_encontrados:
            logger.warning("Nenhum seletor de card encontrou resultados — usando só xpath.")

        for card in cards_encontrados:
            try:
                links = card.find_elements(By.CSS_SELECTOR, "a[href]")
                todos_labels = [
                    (link.get_attribute("aria-label") or "").strip()
                    for link in links
                ]
                for idx, link in enumerate(links):
                    href = link.get_attribute("href") or ""
                    if "/maps/place/" in href and href not in seen:
                        nome_hint = todos_labels[idx]
                        if not nome_hint:
                            nome_hint = next((l for l in todos_labels if l), "")
                        seen.add(href)
                        itens.append({"url": href, "nome_hint": nome_hint})
                        break
            except Exception:
                pass

        # Estratégia 2: sempre roda e complementa (merge via seen)
        links_xpath = feed.find_elements(By.XPATH, ".//a[contains(@href,'/maps/place/')]")
        adicionados = 0
        for link in links_xpath:
            try:
                href  = link.get_attribute("href") or ""
                label = (link.get_attribute("aria-label") or "").strip()
                if href and href not in seen:
                    seen.add(href)
                    itens.append({"url": href, "nome_hint": label})
                    adicionados += 1
            except Exception:
                pass
        if adicionados:
            logger.info("Estratégia 2 (xpath links) adicionou %d extras.", adicionados)

    except Exception as exc:
        logger.error("Erro ao coletar feed: %s", exc)

    logger.info("Fase 1: %d URLs coletadas.", len(itens))
    return itens


_NOMES_INVALIDOS = {"results", "google maps", "google", ""}

# Domínios que NÃO são sites próprios — redes sociais / encurtadores
_REDES_SOCIAIS = {
    "instagram.com", "facebook.com", "fb.com",
    "twitter.com", "x.com",
    "tiktok.com", "linkedin.com",
    "youtube.com", "youtu.be",
    "wa.me", "whatsapp.com",
    "linktr.ee", "linktree.com",
}


def _extrair_de_url(driver, maps_url, nome_hint=""):
    """
    Fase 2 — navega diretamente à URL do place com driver.get() e extrai dados.
    Não depende de click → animação → mudança de URL (que falha no headless Railway).
    """
    driver.get(maps_url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except TimeoutException:
        logger.warning("h1 não carregou em 20s para %s", maps_url[:80])
    time.sleep(2)

    # Nome — valida para não aceitar título genérico da página
    nome = _primeiro_texto(driver, ["h1.DUwDvf", "h1[jsan]", "h1"])
    if not nome or nome.strip().lower() in _NOMES_INVALIDOS:
        nome = nome_hint
    if not nome:
        logger.warning("Nome inválido, URL descartada: %s", maps_url[:80])
        return None

    # Endereço
    endereco = None
    try:
        btn = driver.find_element(By.CSS_SELECTOR, 'button[data-item-id="address"]')
        endereco = _primeiro_texto_em(btn, [".Io6YTe", "div", "span"])
    except NoSuchElementException:
        pass

    # Telefone
    telefone = None
    try:
        btn_tel = driver.find_element(By.CSS_SELECTOR, 'button[data-item-id^="phone:tel:"]')
        raw     = (btn_tel.get_attribute("data-item-id") or "").replace("phone:tel:", "").strip()
        telefone = _formatar_tel(raw)
    except NoSuchElementException:
        pass

    # Email
    email = None
    try:
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href^="mailto:"]')
        if links:
            email = links[0].get_attribute("href").replace("mailto:", "").strip()
    except Exception:
        pass

    # Site — ignora redes sociais (Instagram, Facebook etc. não são site próprio)
    tem_site = False
    site_url  = None
    try:
        link     = driver.find_element(By.CSS_SELECTOR, 'a[data-item-id="authority"]')
        raw_url  = link.get_attribute("href") or None
        if raw_url and not any(rede in raw_url.lower() for rede in _REDES_SOCIAIS):
            site_url = raw_url
            tem_site = True
    except NoSuchElementException:
        pass

    # Categoria
    descricao_google = None
    for sel in ["button.DkEaL", ".DkEaL", "button[jsaction*='category']", "span.mgr77e"]:
        try:
            el  = driver.find_element(By.CSS_SELECTOR, sel)
            txt = el.text.strip()
            if txt:
                descricao_google = txt
                break
        except Exception:
            pass

    # Nota
    nota = None
    for sel in ['span[aria-label*="estrela"]', 'span[aria-label*="star"]',
                'div[aria-label*="estrela"]', 'span.MW4etd', 'span.ceNzKf']:
        try:
            el    = driver.find_element(By.CSS_SELECTOR, sel)
            label = el.get_attribute("aria-label") or el.text or ""
            m     = re.search(r'(\d)[,\.](\d)', label)
            if m:
                nota = float(f"{m.group(1)}.{m.group(2)}")
                break
            m2 = re.search(r'(\d+[,\.]\d+)', label)
            if m2:
                nota = float(m2.group(1).replace(',', '.'))
                break
        except Exception:
            pass

    # Avaliações — 4 estratégias para cobrir variações do Google Maps
    avaliacoes = None

    # 1) aria-label com "avalia" ou "review"
    for sel in ['span[aria-label*="avalia"]', 'button[aria-label*="avalia"]',
                'span[aria-label*="review"]', 'button[aria-label*="review"]']:
        try:
            el    = driver.find_element(By.CSS_SELECTOR, sel)
            label = el.get_attribute("aria-label") or el.text or ""
            m     = re.search(r'(\d[\d\.,]*)', label)
            if m:
                avaliacoes = int(m.group(1).replace('.', '').replace(',', ''))
                break
        except Exception:
            pass

    # 2) classes conhecidas — conteúdo textual direto
    if avaliacoes is None:
        for sel in ['span.UY7F9', 'span.e4rVHe']:
            try:
                el  = driver.find_element(By.CSS_SELECTOR, sel)
                txt = re.sub(r'[^\d]', '', el.text or "")
                if txt:
                    avaliacoes = int(txt)
                    break
            except Exception:
                pass

    # 3) XPath — span com texto no formato "(47)"
    if avaliacoes is None:
        try:
            els = driver.find_elements(
                By.XPATH,
                "//span[contains(text(),'(') and contains(text(),')')]"
            )
            for el in els:
                txt = re.sub(r'[^\d]', '', el.text or "")
                if txt:
                    n = int(txt)
                    if 1 <= n <= 999999:
                        avaliacoes = n
                        break
        except Exception:
            pass

    # 4) regex no source HTML da área de rating
    if avaliacoes is None:
        try:
            area = driver.find_element(By.CSS_SELECTOR,
                'div.F7nice, div[jsaction*="rating"], div[aria-label*="avalia"]')
            src = area.get_attribute("innerHTML") or ""
            m = re.search(r'(\d[\d\.]*)\s*(?:avalia|review)', src, re.IGNORECASE)
            if m:
                avaliacoes = int(m.group(1).replace('.', ''))
        except Exception:
            pass

    # Foto principal
    foto_url = ""
    for sel in ['img.aoRNLd', 'div.RZ66Rb img', 'button.aoRNLd',
                'img[decoding="async"][src*="googleusercontent"]']:
        try:
            el  = driver.find_element(By.CSS_SELECTOR, sel)
            src = el.get_attribute("src") or el.get_attribute("data-src") or ""
            if src and ("googleusercontent" in src or "ggpht" in src):
                foto_url = src
                break
        except Exception:
            pass

    # Múltiplas fotos
    fotos_lista = []
    try:
        imgs   = driver.find_elements(By.CSS_SELECTOR,
                     'img[src*="googleusercontent"], img[src*="ggpht"]')
        seen_f = set()
        if foto_url:
            seen_f.add(foto_url)
            fotos_lista.append(foto_url)
        for el in imgs:
            src = el.get_attribute("src") or ""
            if src and src not in seen_f and len(fotos_lista) < 6:
                seen_f.add(src)
                fotos_lista.append(src)
    except Exception:
        if foto_url:
            fotos_lista = [foto_url]

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
        "maps_url":         (maps_url or "").split("?", 1)[0].rstrip("/"),  # canônica para dedupe
        "foto_url":         foto_url,
        "fotos_urls":       json.dumps(fotos_lista),
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
    raw = str(raw).strip()
    # Normalização E164 via phonenumbers (mesma regra do banco) — dedup consistente
    try:
        import phonenumbers
        num = phonenumbers.parse(raw, "BR")
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    # Fallback: só dígitos
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
