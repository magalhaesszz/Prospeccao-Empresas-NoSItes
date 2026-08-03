"""
Geração de conteúdo (copy) via IA — retorna JSON estruturado, nunca HTML.
Pequeno, rápido, barato e confiável. Se a IA falhar, usa fallback derivado
dos dados reais, de modo que a página SEMPRE renderiza.
"""
import json
import logging

logger = logging.getLogger(__name__)


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


def _fallback(c):
    """Conteúdo genérico porém preenchido com dados reais — página nunca quebra."""
    nome, cat, cidade = c["nome"], c["categoria"], c["cidade"]
    local = f" em {cidade}" if cidade else ""
    servs = [
        {"titulo": "Atendimento de Qualidade", "descricao": f"Serviço profissional de {cat} com foco total na sua satisfação."},
        {"titulo": "Profissionais Experientes", "descricao": "Equipe qualificada e dedicada a entregar o melhor resultado."},
        {"titulo": "Compromisso com Você", "descricao": f"Referência em {cat}{local}, com clientes que voltam sempre."},
        {"titulo": "Praticidade e Confiança", "descricao": "Facilidade no agendamento e transparência em tudo que fazemos."},
    ]
    difs = [
        {"titulo": "Experiência comprovada", "descricao": f"Anos de dedicação em {cat}{local}."},
        {"titulo": "Clientes satisfeitos", "descricao": "Avaliações positivas de quem já é nosso cliente."},
        {"titulo": "Atendimento próximo", "descricao": "Você é tratado como prioridade do início ao fim."},
    ]
    deps = [
        {"nome": "Ana Paula", "meta": "Cliente desde 2023", "texto": f"Melhor {cat}{local}! Atendimento nota 10, super recomendo."},
        {"nome": "Carlos Silva", "meta": "Cliente", "texto": "Profissionais atenciosos e resultado excelente. Voltarei com certeza."},
        {"nome": "Juliana Mendes", "meta": "Cliente desde 2024", "texto": "Fui muito bem atendida, ambiente ótimo e serviço de qualidade."},
    ]
    if c.get("tem_nota"):
        nums = [
            {"valor": c["nota_fmt"], "rotulo": "Nota no Google"},
            {"valor": f"+{c['avaliacoes']}", "rotulo": "Avaliações reais"},
            {"valor": "+500", "rotulo": "Clientes atendidos"},
            {"valor": "100%", "rotulo": "Compromisso com você"},
        ]
    else:
        nums = [
            {"valor": "+10", "rotulo": "Anos de experiência"},
            {"valor": "+500", "rotulo": "Clientes atendidos"},
            {"valor": "100%", "rotulo": "Satisfação garantida"},
            {"valor": "5.0", "rotulo": "Nota dos clientes"},
        ]
    faq = [
        {"pergunta": f"Como faço para agendar/contratar?", "resposta": f"É simples: fale com a gente pelo WhatsApp ou telefone e a {nome} cuida de todo o resto."},
        {"pergunta": "Qual o horário de atendimento?", "resposta": "Atendemos em horário comercial. Entre em contato e encontramos o melhor horário para você."},
        {"pergunta": "Onde vocês ficam?", "resposta": f"Estamos{local}. Chame no WhatsApp que enviamos a localização e tiramos todas as suas dúvidas."},
        {"pergunta": "Quais formas de pagamento?", "resposta": "Aceitamos as principais formas de pagamento. Fale conosco para mais detalhes."},
    ]
    return {
        "hero_titulo": f"{nome}",
        "hero_subtitulo": f"{cat}{local} com qualidade, confiança e atendimento que faz a diferença.",
        "hero_badge": "Qualidade e confiança",
        "servicos": servs,
        "diferenciais": difs,
        "sobre": (f"A {nome} é referência em {cat}{local}. Com uma equipe dedicada e apaixonada "
                  f"pelo que faz, oferecemos um atendimento personalizado e resultados que "
                  f"conquistam a confiança de cada cliente. Nosso compromisso é entregar sempre "
                  f"o melhor, unindo experiência, cuidado e atenção aos detalhes. Venha nos "
                  f"conhecer e descubra por que tantos clientes escolhem a gente."),
        "depoimentos": deps,
        "numeros": nums,
        "faq": faq,
        "cta_titulo": "Pronto para dar o próximo passo?",
        "cta_texto": f"Fale com a {nome} agora mesmo e agende seu atendimento sem compromisso.",
        "meta_description": f"{nome} — {cat}{local}. Atendimento de qualidade e clientes satisfeitos.",
    }


def _garantir(conteudo, fb, n_serv):
    """Mescla o retorno da IA com o fallback, garantindo todos os campos e tamanhos."""
    out = dict(fb)
    if isinstance(conteudo, dict):
        for k, v in conteudo.items():
            if v:
                out[k] = v
    # normaliza listas
    def _lista(campo, minimo):
        val = out.get(campo)
        if not isinstance(val, list) or len(val) < 1:
            out[campo] = fb[campo]
        else:
            # completa se vier curto
            while len(out[campo]) < minimo:
                out[campo].append(fb[campo][len(out[campo]) % len(fb[campo])])
    _lista("servicos", 4)
    _lista("diferenciais", 3)
    _lista("depoimentos", 3)
    _lista("numeros", 4)
    _lista("faq", 4)
    out["servicos"] = out["servicos"][:n_serv]
    out["diferenciais"] = out["diferenciais"][:3]
    out["depoimentos"] = out["depoimentos"][:3]
    out["numeros"] = out["numeros"][:4]
    out["faq"] = out["faq"][:6]
    return out


def gerar_conteudo(c, api_key, gerar_fn):
    """
    c: contexto (dict) da empresa + tema.
    gerar_fn: função (prompt, api_key, **kw) -> str (o _gerar do enricher).
    Retorna dict de conteúdo pronto para os layouts.
    """
    fb = _fallback(c)
    nome, cat = c["nome"], c["categoria"]
    local = f" em {c['cidade']}" if c["cidade"] else ""
    preco_regra = (
        'Inclua "preco" plausível em reais (ex: "R$ 45") em cada serviço.'
        if c["mostra_preco"] else
        'NÃO inclua campo "preco".'
    )
    dados = [f"Nome: {nome}", f"Segmento: {cat}"]
    if c["cidade"]:
        dados.append(f"Cidade: {c['cidade']}")
    if c["endereco"]:
        dados.append(f"Endereço: {c['endereco']}")
    if c.get("tem_nota"):
        dados.append(f"Nota Google: {c['nota_fmt']} ({c['avaliacoes']} avaliações)")

    system = (
        "Você é copywriter de conversão especializado em negócios locais brasileiros. "
        "Escreve textos persuasivos, específicos e nada genéricos. "
        "Responde SOMENTE com JSON válido, sem markdown, sem comentários."
    )
    prompt = f"""Crie o conteúdo de uma landing page para o negócio abaixo. Português brasileiro, tom {("sofisticado e acolhedor" if c["nicho"] in ("salao","hotel","clinica","advocacia") else "direto e caloroso")}.

DADOS REAIS:
{chr(10).join(dados)}

Responda EXATAMENTE neste formato JSON (sem texto fora do JSON):
{{
  "hero_titulo": "H1 curto e impactante focado no benefício do cliente (máx 9 palavras, NÃO só o nome)",
  "hero_subtitulo": "1 frase de valor sobre {cat}{local} (máx 22 palavras)",
  "hero_badge": "selo curto de 2-4 palavras (ex: 'Referência{local}')",
  "servicos": [ {{ "titulo": "nome do serviço real de {cat}", "descricao": "1 frase específica (máx 18 palavras)" }} ... exatamente 6 itens ],
  "diferenciais": [ {{ "titulo": "curto", "descricao": "1 frase" }} ... exatamente 3 itens ],
  "numeros": [ {{ "valor": "número curto de impacto (ex '+500', '10', '4.9', '100%')", "rotulo": "o que o número representa (2-3 palavras)" }} ... exatamente 4 itens ],
  "sobre": "texto humanizado de 80-110 palavras posicionando {nome} como autoridade em {cat}{local}",
  "depoimentos": [ {{ "nome": "nome brasileiro realista", "meta": "Cliente desde 2023", "texto": "depoimento realista sobre {cat}" }} ... exatamente 3 itens ],
  "faq": [ {{ "pergunta": "dúvida real e comum de clientes de {cat}", "resposta": "1-2 frases claras" }} ... exatamente 4 itens ],
  "cta_titulo": "chamada curta para ação",
  "cta_texto": "1 frase incentivando o contato",
  "meta_description": "frase SEO de até 150 caracteres"
}}

REGRAS:
- Serviços REAIS e específicos de {cat} — proibido genérico tipo "serviço 1".
- {preco_regra}
- Zero Lorem Ipsum. Zero placeholder. Tudo pronto para publicar.
- Retorne SOMENTE o JSON."""

    try:
        bruto = gerar_fn(prompt, api_key, max_tokens=3400, timeout=110.0, temperature=0.75, system=system)
        parsed = _extrair_json(bruto)
        if parsed:
            logger.info("[site_gen] Conteúdo IA OK para '%s'", nome)
            return _garantir(parsed, fb, 6)
        logger.warning("[site_gen] IA não retornou JSON válido para '%s' — usando fallback", nome)
    except Exception as e:
        logger.error("[site_gen] Falha conteúdo IA '%s': %s — usando fallback", nome, e)
    return _garantir({}, fb, 6)
