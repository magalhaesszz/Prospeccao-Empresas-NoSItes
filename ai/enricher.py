"""
Groq AI enrichment pipeline.
Given a company dict (with scraped Google Maps data), generates:
  - Personalized WhatsApp message (unique per company, uses real data)
  - Landing page HTML (complete, self-contained, uses real data)
"""
import secrets, logging, re, json
logger = logging.getLogger(__name__)


_MODELO = "llama-3.3-70b-versatile"

def _gerar(prompt, api_key):
    from groq import Groq
    client = Groq(api_key=api_key, timeout=120.0)
    resp = client.chat.completions.create(
        model=_MODELO,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
    )
    return resp.choices[0].message.content.strip()


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

    # Normaliza telefone para wa.me (só dígitos)
    tel_digits = "".join(d for d in (telefone or "") if d.isdigit())
    wa_number  = f"55{tel_digits}" if tel_digits and not tel_digits.startswith("55") else tel_digits
    wa_link    = f"https://wa.me/{wa_number}" if wa_number else "https://wa.me/"
    tel_link   = f"tel:+55{tel_digits}" if tel_digits else "#"

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

    # Bloco hero: foto de fundo ou cor sólida
    if fotos_lista:
        hero_bg = f'background: linear-gradient(rgba(0,0,0,0.55),rgba(0,0,0,0.55)), url("{fotos_lista[0]}") center/cover no-repeat;'
        hero_color = "#ffffff"
    else:
        hero_bg = f"background: linear-gradient(135deg, {cor_primaria} 0%, {cor_acento}33 100%);"
        hero_color = "#ffffff"

    # Seção galeria
    if len(fotos_lista) > 1:
        imgs_html = "\n".join(
            f'          <img src="{f}" alt="Foto {i+1} - {nome}" loading="lazy">'
            for i, f in enumerate(fotos_lista)
        )
        galeria_instrucao = f"""
━━ SEÇÃO GALERIA (inserir APÓS Serviços) ━━
Título: "Nossa Galeria"
CSS grid: 3 colunas desktop, 2 mobile (375px), gap 12px
Cada <img>: object-fit:cover; height:220px; width:100%; border-radius:10px; display:block
USAR EXATAMENTE ESSAS URLs (não inventar outras):
{imgs_html}"""
    elif fotos_lista:
        galeria_instrucao = f"""
━━ FOTO REAL (usar no hero e na seção Sobre) ━━
URL: {fotos_lista[0]}
No hero: background-image inline no elemento, não em <img>.
Na seção Sobre: <img src="{fotos_lista[0]}" alt="{nome}" style="width:100%;max-width:480px;border-radius:12px;object-fit:cover;display:block;margin:0 auto">"""
    else:
        galeria_instrucao = "Não há fotos reais — NÃO use nenhuma imagem placeholder ou via picsum/unsplash/via.placeholder."

    # Badge avaliações
    if nota and avs:
        badge_instrucao = f"""
━━ SEÇÃO BADGE GOOGLE (inserir APÓS Diferenciais) ━━
Fundo {cor_acento}15, borda {cor_acento}, border-radius 16px, padding 32px, text-align center
Estrelas: mostrar {int(nota)} estrelas douradas ({cor_acento}) via CSS/Unicode ★
Texto grande: "{nota:.1f} no Google Maps"
Subtexto: "Baseado em {avs} avaliações reais de clientes"
Link: <a href="{maps_url or '#'}" target="_blank" rel="noopener">Ver avaliações no Google</a>"""
    else:
        badge_instrucao = ""

    prompt = f"""Você é desenvolvedor web sênior especialista em landing pages de alta conversão para negócios locais brasileiros.
Gere UMA landing page HTML completa e profissional para a empresa abaixo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DADOS REAIS DA EMPRESA — USE TODOS, NÃO INVENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nome:      {nome}
Segmento:  {categoria}
Cidade:    {cidade}
Endereço:  {endereco}
Telefone:  {telefone}
Nota:      {f"{nota:.1f} ⭐" if nota else "não informada"}
Avaliações:{f" {avs} avaliações no Google" if avs else " não informado"}
Maps:      {maps_url or "não informado"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PALETA DE CORES OBRIGATÓRIA (não alterar)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Primária:  {cor_primaria}
Acento:    {cor_acento}
Fundo seções alternadas: {cor_primaria}0d  (primária com 5% opacidade)
Texto principal: #1a1a1a
Texto sobre fundo escuro: #ffffff

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESPECIFICAÇÕES TÉCNICAS (TODAS OBRIGATÓRIAS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• DOCTYPE html5, meta charset="UTF-8", meta name="viewport" content="width=device-width,initial-scale=1"
• title: "{nome} | {categoria} em {cidade}"
• meta description: frase única sobre o negócio (máx 155 chars)
• Todo CSS em <style> no <head> — ZERO CDN, ZERO link externo
• font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif
• Mobile-first: layout base para 375px, depois @media(min-width:768px) para desktop
• JavaScript: apenas menu hamburger mobile e smooth scroll — inline no </body>
• ZERO Bootstrap, ZERO Tailwind, ZERO Font Awesome, ZERO Google Fonts URL
• SVG ícones: sempre inline <svg> dentro do HTML — nunca src externo
• HTML válido: todas as tags abertas devem ser fechadas corretamente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA OBRIGATÓRIA (nessa ordem exata, sem pular seções)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NAV STICKY
   position:sticky; top:0; z-index:1000; background:{cor_primaria}; color:#fff
   Esquerda: nome "{nome}" em negrito (font-size:1.1rem)
   Centro: links âncora (Início · Serviços · Sobre · Contato) — ocultos em mobile
   Direita: <a href="{wa_link}" target="_blank"> botão "WhatsApp" background:{cor_acento}; color:#fff; border-radius:6px; padding:8px 16px
   Hamburger (☰) visível só em mobile, abre menu vertical

2. HERO
   {hero_bg}
   color:{hero_color}; min-height:85vh; display:flex; align-items:center; justify-content:center; text-align:center; padding:40px 20px
   H1: nome do negócio em destaque (font-size clamp(2rem,5vw,3.5rem); font-weight:800)
   P: categoria + cidade em subtítulo (font-size:1.1rem; opacity:.9)
   2 botões lado a lado (flex-wrap:wrap; gap:16px; justify-content:center; margin-top:32px):
     • "📱 Agendar pelo WhatsApp" — background:{cor_acento}; color:#fff; href="{wa_link}"; target="_blank"
     • "↓ Nossos Serviços" — border:2px solid #fff; color:#fff; background:transparent; href="#servicos"
   Botões: padding:14px 28px; border-radius:8px; font-size:1rem; font-weight:600; text-decoration:none; display:inline-block

3. SERVIÇOS  id="servicos"
   background:#fff; padding:80px 20px; text-align:center
   Título seção: "Nossos Serviços" (font-size:2rem; color:{cor_primaria}; margin-bottom:48px)
   Grid: display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:24px; max-width:1100px; margin:0 auto
   MÍNIMO 4 cards — MÁXIMO 6 cards, específicos para "{categoria}"
   Cada card: background:#fff; border:1px solid #e8e8e8; border-radius:12px; padding:32px 24px; box-shadow:0 2px 12px rgba(0,0,0,.07); transition:transform .3s
   Card hover: transform:translateY(-4px); box-shadow:0 8px 24px rgba(0,0,0,.12)
   Cada card: SVG ícone inline (48x48, fill:{cor_acento}), <h3> serviço (color:{cor_primaria}), <p> descrição real (color:#555)
   Os serviços DEVEM ser reais e típicos de "{categoria}" — NÃO use serviços genéricos

4. DIFERENCIAIS  id="diferenciais"
   background:{cor_primaria}0d; padding:80px 20px; text-align:center
   Título: "Por que nos escolher?" (font-size:2rem; color:{cor_primaria})
   Flex: display:flex; flex-wrap:wrap; gap:32px; justify-content:center; max-width:900px; margin:32px auto 0
   3 itens — cada um: SVG ícone inline (40x40 fill:{cor_acento}), <h3> título (color:{cor_primaria}), <p> texto (color:#444; max-width:260px)
   Diferenciais específicos para o segmento "{categoria}" em {cidade}
{badge_instrucao}
{galeria_instrucao}

5. SOBRE  id="sobre"
   background:#fff; padding:80px 20px
   Layout desktop 2 colunas (grid-template-columns:1fr 1fr; gap:48px; align-items:center); mobile 1 coluna
   Coluna texto: título "Sobre {nome}" (color:{cor_primaria}), parágrafo humanizado (mín 80 palavras) sobre o negócio em {cidade}, mencione o endereço "{endereco}"
   Coluna visual: (ver instruções de foto acima)

6. DEPOIMENTOS  id="depoimentos"
   background:{cor_primaria}0d; padding:80px 20px; text-align:center
   Título: "O que nossos clientes dizem"
   Grid: 3 cards; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:24px; max-width:900px; margin:32px auto 0
   Cada card: background:#fff; border-radius:12px; padding:28px; box-shadow:0 2px 8px rgba(0,0,0,.06)
   Ícone aspas: " (font-size:3rem; color:{cor_acento}; line-height:1)
   Texto do depoimento: específico para "{categoria}" (mín 30 palavras)
   Nome: nome brasileiro realista; Período: "Cliente desde 202X"
   Estrelas: ★★★★★ (color:{cor_acento})

7. CONTATO  id="contato"
   background:#fff; padding:80px 20px
   Título: "Fale Conosco" (color:{cor_primaria})
   Layout desktop 2 colunas; mobile 1 coluna
   Coluna esquerda — informações:
     • Endereço: 📍 {endereco}
     • Telefone: 📞 <a href="{tel_link}" style="color:{cor_acento}">{telefone}</a>
     • WhatsApp: 💬 <a href="{wa_link}" target="_blank" style="color:{cor_acento}">Chamar no WhatsApp</a>
     • Maps: 🗺️ <a href="{maps_url or '#'}" target="_blank" style="color:{cor_acento}">Ver no Google Maps</a>
   Coluna direita — formulário visual (SEM action, apenas visual):
     Campos: Nome, E-mail, Telefone, Mensagem (textarea)
     Botão submit: background:{cor_acento}; color:#fff; width:100%; padding:14px; border-radius:8px; border:none; font-size:1rem; cursor:pointer
     Todos inputs: border:1px solid #ddd; border-radius:8px; padding:12px; width:100%; font-size:1rem; margin-bottom:12px

8. WHATSAPP FLUTUANTE
   position:fixed; bottom:24px; right:24px; z-index:9999
   <a href="{wa_link}" target="_blank" rel="noopener" aria-label="WhatsApp">
   Círculo: width:60px; height:60px; background:#25D366; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 4px 16px rgba(37,211,102,.4); text-decoration:none
   SVG WhatsApp branco inline (width:32; height:32; fill:#fff)

9. FOOTER
   background:{cor_primaria}; color:#fff; text-align:center; padding:32px 20px; font-size:.9rem
   © 2025 {nome} — {categoria} em {cidade}. Todos os direitos reservados.
   Linha: <a href="{wa_link}" style="color:{cor_acento}; text-decoration:none">💬 Falar pelo WhatsApp</a>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGRAS ABSOLUTAS (violação = site inválido)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ PROIBIDO: Lorem ipsum, placeholder, "exemplo", "digite aqui"
✗ PROIBIDO: qualquer URL externa de imagem que não seja das fotos reais acima
✗ PROIBIDO: Bootstrap, Tailwind CDN, Font Awesome CDN, Google Fonts URL
✗ PROIBIDO: <img> sem src real (não usar picsum, via.placeholder, unsplash etc)
✗ PROIBIDO: inventar endereço, telefone ou qualquer dado que não foi fornecido
✗ PROIBIDO: wrapper ```html``` ou qualquer texto antes/depois do HTML
✓ TODO telefone clicável: href="{tel_link}"
✓ TODO WhatsApp: href="{wa_link}"
✓ Textos em português brasileiro, persuasivos, específicos ao segmento

RETORNE APENAS O CÓDIGO HTML. Começa com <!DOCTYPE html> e termina com </html>. Nada mais."""

    html = _strip_markdown(_gerar(prompt, api_key))
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
            logger.info("[Groq] Página gerada para '%s' → /p/%s", empresa.get("nome"), slug)
        except Exception as e:
            logger.error("[Groq] Falha página '%s': %s", empresa.get("nome"), e)

    mensagem = None
    try:
        mensagem = gerar_mensagem(empresa, api_key, preview_url)
        logger.info("[Groq] Mensagem gerada para '%s'", empresa.get("nome"))
    except Exception as e:
        logger.error("[Groq] Falha mensagem '%s': %s", empresa.get("nome"), e)

    return {
        "empresa_id":  empresa.get("id"),
        "slug":        slug,
        "html":        html,
        "mensagem":    mensagem,
        "preview_url": preview_url,
    }
