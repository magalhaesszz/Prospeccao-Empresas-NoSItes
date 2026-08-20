"""
AI enrichment pipeline.
Given a company dict (with scraped Google Maps data), generates:
  - Direct WhatsApp first-contact message offering a website
  - Landing page HTML using only available business data
"""
import logging

from ai.copy_rules import (
    WHATSAPP_SYSTEM,
    fallback_primeiro_contato,
    limpar_texto_whatsapp,
    mensagem_prospeccao_aceitavel,
)

logger = logging.getLogger(__name__)


def _gerar(prompt, api_key, max_tokens=4096, timeout=90.0, temperature=0.7, system=None):
    """Gera texto usando a camada central de providers/modelos e seus fallbacks."""
    from config import CONFIG
    from ai.runtime import gerar_texto

    provider = CONFIG.get("ai_provider", "groq").lower()
    resultado = gerar_texto(
        prompt,
        CONFIG,
        preferred=provider,
        legacy_api_key=api_key,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        system=system,
    )
    return resultado["text"].strip()


def _strip_markdown(text):
    """Remove ```html ... ``` wrappers that models sometimes add around HTML."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        t = "\n".join(lines).strip()
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

    ordem = {u: i for i, u in enumerate(urls)}
    return sorted(validas, key=lambda u: ordem.get(u, 99))


# ── Contexto da empresa ───────────────────────────────────────────────────────

def _contexto(empresa, preview_url=""):
    """Monta contexto somente com dados reais disponíveis."""
    partes = [f"Empresa: {empresa.get('nome', '')}"]

    categoria = empresa.get("descricao_google") or empresa.get("categoria") or ""
    cidade    = empresa.get("cidade") or ""
    endereco  = empresa.get("endereco") or ""
    nota      = empresa.get("nota")
    avs       = empresa.get("avaliacoes")

    if categoria:
        partes.append(f"Categoria: {categoria}")
    if cidade:
        partes.append(f"Cidade: {cidade}")
    if endereco:
        partes.append(f"Endereço: {endereco}")
    if nota not in (None, ""):
        try:
            partes.append(f"Nota no Google: {float(str(nota).replace(',', '.')):.1f}")
        except (TypeError, ValueError):
            pass
    if avs not in (None, ""):
        partes.append(f"Quantidade de avaliações no Google: {avs}")
    if preview_url:
        partes.append(f"Prévia de site já criada: {preview_url}")

    return "\n".join(partes)


def _fallback_mensagem(empresa, preview_url=""):
    """Monta o fallback usando os mesmos dados reais disponíveis para a IA."""
    categoria = empresa.get("descricao_google") or empresa.get("categoria") or ""
    return fallback_primeiro_contato(
        nome=empresa.get("nome", ""),
        preview_url=preview_url,
        categoria=categoria,
        cidade=empresa.get("cidade", ""),
        nota=empresa.get("nota"),
        avaliacoes=empresa.get("avaliacoes"),
    )


# ── Gerador de mensagem personalizada ─────────────────────────────────────────

def gerar_mensagem(empresa, api_key, preview_url=""):
    """Gera primeira mensagem curta que oferece o site de forma direta e factual."""
    nome = (empresa.get("nome") or "").strip()
    ctx = _contexto(empresa, preview_url)

    tarefa = f"""Escreva a PRIMEIRA mensagem de prospecção para este contato.

Contexto real disponível:
{ctx}

OBJETIVO OBRIGATÓRIO:
- Ofereça criação de site profissional já nesta primeira mensagem. Não deixe a oferta para depois.
- Diga claramente, em linguagem normal, que você trabalha/cria sites e quer fazer ou mostrar um site para a empresa.
- Personalize com dados reais. Se houver nota e quantidade de avaliações do Google, priorize esses dados.
- Se a nota for 4,5 ou maior, pode elogiar de forma concreta dizendo que estão bem ou muito bem avaliados no Google, citando a nota real e, quando houver, a quantidade de avaliações.
- Se a nota for menor que 4,5, não chame de excelente nem muito bem avaliada; apenas cite o dado ou use categoria/cidade.
- Use no máximo 1 ou 2 detalhes da empresa. Não despeje todos os dados coletados.
- Explique o serviço em uma frase curta: um site profissional para apresentar bem o negócio e facilitar o contato. Não prometa vendas, clientes ou resultados.
- Se existe prévia, diga que você já montou a prévia e inclua exatamente o link fornecido.
- Se não existe prévia, ofereça criar/mostrar uma ideia de site, sem fingir que já existe uma página pronta.
- Termine com um CTA curto e leve, com no máximo uma pergunta.

FORMATO:
- 2 a 4 frases curtas.
- Normalmente 25 a 65 palavras.
- Sem emoji, Markdown, lista, linguagem corporativa ou clichê de marketing.
- Não comece apenas perguntando se é o responsável ou se é a empresa.

Retorne somente a mensagem pronta para envio."""

    try:
        bruto = _gerar(
            tarefa,
            api_key,
            max_tokens=220,
            timeout=60.0,
            temperature=0.6,
            system=WHATSAPP_SYSTEM,
        )
        mensagem = limpar_texto_whatsapp(bruto)
        if mensagem_prospeccao_aceitavel(mensagem, max_palavras=70):
            return mensagem
        logger.warning("[AI] Mensagem sem oferta direta ou fora do estilo para '%s' — usando fallback", nome)
    except Exception:
        logger.exception("[AI] Falha ao gerar mensagem para '%s' — usando fallback", nome)

    return _fallback_mensagem(empresa, preview_url)


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
    return "#1a1a2a", "#e67e22"


def gerar_pagina(empresa, api_key):
    """Gera um site demo usando layout fixo e conteúdo textual estruturado."""
    from ai.site_gen import gerar_site
    return gerar_site(
        empresa,
        api_key,
        gerar_fn=_gerar,
        validar_fotos_fn=_validar_fotos,
    )


# ── Pipeline completo por empresa ─────────────────────────────────────────────

def enriquecer(empresa, api_key, app_url="", criar_pagina=True):
    """Gera página opcional e mensagem de WhatsApp preservando o contrato existente."""
    preview_url = ""
    slug = None
    html = None

    if criar_pagina:
        try:
            slug, html = gerar_pagina(empresa, api_key)
            if app_url:
                preview_url = f"{app_url.rstrip('/')}/p/{slug}"
            logger.info("[AI] Página gerada para '%s' → /p/%s", empresa.get("nome"), slug)
        except Exception as e:
            logger.error("[AI] Falha página '%s': %s", empresa.get("nome"), e)

    try:
        mensagem = gerar_mensagem(empresa, api_key, preview_url)
        logger.info("[AI] Mensagem gerada para '%s'", empresa.get("nome"))
    except Exception as e:
        logger.error("[AI] Falha mensagem '%s': %s", empresa.get("nome"), e)
        mensagem = _fallback_mensagem(empresa, preview_url)

    return {
        "empresa_id": empresa.get("id"),
        "slug": slug,
        "html": html,
        "mensagem": mensagem,
        "preview_url": preview_url,
    }
