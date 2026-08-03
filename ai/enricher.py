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

    prompt = f"""Você é especialista em vendas consultivas B2B via WhatsApp com taxa de conversão muito alta.
Crie uma mensagem de prospecção ÚNICA e completamente PERSONALIZADA. Não seja genérico.

DADOS REAIS DA EMPRESA:
{ctx}

ÂNGULO DE ABORDAGEM (baseado no perfil desta empresa específica):
{angulo}

REGRAS OBRIGATÓRIAS:
- Português brasileiro, tom amigável e natural — não corporativo
- MÁXIMO 170 palavras — direto ao ponto
- Use os dados reais (nota, avaliações, segmento, cidade) de forma natural e específica
- A empresa não tem site — mencione isso como oportunidade, não como crítica
- Proposta de valor: site profissional + automação de processos → cobra APENAS após entrega
{"- Mencione naturalmente que você JÁ criou uma prévia do site para eles e compartilhe o link" if tem_link else ""}
- Formatação WhatsApp: *negrito* para 1-2 pontos chave apenas
- Máximo 2 emojis, estratégicos e relevantes ao segmento
- Termine com UMA pergunta simples que incentiva resposta

Retorne APENAS a mensagem. Zero prefácio ou explicação."""

    return _gerar(prompt, api_key)


# ── Gerador de landing page ───────────────────────────────────────────────────

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
        return "#f0f8ff", "#0066cc"
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
    Generates a complete, self-contained HTML landing page using all real company data.
    Returns (slug, html_string).
    """
    nome      = empresa.get("nome", "")
    categoria = empresa.get("descricao_google") or empresa.get("categoria") or "Negócio Local"
    cidade    = empresa.get("cidade") or ""
    endereco  = empresa.get("endereco") or ""
    telefone  = empresa.get("telefone") or ""
    nota      = empresa.get("nota")
    avs       = empresa.get("avaliacoes")
    foto_url  = empresa.get("foto_url") or ""
    maps_url  = empresa.get("maps_url") or ""

    # Normaliza telefone
    tel_digits = "".join(d for d in (telefone or "") if d.isdigit())
    wa_number  = f"55{tel_digits}" if tel_digits and not tel_digits.startswith("55") else tel_digits
    wa_link    = f"https://wa.me/{wa_number}" if wa_number else "https://wa.me/"
    tel_link   = f"tel:+{wa_number}" if wa_number else "#"

    cor_primaria, cor_acento = _paleta_segmento(categoria)

    # Monta lista de fotos reais (até 6)
    fotos_raw = empresa.get("fotos_urls") or "[]"
    try:
        fotos_lista = json.loads(fotos_raw) if isinstance(fotos_raw, str) else []
    except Exception:
        fotos_lista = []
    if foto_url and foto_url not in fotos_lista:
        fotos_lista.insert(0, foto_url)
    fotos_lista = [f for f in fotos_lista if f][:6]
    fotos_lista = _validar_fotos(fotos_lista)

    # Preenche até 6 slots (vazio = sem foto)
    fotos_pad = (fotos_lista + [""] * 6)[:6]
    foto_1, foto_2, foto_3, foto_4, foto_5, foto_6 = fotos_pad

    # Hero: URL da primeira foto ou vazio (modelo gera fallback com gradiente)
    hero_img = fotos_lista[0] if fotos_lista else ""

    nota_fmt       = f"{nota:.1f}" if nota else "5.0"
    total_avaliacoes = str(avs) if avs else "0"

    # Instrução de galeria
    if fotos_lista:
        aviso_fotos = f"ATENÇÃO: Use APENAS estas URLs de imagem reais: {', '.join(f for f in fotos_lista if f)}. NÃO invente outras URLs."
    else:
        aviso_fotos = "Não há fotos reais disponíveis. NÃO use imagens placeholder, picsum, unsplash ou via.placeholder. Seção galeria deve exibir mensagem 'Fotos em breve'."

    system_msg = (
        "Você é um Desenvolvedor Front-end Sênior e Copywriter de Conversão especializado em "
        "landing pages de alta conversão para negócios locais brasileiros. "
        "Você produz HTML5 impecável, autocontido, mobile-first, sem dependências externas. "
        "Siga todas as instruções com precisão absoluta. Retorne SOMENTE o código HTML — "
        "sem texto, sem comentários, sem blocos markdown fora do HTML."
    )

    prompt = f"""Gere um arquivo HTML único, completo e de altíssima qualidade para uma landing page comercial de alta conversão.

=== DADOS DO CLIENTE ===
Nome da Empresa: {nome}
Segmento/Categoria: {categoria}
Localização: {cidade}
Endereço Completo: {endereco}
Telefone: {telefone}
Nota do Google: {nota_fmt} de 5.0
Total de Avaliações: {total_avaliacoes}

=== VARIÁVEIS DE INTEGRAÇÃO ===
Link WhatsApp: {wa_link}
Link Telefone: {tel_link}
Link Google Maps: {maps_url or "#"}

=== DESIGN SYSTEM & RECURSOS VISUAIS ===
Cor Primária: {cor_primaria}
Cor de Destaque (Acento): {cor_acento}
Imagem Principal (Hero URL): {hero_img or "nenhuma — use gradiente com cor primária"}
Foto 1: {foto_1 or "indisponível"}
Foto 2: {foto_2 or "indisponível"}
Foto 3: {foto_3 or "indisponível"}
Foto 4: {foto_4 or "indisponível"}
Foto 5: {foto_5 or "indisponível"}
Foto 6: {foto_6 or "indisponível"}
{aviso_fotos}

=== REGRAS DE CÓDIGO E DESIGN (OBRIGATÓRIO) ===
1. ARQUITETURA AUTOCONTIDA: Código 100% em único arquivo. CSS dentro de <style> no <head>. JavaScript mínimo (menu mobile + smooth scroll) antes do </body>.
2. ZERO DEPENDÊNCIAS: Proibido Bootstrap, Tailwind, jQuery, Google Fonts, CDNs. Use font-family: system-ui, -apple-system, sans-serif e ícones SVG inline.
3. CSS VARIABLES: Use :root com --cor-primaria: {cor_primaria}; --cor-acento: {cor_acento}; aplique via var(). Mobile-first com @media (min-width: 768px) para desktop. Flexbox/Grid moderno.
4. IMAGENS: Use APENAS as URLs fornecidas acima. Fotos marcadas como "indisponível" NÃO devem aparecer no HTML. object-fit: cover em todas as imagens. Alt text descritivo focado em {categoria}.
5. COPYWRITING: Proibido Lorem Ipsum. Textos persuasivos, criativos e específicos para {categoria} em {cidade}.

=== ESTRUTURA OBRIGATÓRIA (9 seções, nesta ordem exata) ===

1. HEADER/NAV (sticky, top:0, z-index:1000, background: var(--cor-primaria), color:#fff)
   - Esquerda: {nome} em negrito
   - Centro: links âncora Início · Serviços · Sobre · Contato (hidden em mobile)
   - Direita: botão WhatsApp (background: var(--cor-acento)) → {wa_link}
   - Ícone hamburger (☰) mobile que abre menu vertical

2. HERO SECTION (min-height:85vh, display:flex, align-items:center, text-align:center)
   - Background: se hero URL disponível → background-image com overlay rgba(0,0,0,0.55); senão gradiente com var(--cor-primaria)
   - H1 impactante focado na dor do cliente (font-size: clamp(2rem,5vw,3.5rem); font-weight:800; color:#fff)
   - Subtítulo: {categoria} em {cidade}
   - 2 CTAs: "📱 Agendar pelo WhatsApp" (var(--cor-acento)) e "↓ Nossos Serviços" (outline branco)

3. SERVIÇOS (id="servicos", background:#fff, padding:80px 20px)
   - 4 a 6 cards em CSS Grid (repeat(auto-fit, minmax(220px,1fr)))
   - Cada card: SVG ícone inline, h3 do serviço, parágrafo descritivo
   - Serviços REAIS e específicos para {categoria} — zero genérico

4. DIFERENCIAIS (id="diferenciais", background: var(--cor-primaria) com 5% opacidade)
   - 3 diferenciais em flexbox, específicos para {categoria} em {cidade}
   - Cada um com SVG ícone inline, título e texto

5. PROVA SOCIAL — GOOGLE BADGE (background destacado com borda var(--cor-acento))
   - Nota {nota_fmt} em destaque grande
   - {total_avaliacoes} avaliações reais
   - Estrelas em SVG inline (cor: var(--cor-acento))
   - Link → {maps_url or "#"}

6. GALERIA DE FOTOS (id="galeria", CSS Grid 3 colunas desktop / 2 mobile)
   - Use APENAS as fotos marcadas como disponíveis acima
   - object-fit:cover; height:220px; border-radius:10px

7. SOBRE NÓS (id="sobre", grid 2 colunas desktop)
   - Texto humanizado (mín. 80 palavras) posicionando {nome} como autoridade em {cidade}
   - Mencione o endereço: {endereco}
   - Coluna visual: foto disponível ou bloco de cor

8. DEPOIMENTOS (id="depoimentos", 3 cards em grid)
   - 3 avaliações simuladas realistas de clientes sobre {categoria}
   - Nomes brasileiros, estrelas ★★★★★ em var(--cor-acento), "Cliente desde 202X"

9. CONTATO & FOOTER (id="contato")
   - Endereço: {endereco}
   - Botão Ligar: {tel_link}
   - Botão WhatsApp: {wa_link}
   - Botão Google Maps: {maps_url or "#"}
   - Formulário visual (sem action): Nome, E-mail, Telefone, Mensagem, botão Enviar
   - Footer: © 2025 {nome} — {categoria} em {cidade}

EXTRA OBRIGATÓRIO: Botão flutuante WhatsApp (position:fixed; bottom:24px; right:24px; z-index:9999) círculo verde #25D366 com SVG branco → {wa_link}

=== SCHEMA.ORG (OBRIGATÓRIO — inserir no <head> antes de </head>) ===
Adicione este bloco JSON-LD exato, substituindo os valores pelos dados reais:
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "{nome}",
  "description": "{categoria} em {cidade}",
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": "{endereco}",
    "addressLocality": "{cidade}",
    "addressCountry": "BR"
  }},
  "telephone": "{telefone}",
  "url": "",
  "aggregateRating": {{
    "@type": "AggregateRating",
    "ratingValue": "{nota_fmt}",
    "reviewCount": "{total_avaliacoes}"
  }}
}}
</script>

=== FORMATO DE SAÍDA ===
Inicie com <!DOCTYPE html> e termine com </html>. Nada mais."""

    html = _strip_markdown(_gerar(
        prompt, api_key,
        max_tokens=8192,
        timeout=120.0,
        temperature=0.4,
        system=system_msg,
    ))

    # Valida que o HTML está completo
    html_lower = html.strip().lower()
    if not html_lower.startswith("<!doctype"):
        raise Exception("HTML gerado inválido — modelo não retornou DOCTYPE. Tente novamente.")
    if not html_lower.endswith("</html>"):
        # Fecha tags abertas de forma defensiva
        if "</body>" not in html_lower:
            html = html.rstrip() + "\n</body>\n</html>"
        else:
            html = html.rstrip() + "\n</html>"
        logger.warning("[AI] HTML truncado para '%s' — fechado automaticamente", nome)

    slug = secrets.token_urlsafe(8)
    return slug, html


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
