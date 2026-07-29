"""
Gemini AI enrichment pipeline.
Given a company dict (with scraped Google Maps data), generates:
  - Personalized WhatsApp message (unique per company, uses real data)
  - Landing page HTML (complete, self-contained, uses real data)
"""
import secrets, logging, re
logger = logging.getLogger(__name__)


def _model(api_key, name="gemini-2.5-flash"):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(name)


def _strip_markdown(text):
    """Remove ```html ... ``` wrappers if Gemini returns them."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        t = "\n".join(lines).strip()
    return t


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

    model = _model(api_key)
    resp  = model.generate_content(prompt)
    return resp.text.strip()


# ── Gerador de landing page ───────────────────────────────────────────────────

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

    dados_reais = f"Nome: {nome}"
    if categoria: dados_reais += f"\nSegmento: {categoria}"
    if cidade:    dados_reais += f"\nCidade: {cidade}"
    if endereco:  dados_reais += f"\nEndereço: {endereco}"
    if telefone:  dados_reais += f"\nTelefone: {telefone}"
    if nota:      dados_reais += f"\nNota Google Maps: {nota:.1f} estrelas"
    if avs:       dados_reais += f"\nTotal de avaliações: {avs}"
    if foto_url:  dados_reais += f"\nFoto real do estabelecimento (URL): {foto_url}"
    if maps_url:  dados_reais += f"\nLink Google Maps: {maps_url}"

    badge_avaliacao = ""
    if nota and avs:
        badge_avaliacao = f"""
6. Seção Badge de Reputação: destaque visual com {nota:.1f}⭐ estrelas e {avs} avaliações reais no Google.
   Use CSS para criar um badge dourado elegante com as estrelas e link para o Maps: {maps_url or '#'}"""

    foto_instrucao = ""
    if foto_url:
        foto_instrucao = f"""
• FOTO REAL: use a URL da foto real do estabelecimento ({foto_url}) como <img> no hero ou seção "Sobre".
  Adicione object-fit:cover, border-radius:12px, max-width:100%, loading="lazy"."""

    prompt = f"""Você é um desenvolvedor web sênior especialista em landing pages de alta conversão.
Crie uma landing page HTML completa, profissional e visualmente impressionante.

DADOS REAIS DA EMPRESA (use TODOS na página):
{dados_reais}

━━ ESPECIFICAÇÕES TÉCNICAS (OBRIGATÓRIAS) ━━
• HTML5 completo: <!DOCTYPE html> até </html>
• CSS 100% inline em <style> — ZERO CDN, ZERO Google Fonts por URL
• Fontes: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, Helvetica, sans-serif
• Totalmente responsivo (mobile-first com @media queries)
• JavaScript MÍNIMO inline apenas para menu mobile e scroll suave{foto_instrucao}

━━ ESTRUTURA DA PÁGINA (nesta ordem exata) ━━
1. <head>: meta charset, viewport, title="{nome} | {cidade}", meta description SEO
2. Navegação sticky: logo texto com nome + links ancora (Início, Serviços, Sobre, Contato)
3. Hero: headline forte e específica para o segmento "{categoria}", subtítulo persuasivo,
   2 botões CTA: [Falar pelo WhatsApp] (verde #25D366) e [Ver Nossos Serviços]
4. Serviços: grid 3-4 cards com SVG ícone INLINE (não img), título e descrição real do segmento
5. Diferenciais: 3 razões específicas para escolher (baseadas no segmento real){badge_avaliacao}
7. Sobre a empresa: parágrafo sobre a empresa em {cidade}, mencione o endereço real
8. Depoimentos: 3 cards com texto, nome (nome brasileiro realista), "Cliente desde 202X"
9. Contato: seção com endereço real ({endereco}), telefone real ({telefone}),
   formulário visual (nome/email/telefone/mensagem) com estilo bonito
10. Botão WhatsApp flutuante FIXO: canto inferior direito, background #25D366, SVG WhatsApp branco
11. Footer: © 2025 {nome} • {cidade} • Todos os direitos reservados

━━ DESIGN E QUALIDADE ━━
• Paleta de cores profissional e moderna adequada ao segmento "{categoria}"
• Use gradientes CSS sutis no hero e nas seções alternadas
• Sombras suaves (box-shadow), border-radius 8-16px, hover transitions .3s
• Ícones SVG inline (sem CDN) — simples, elegantes
• Espaçamento generoso (padding 60-80px nas seções), tipografia bem hierarquizada
• Aparência de site REAL e estabelecido, não de template
• Animações CSS: fade-in suave nos cards via @keyframes + IntersectionObserver inline
• Textos em português brasileiro, criativos, persuasivos e específicos ao segmento

RETORNE ÚNICA E EXCLUSIVAMENTE O CÓDIGO HTML. Sem markdown, sem ```, sem qualquer texto antes ou depois."""

    model = _model(api_key)
    resp  = model.generate_content(prompt)
    html  = _strip_markdown(resp.text)
    slug  = secrets.token_urlsafe(8)
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
            logger.info("[Gemini] Página gerada para '%s' → /p/%s", empresa.get("nome"), slug)
        except Exception as e:
            logger.error("[Gemini] Falha página '%s': %s", empresa.get("nome"), e)

    mensagem = None
    try:
        mensagem = gerar_mensagem(empresa, api_key, preview_url)
        logger.info("[Gemini] Mensagem gerada para '%s'", empresa.get("nome"))
    except Exception as e:
        logger.error("[Gemini] Falha mensagem '%s': %s", empresa.get("nome"), e)

    return {
        "empresa_id":  empresa.get("id"),
        "slug":        slug,
        "html":        html,
        "mensagem":    mensagem,
        "preview_url": preview_url,
    }
