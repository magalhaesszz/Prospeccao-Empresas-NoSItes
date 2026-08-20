"""
Geração de conteúdo textual para as landing pages.

A IA retorna somente JSON estruturado. Campos que poderiam virar fatos falsos
(serviços, números, depoimentos, preços e informações operacionais) são
montados exclusivamente a partir dos dados reais disponíveis no contexto.
"""
import json
import logging

from ai.copy_rules import SITE_SYSTEM

logger = logging.getLogger(__name__)


_CLICHES_SITE = (
    "excelência",
    "qualidade e confiança",
    "atendimento que faz a diferença",
    "compromisso com você",
    "profissionais experientes",
    "satisfação garantida",
    "referência em",
    "resultados que conquistam",
    "pronto para dar o próximo passo",
    "atendimento personalizado",
)


def _extrair_json(texto):
    """Extrai o primeiro objeto JSON de um texto (tolera cercas markdown/prefácio)."""
    if not texto:
        return None
    t = texto.strip()
    if t.startswith("```"):
        t = "\n".join(l for l in t.split("\n") if not l.strip().startswith("```")).strip()
    ini = t.find("{")
    fim = t.rfind("}")
    if ini == -1 or fim == -1 or fim <= ini:
        return None
    try:
        return json.loads(t[ini:fim + 1])
    except Exception:
        return None


def _local(c):
    return f" em {c['cidade']}" if c.get("cidade") else ""


def _fallback(c):
    """Conteúdo conservador: só fatos recebidos do scraping/banco."""
    nome = (c.get("nome") or "").strip() or "Empresa"
    cat = (c.get("categoria") or "Negócio local").strip()
    local = _local(c)
    telefone = (c.get("telefone") or "").strip()
    endereco = (c.get("endereco") or "").strip()

    # Sem uma lista real de serviços, não adivinhamos itens do catálogo.
    servs = [{
        "titulo": cat,
        "descricao": f"Fale com a {nome} para confirmar os serviços disponíveis, valores e disponibilidade.",
    }]

    difs = []
    if c.get("tem_nota"):
        difs.append({
            "titulo": "Avaliações no Google",
            "descricao": f"Nota {c['nota_fmt']} com {c.get('avaliacoes') or 0} avaliações no Google.",
        })
    if endereco:
        difs.append({"titulo": "Localização", "descricao": endereco})
    elif c.get("cidade"):
        difs.append({"titulo": "Localização", "descricao": c["cidade"]})
    if telefone:
        difs.append({"titulo": "Contato", "descricao": telefone})

    nums = []
    if c.get("tem_nota"):
        nums.append({"valor": c["nota_fmt"], "rotulo": "Nota no Google"})
        if c.get("avaliacoes") is not None:
            nums.append({"valor": str(c.get("avaliacoes") or 0), "rotulo": "Avaliações"})

    faq = [{
        "pergunta": "Quais serviços estão disponíveis?",
        "resposta": f"Fale com a {nome} para confirmar os serviços, valores e disponibilidade.",
    }]
    if telefone:
        faq.append({
            "pergunta": f"Como falar com a {nome}?",
            "resposta": "Use o telefone ou o WhatsApp informado nesta página.",
        })
    if endereco:
        faq.append({"pergunta": "Onde fica?", "resposta": endereco})

    sobre_partes = [f"{nome} — {cat}{local}."]
    if endereco:
        sobre_partes.append(f"Endereço informado: {endereco}.")
    if c.get("tem_nota"):
        sobre_partes.append(
            f"No Google, a empresa aparece com nota {c['nota_fmt']} em {c.get('avaliacoes') or 0} avaliações."
        )

    return {
        "hero_titulo": nome,
        "hero_subtitulo": f"{cat}{local}.",
        "hero_badge": c.get("cidade") or cat,
        "servicos": servs,
        "diferenciais": difs[:3],
        "sobre": " ".join(sobre_partes),
        "depoimentos": [],
        "numeros": nums[:2],
        "faq": faq,
        "cta_titulo": f"Fale com a {nome}",
        "cta_texto": "Entre em contato para tirar dúvidas e confirmar as informações que você precisa.",
        "meta_description": f"{nome} — {cat}{local}. Informações e contato.",
    }


def _texto_seguro(valor):
    if not isinstance(valor, str):
        return False
    baixo = valor.lower()
    return not any(cliche in baixo for cliche in _CLICHES_SITE)


def _garantir(conteudo, fb, n_serv=None):
    """Mescla apenas copy escalar segura; fatos estruturados vêm do contexto real."""
    out = dict(fb)
    if isinstance(conteudo, dict):
        for campo in (
            "hero_titulo", "hero_subtitulo", "hero_badge", "sobre",
            "cta_titulo", "cta_texto", "meta_description",
        ):
            valor = conteudo.get(campo)
            if valor and _texto_seguro(valor):
                out[campo] = valor.strip()

    # Não aceitamos fatos que o modelo tenha criado sem fonte no scraping.
    out["servicos"] = list(fb["servicos"])
    out["diferenciais"] = list(fb["diferenciais"])
    out["depoimentos"] = []
    out["numeros"] = list(fb["numeros"])
    out["faq"] = list(fb["faq"])
    return out


def gerar_conteudo(c, api_key, gerar_fn):
    """
    c: contexto factual da empresa + tema.
    gerar_fn: função (prompt, api_key, **kw) -> str.
    Retorna dict de conteúdo pronto para os layouts.
    """
    fb = _fallback(c)
    nome = c["nome"]
    cat = c["categoria"]

    dados = [f"Nome: {nome}", f"Categoria no Google: {cat}"]
    if c.get("cidade"):
        dados.append(f"Cidade: {c['cidade']}")
    if c.get("endereco"):
        dados.append(f"Endereço: {c['endereco']}")
    if c.get("telefone"):
        dados.append(f"Telefone: {c['telefone']}")
    if c.get("tem_nota"):
        dados.append(f"Nota no Google: {c['nota_fmt']} ({c.get('avaliacoes') or 0} avaliações)")

    prompt = f"""Escreva apenas os textos gerais de uma landing page para o negócio abaixo.

DADOS REAIS:
{chr(10).join(dados)}

Responda exatamente com este JSON, sem Markdown e sem texto fora dele:
{{
  "hero_titulo": "título curto e factual",
  "hero_subtitulo": "uma frase curta explicando o que é o negócio e, se houver, onde fica",
  "hero_badge": "rótulo curto baseado somente nos dados reais",
  "sobre": "2 a 4 frases curtas, somente com informações confirmadas acima",
  "cta_titulo": "convite simples para entrar em contato",
  "cta_texto": "uma frase curta orientando a pessoa a falar com o negócio",
  "meta_description": "descrição factual de até 150 caracteres"
}}

Não invente serviços, preços, horários, formas de pagamento, tempo de mercado, equipe, garantias, números, clientes ou depoimentos.
Não tente transformar poucos dados em elogios ou promessas. Se houver pouco contexto, escreva pouco.
O nome da empresa pode ser o próprio título; não é necessário criar slogan."""

    try:
        bruto = gerar_fn(
            prompt,
            api_key,
            max_tokens=900,
            timeout=75.0,
            temperature=0.35,
            system=SITE_SYSTEM,
        )
        parsed = _extrair_json(bruto)
        if parsed:
            logger.info("[site_gen] Conteúdo IA OK para '%s'", nome)
            return _garantir(parsed, fb)
        logger.warning("[site_gen] IA não retornou JSON válido para '%s' — usando fallback", nome)
    except Exception as e:
        logger.error("[site_gen] Falha conteúdo IA '%s': %s — usando fallback", nome, e)
    return _garantir({}, fb)
