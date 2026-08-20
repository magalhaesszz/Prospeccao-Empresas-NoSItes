"""
AI enrichment pipeline.
Given a company dict (with scraped Google Maps data), generates:
  - Short WhatsApp first-contact message
  - Landing page HTML using only available business data
"""
import logging

from ai.copy_rules import WHATSAPP_SYSTEM, fallback_primeiro_contato, limpar_texto_whatsapp

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
    if nota:
        try:
            partes.append(f"Nota no Google: {float(nota):.1f}")
        except (TypeError, ValueError):
            pass
    if avs:
        partes.append(f"Quantidade de avaliações no Google: {avs}")
    if preview_url:
        partes.append(f"Prévia de site já criada: {preview_url}")

    return "\n".join(partes)


_PROIBIDAS_PROSPECCAO = (
    "presença digital",
    "potencializar",
    "alavancar",
    "solução personalizada",
    "oportunidade incrível",
    "gostaria de apresentar",
    "venho por meio",
    "identifiquei que",
    "analisando sua empresa",
    "se destacar da concorrência",
    "maximizar",
    "revolucionar",
    "compromisso com a excelência",
)


def _mensagem_aceitavel(texto):
    baixo = (texto or "").lower()
    if not texto or len(texto.split()) > 45:
        return False
    if any(x in baixo for x in _PROIBIDAS_PROSPECCAO):
        return False
    if any(x in texto for x in ("**", "```", "✅", "🚀", "👋", "🎯", "💡")):
        return False
    return texto.count("?") <= 1


# ── Gerador de mensagem personalizada ─────────────────────────────────────────

def gerar_mensagem(empresa, api_key, preview_url=""):
    """Gera uma primeira mensagem curta, factual e natural para WhatsApp."""
    nome = (empresa.get("nome") or "").strip()
    ctx = _contexto(empresa, preview_url)

    tarefa = f"""Escreva a primeira mensagem para este contato.

Contexto disponível:
{ctx}

A mensagem deve ter normalmente 1 a 3 frases e poucas palavras.
Não faça um mini pitch. Não tente vender site e automação ao mesmo tempo.
Não precisa usar nome, cidade, nota, avaliações ou categoria só porque esses dados existem.
Não elogie a empresa sem um motivo concreto.
Varie naturalmente a abertura: pode confirmar se é a empresa, mencionar a prévia ou perguntar se pode enviar uma ideia.
{"Como já existe uma prévia, você pode mencioná-la e usar exatamente o link informado." if preview_url else "Como não há prévia informada, não diga que já fez ou já deixou um site pronto."}
Não fale que a empresa perde clientes, não critique o negócio e não diga que ela precisa melhorar.

Retorne somente a mensagem."""

    try:
        bruto = _gerar(
            tarefa,
            api_key,
            max_tokens=140,
            timeout=60.0,
            temperature=0.6,
            system=WHATSAPP_SYSTEM,
        )
        mensagem = limpar_texto_whatsapp(bruto)
        if _mensagem_aceitavel(mensagem):
            return mensagem
        logger.warning("[AI] Mensagem fora do estilo esperado para '%s' — usando fallback", nome)
    except Exception:
        logger.exception("[AI] Falha ao gerar mensagem para '%s' — usando fallback", nome)

    return fallback_primeiro_contato(nome, preview_url)


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
        mensagem = fallback_primeiro_contato(empresa.get("nome", ""), preview_url)

    return {
        "empresa_id": empresa.get("id"),
        "slug": slug,
        "html": html,
        "mensagem": mensagem,
        "preview_url": preview_url,
    }
