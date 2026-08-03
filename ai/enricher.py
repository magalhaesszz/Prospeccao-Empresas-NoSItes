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
{"- Mencione naturalmente que você JÁ criou uma prévia do site para eles e compartilhe o link" if tem_link else "- Ao final, pergunte de forma natural e curiosa se a empresa gostaria de ver um site demonstrativo criado especialmente para eles, sem compromisso"}
- Formatação WhatsApp: *negrito* para 1-2 pontos chave apenas
- Máximo 2 emojis, estratégicos e relevantes ao segmento
- Termine com UMA pergunta simples que incentiva resposta

Retorne APENAS a mensagem. Zero prefácio ou explicação."""

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
    cor_primaria_escura = _escurecer(cor_primaria)

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

=== FUNDAÇÃO TÉCNICA DO <head> (OBRIGATÓRIO) ===
- Estrutura: <!DOCTYPE html>, <html lang="pt-BR">, <meta charset="UTF-8">, <meta name="viewport" content="width=device-width, initial-scale=1.0">.
- <title>: "{nome} — {categoria} em {cidade}".
- <meta name="description">: frase persuasiva de até 155 caracteres sobre {nome}, incluindo {categoria} e {cidade}.
- RESET GLOBAL no CSS: seletor asterisco com margin:0; padding:0; box-sizing:border-box. Tag html com scroll-behavior:smooth. Tag img com display:block; max-width:100%.
- FONTE PREMIUM (somente fontes de sistema): font-family "Segoe UI", system-ui, -apple-system, Roboto, Helvetica, Arial, sans-serif. Texto base: cor #1f2933, line-height:1.65, font-size:16px (17px em @media min-width:768px). Títulos com line-height:1.15 e letter-spacing:-0.02em.
- CONTAINER: classe .container com max-width:1160px; margin:0 auto; padding:0 24px. TODO conteúdo de seção deve ficar dentro de um .container — nunca encostado na borda da tela.
- RITMO VERTICAL: cada <section> com padding vertical clamp(56px, 8vw, 96px). Espaçamento generoso e consistente; jamais elementos colados.

=== REGRAS DE CÓDIGO E DESIGN (OBRIGATÓRIO) ===
1. ARQUITETURA AUTOCONTIDA: Código 100% em único arquivo. CSS dentro de <style> no <head>. JavaScript mínimo antes do </body>: (a) toggle do menu mobile; (b) IntersectionObserver que adiciona a classe "visivel" às seções quando entram na viewport, para a animação de entrada.
2. ZERO DEPENDÊNCIAS: Proibido Bootstrap, Tailwind, jQuery, Google Fonts, CDNs. Use font-family: system-ui, -apple-system, sans-serif e ícones SVG inline.
3. CSS VARIABLES: :root deve conter:
   --cor-primaria: {cor_primaria};
   --cor-acento: {cor_acento};
   --cor-primaria-escura: {cor_primaria_escura};
   --sombra-card: 0 4px 24px rgba(0,0,0,0.10);
   --radius: 14px;
   --radius-btn: 50px;
   --transicao: 0.25s ease;
   Mobile-first com @media (min-width: 768px) para desktop. Flexbox/Grid moderno.
4. DESIGN VISUAL DE ALTA QUALIDADE (obrigatório):
   - Todos os cards: background:#fff; border-radius:var(--radius); box-shadow:var(--sombra-card); padding:28px 24px; border-top:4px solid var(--cor-acento).
   - Hover nos cards: transform:translateY(-5px); box-shadow:0 12px 36px rgba(0,0,0,0.18); transition:var(--transicao).
   - Botões CTA: border-radius:var(--radius-btn); padding:14px 32px; font-weight:700; letter-spacing:0.3px; transition:var(--transicao); sem borda quadrada jamais.
   - Hover nos botões: filter:brightness(1.1); transform:translateY(-2px).
   - Seções alternadas: fundo branco (#fff) e fundo claro (f8f9fa ou var(--cor-primaria) em 6% opacidade).
   - Títulos de seção: font-size:clamp(1.7rem,4vw,2.5rem); font-weight:800; posição central; linha decorativa embaixo (width:60px; height:4px; background:var(--cor-acento); border-radius:2px; margin:12px auto 0).
   - Ícones SVG: 48px, cor var(--cor-acento), círculo de fundo com var(--cor-acento) em 12% opacidade, border-radius:50%, padding:14px.
   - Inputs do formulário: border:2px solid #e0e0e0; border-radius:10px; padding:12px 16px; focus:border-color:var(--cor-acento); outline:none; width:100%.
   - ANIMAÇÃO DE ENTRADA (sutil e elegante): seções começam com opacity:0 e transform:translateY(28px); a classe "visivel" (adicionada via IntersectionObserver) aplica opacity:1 e translateY(0) com transition:0.6s ease. Envolver em @media (prefers-reduced-motion: reduce) que desativa a animação (opacity:1; transform:none).
   - GRID RESPONSIVO REAL: em mobile todos os grids viram 1 coluna; nunca deixe texto ou cards espremidos lado a lado em telas pequenas.
5. IMAGENS: Use APENAS as URLs fornecidas acima. Fotos marcadas como "indisponível" NÃO devem aparecer no HTML. object-fit: cover em todas as imagens. Alt text descritivo focado em {categoria}.
6. COPYWRITING: Proibido Lorem Ipsum. Textos persuasivos, criativos e específicos para {categoria} em {cidade}.

=== ESTRUTURA OBRIGATÓRIA (9 seções, nesta ordem exata) ===

1. HEADER/NAV (sticky, top:0, z-index:1000, background: var(--cor-primaria), color:#fff)
   - Esquerda: {nome} em negrito
   - Centro: links âncora Início · Serviços · Sobre · Contato (hidden em mobile)
   - Direita: botão WhatsApp (background: var(--cor-acento)) → {wa_link}
   - Ícone hamburger (☰) mobile que abre menu vertical

2. HERO SECTION (min-height:88vh, display:flex, align-items:center, text-align:center, position:relative)
   - Background COM foto: background-image em camadas — linear-gradient(rgba(0,0,0,0.35), rgba(0,0,0,0.72)) SOBRE a URL do hero; background-size:cover; background-position:center. O gradiente escurece embaixo para o texto respirar.
   - Background SEM foto: gradiente rico 135deg de var(--cor-primaria) até var(--cor-primaria-escura), com uma sutil textura de brilho radial (radial-gradient com var(--cor-acento) em ~15% opacidade no canto superior).
   - H1 impactante focado no benefício/dor do cliente (font-size:clamp(2.2rem,5.5vw,3.8rem); font-weight:800; color:#fff; text-shadow:0 2px 12px rgba(0,0,0,0.3); max-width:820px; margin:0 auto).
   - Subtítulo (color:rgba(255,255,255,0.92); font-size:clamp(1.05rem,2.5vw,1.35rem)): frase de valor sobre {categoria} em {cidade}.
   - 2 CTAs lado a lado (flex-wrap:wrap; gap:16px; justify-content:center): "Agendar pelo WhatsApp" (fundo var(--cor-acento), com ícone SVG do WhatsApp) e "Ver Serviços" (outline branco 2px, fundo transparente).

3. SERVIÇOS (id="servicos", background:#fff — respeita o ritmo vertical e o .container)
   - 4 a 6 cards em CSS Grid (repeat(auto-fit, minmax(240px,1fr)); gap:24px)
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
        max_tokens=16000,
        timeout=180.0,
        temperature=0.6,
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
