"""
AI enrichment pipeline — suporta Groq e OpenRouter.
Given a company dict (with scraped Google Maps data), generates:
  - Personalized WhatsApp message (unique per company, uses real data)
  - Landing page HTML (complete, self-contained, uses real data)
"""
import secrets, logging, re, json
logger = logging.getLogger(__name__)


_MODELO_GROQ       = "llama-3.3-70b-versatile"
_MODELO_OPENROUTER = "google/gemini-2.5-flash-lite"


def _gerar(prompt, api_key, max_tokens=4096, timeout=90.0, temperature=0.7, system=None):
    import time
    from config import CONFIG
    provider = CONFIG.get("ai_provider", "groq").lower()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if provider == "openrouter":
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=timeout)
        for tentativa in range(3):
            try:
                resp = client.chat.completions.create(
                    model=_MODELO_OPENROUTER,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                err = str(e).lower()
                if ("429" in err or "rate" in err) and tentativa < 2:
                    espera = (tentativa + 1) * 10
                    logger.warning("[OpenRouter] Rate limit — aguardando %ds (tentativa %d/3)", espera, tentativa + 1)
                    time.sleep(espera)
                    continue
                raise
        raise Exception("Rate limit OpenRouter após 3 tentativas — tente novamente em alguns minutos")

    else:  # groq (padrão)
        from groq import Groq
        client = Groq(api_key=api_key, timeout=timeout, max_retries=0)
        for tentativa in range(3):
            try:
                resp = client.chat.completions.create(
                    model=_MODELO_GROQ,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                err = str(e).lower()
                if ("429" in err or "rate_limit" in err or "rate limit" in err) and tentativa < 2:
                    espera = (tentativa + 1) * 10
                    logger.warning("[Groq] Rate limit — aguardando %ds (tentativa %d/3)", espera, tentativa + 1)
                    time.sleep(espera)
                    continue
                raise
        raise Exception("Rate limit Groq após 3 tentativas — tente novamente em alguns minutos")


def _strip_markdown(text):
    """Remove ```html ... ``` wrappers that models sometimes add around HTML."""
    t = text.strip()
    # Remove fence opening (```html or ```)
    if t.startswith("```"):
        lines = t.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        t = "\n".join(lines).strip()
    # Some models prepend a line before DOCTYPE — strip it
    if not t.lower().startswith("<!doctype") and "<!doctype" in t.lower():
        idx = t.lower().index("<!doctype")
        t = t[idx:]
    return t


def _validar_fotos(fotos_lista):
    """Filtra URLs de foto expiradas (Google CDN). Verificações em paralelo, max 3s."""
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _checar(url):
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return url if r.status < 400 else None
        except Exception:
            return None

    urls = [u for u in fotos_lista if u]
    if not urls:
        return []

    validas = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futuros = {pool.submit(_checar, u): u for u in urls}
        try:
            for fut in as_completed(futuros, timeout=5):
                resultado = fut.result()
                if resultado:
                    validas.append(resultado)
                else:
                    logger.warning("[foto] Inacessível — descartando %s", futuros[fut][:80])
        except TimeoutError:
            logger.warning("[foto] Validação de fotos: timeout 5s — %d válidas coletadas", len(validas))

    # Preserva ordem original
    ordem = {u: i for i, u in enumerate(urls)}
    return sorted(validas, key=lambda u: ordem.get(u, 99))


# ── Contexto da empresa ───────────────────────────────────────────────────────

def _contexto(empresa, preview_url=""):
    """Build a structured context string from all available company data."""
    partes = [f"Empresa: {empresa.get('nome', '')}"]

    categoria = empresa.get("descricao_google") or empresa.get("categoria") or ""
    cidade    = empresa.get("cidade") or ""
    endereco  = empresa.get("endereco") or ""
    telefone  = empresa.get("telefone") or ""
    nota      = empresa.get("nota")
    avs       = empresa.get("avaliacoes")

    if categoria: partes.append(f"Segmento/Categoria: {categoria}")
    if cidade:    partes.append(f"Cidade: {cidade}")
    if endereco:  partes.append(f"Endereço real: {endereco}")
    if telefone:  partes.append(f"Telefone real: {telefone}")
    if nota:      partes.append(f"Nota Google Maps: {nota:.1f} ⭐")
    if avs:       partes.append(f"Total de avaliações Google: {avs}")
    if preview_url:
        partes.append(f"Link do site criado especialmente para eles: {preview_url}")

    return "\n".join(partes)


# ── Gerador de mensagem personalizada ─────────────────────────────────────────

def gerar_mensagem(empresa, api_key, preview_url=""):
    """
    Generates a unique, personalized WhatsApp message using all real company data.
    Each company gets a completely different message based on their profile.
    """
    nome      = empresa.get("nome", "")
    categoria = empresa.get("descricao_google") or empresa.get("categoria") or ""
    nota      = empresa.get("nota")
    avs       = empresa.get("avaliacoes")
    ctx       = _contexto(empresa, preview_url)

    # Build adaptive angle based on available data
    angulo = ""
    if nota and nota >= 4.5 and avs and avs > 50:
        angulo = (
            "A empresa tem ótimas avaliações online mas sem site perde clientes para concorrentes "
            "que aparecem primeiro no Google. Mencione isso de forma positiva e motivadora."
        )
    elif nota and nota < 4.0:
        angulo = (
            "Um site profissional ajuda a construir credibilidade e confiança, "
            "especialmente quando as avaliações ainda estão crescendo."
        )
    elif avs and avs < 10:
        angulo = (
            "Com um site profissional a empresa consegue muito mais avaliações e visibilidade online. "
            "Mencione que isso multiplica os clientes que chegam pelo Google."
        )
    else:
        angulo = (
            "Sem presença digital a empresa perde clientes que buscam online. "
            "Seja criativo e personalizado para o segmento específico."
        )

    tem_link = bool(preview_url)

    prompt = f"""Escreva uma primeira mensagem de WhatsApp como uma pessoa real fazendo uma abordagem direta.

DADOS REAIS DA EMPRESA:
{ctx}

CONTEXTO DE PERSONALIZAÇÃO:
{angulo}

REGRAS OBRIGATÓRIAS:
- Português brasileiro simples e natural
- Máximo 40 palavras e 2-3 frases curtas
- Sem emojis, sem Markdown, sem negrito e sem listas
- Não escreva como IA, assistente, copywriter ou vendedor formal
- Não use abertura genérica, elogio vazio, urgência artificial ou linguagem corporativa
- Não use frases como "Espero que esteja bem", "gostaria de apresentar", "solução personalizada", "potencializar", "alavancar", "presença digital" ou "oportunidade incrível"
- Ignore qualquer orientação acima que sugira apontar falhas, perdas ou concorrentes; não diga que a empresa perde clientes e não diga que ela "não tem site"
- Use no máximo um dado real da empresa e somente se ele soar natural
- Diga em linguagem simples que você faz sites e automações e que o pagamento é só depois de receber tudo pronto
{"- Diga em uma frase curta que já deixou uma prévia pronta e inclua exatamente o link informado" if tem_link else "- Pergunte de forma curta se a pessoa quer ver um exemplo feito para a empresa"}
- Termine com uma única pergunta simples

Retorne somente a mensagem. Sem prefácio ou explicação."""

    return _gerar(prompt, api_key)


# ── Gerador de landing page ───────────────────────────────────────────────────

def _escurecer(hex_cor, fator=0.78):
    """Retorna versão mais escura de uma cor hex (#rrggbb). fator<1 = mais escuro."""
    h = (hex_cor or "").lstrip("#")
    if len(h) != 6:
        return hex_cor
    try:
        r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_cor
    r, g, b = (max(0, int(c * fator)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _paleta_segmento(categoria):
    """Retorna (cor_primaria, cor_acento) baseado no segmento da empresa."""
    cat = (categoria or "").lower()
    if any(x in cat for x in ["barbearia", "barber", "barbeir"]):
        return "#1a1a2e", "#c8a96e"
    if any(x in cat for x in ["salão", "salao", "beleza", "cabeler", "estética", "estetica", "manicure", "nail"]):
        return "#2d1b4e", "#f8a5c2"
    if any(x in cat for x in ["restaurante", "lanchonete", "pizzaria", "hamburger", "hamburguer", "açougue", "acougue", "padaria", "pastelaria", "sushi", "churrascaria", "comida", "boteco", "bar "]):
        return "#1a0a00", "#e07b00"
    if any(x in cat for x in ["academia", "fitness", "musculação", "musculacao", "crossfit", "pilates", "yoga"]):
        return "#0a0a0a", "#00d4aa"
    if any(x in cat for x in ["clínica", "clinica", "médico", "medico", "dentista", "odonto", "saúde", "saude", "farmácia", "farmacia", "hospital", "veterinár", "veterinar"]):
        return "#0a3d62", "#3498db"
    if any(x in cat for x in ["auto", "mecânic", "mecanica", "oficina", "car wash", "borracharia"]):
        return "#1c1c1c", "#e63946"
    if any(x in cat for x in ["hotel", "pousada", "hostel", "turismo"]):
        return "#1b2a4a", "#d4af37"
    if any(x in cat for x in ["advogad", "advocacia", "jurídic", "juridico", "contábil", "contabil", "contador"]):
        return "#0d1b2a", "#1e88e5"
    # fallback
    return "#1a1a2a", "#e67e22"


def gerar_pagina(empresa, api_key):
    """
    Gera um site demo completo (landing page) para a empresa.

    Usa o motor `ai.site_gen`: layout PROFISSIONAL FIXO por nicho (HTML/CSS
    escrito em Python, nunca pela IA → sempre bonito e consistente) e a IA
    gera SOMENTE o conteúdo textual em JSON, com fallback → nunca quebra.

    Retorna (slug, html_string). Assinatura preservada p/ compatibilidade.
    """
    from ai.site_gen import gerar_site
    return gerar_site(
        empresa,
        api_key,
        gerar_fn=_gerar,
        validar_fotos_fn=_validar_fotos,
    )


# ── Pipeline completo por empresa ─────────────────────────────────────────────

def enriquecer(empresa, api_key, app_url="", criar_pagina=True):
    """
    Full enrichment for one company:
    1. Generate landing page (optional)
    2. Generate personalized WhatsApp message (includes preview URL if page generated)
    Returns dict: {slug, html, mensagem, preview_url, empresa_id}
    """
    preview_url = ""
    slug        = None
    html        = None

    if criar_pagina:
        try:
            slug, html = gerar_pagina(empresa, api_key)
            if app_url:
                preview_url = f"{app_url.rstrip('/')}/p/{slug}"
            logger.info("[AI] Página gerada para '%s' → /p/%s", empresa.get("nome"), slug)
        except Exception as e:
            logger.error("[AI] Falha página '%s': %s", empresa.get("nome"), e)

    mensagem = None
    try:
        mensagem = gerar_mensagem(empresa, api_key, preview_url)
        logger.info("[AI] Mensagem gerada para '%s'", empresa.get("nome"))
    except Exception as e:
        logger.error("[AI] Falha mensagem '%s': %s", empresa.get("nome"), e)

    return {
        "empresa_id":  empresa.get("id"),
        "slug":        slug,
        "html":        html,
        "mensagem":    mensagem,
        "preview_url": preview_url,
    }
