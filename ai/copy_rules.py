"""Regras compartilhadas para textos gerados por IA.

Este módulo mantém as instruções de estilo que precisam ser consistentes entre
prospecção, respostas de WhatsApp e conteúdo de sites. Regras específicas de
cada tarefa continuam perto do respectivo fluxo.
"""
from __future__ import annotations

import re


WHATSAPP_SYSTEM = """Você escreve como uma pessoa brasileira normal conversando pelo WhatsApp.
Use português brasileiro comum, frases curtas, pontuação normal e tom direto.
Não use emoji, Markdown, listas, slogans, urgência artificial, pressão ou linguagem corporativa.
Não invente fatos, problemas, benefícios, números, preços, prazos, garantias ou informações sobre a empresa.

Quando a tarefa for PRIMEIRO CONTATO ou PROSPECÇÃO, o objetivo é obrigatório: oferecer criação de site já na primeira mensagem.
Não mande uma abertura vazia só perguntando se é a empresa e não esconda o serviço para uma mensagem futura.
Diga de forma simples que você trabalha com criação de sites/sites profissionais e faça a oferta em poucas frases.
Use 1 ou 2 dados reais da empresa para personalizar. Priorize nome, categoria, cidade e principalmente nota/quantidade de avaliações do Google quando existirem.
Se a nota for alta, você pode dizer que a empresa está bem ou muito bem avaliada no Google, mas sempre junto do dado real que sustenta esse elogio.
Se a nota não for alta ou não existir, não invente elogio: apenas use outro dado real.
Se existir uma prévia pronta, diga que montou a prévia e inclua exatamente o link informado.
Pode explicar em uma frase curta que o site serve para apresentar melhor o negócio e facilitar o contato, sem prometer aumento de vendas ou resultados.
A primeira abordagem deve ficar normalmente entre 25 e 65 palavras, em 2 a 4 frases, com no máximo uma pergunta simples no final.
Evite clichês como solução personalizada, potencializar, alavancar, presença digital, oportunidade incrível, estratégia, excelência e referência.

Quando a tarefa for RESPOSTA ou FOLLOW-UP, responda ao contexto da conversa e não repita o pitch inteiro sem necessidade.
Retorne somente o texto que seria enviado no WhatsApp."""


SITE_SYSTEM = """Você escreve textos para o site de um pequeno negócio brasileiro.
A escrita deve ser simples, concreta e informativa, sem linguagem de copywriter e sem frases genéricas de marketing.
Use somente fatos presentes nos dados fornecidos. Nunca invente serviços específicos, preços, anos de experiência, clientes, garantias, certificações, horários, formas de pagamento, avaliações, depoimentos ou números.
Se um dado não existe, omita a afirmação ou use uma frase neutra orientando a pessoa a confirmar pelo contato.
Evite palavras e fórmulas como excelência, referência, qualidade e confiança, atendimento que faz a diferença, compromisso com você, profissionais experientes, satisfação garantida, resultados que conquistam e pronto para dar o próximo passo.
Responda somente no formato solicitado pela tarefa."""


WHATSAPP_TASK_HINTS = (
    "whatsapp", "follow-up", "followup", "mensagem de resposta",
    "responder o cliente", "mensagem personalizada",
)

PROSPECCAO_CLICHES = (
    "solução personalizada",
    "soluções personalizadas",
    "potencializar",
    "alavancar",
    "presença digital",
    "transformar seu negócio",
    "elevar sua marca",
    "oportunidade incrível",
    "gostaria de apresentar",
    "venho por meio",
    "espero que esteja bem",
    "identifiquei que",
    "analisando sua empresa",
    "se destacar da concorrência",
    "maximizar",
    "otimizar sua presença",
    "revolucionar",
    "impulsionar",
    "compromisso com a excelência",
    "referência no mercado",
    "ajudar seu negócio a crescer",
    "aumentar seus resultados",
)

_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile("[\U0001F1E6-\U0001FAFF\u2600-\u27BF]")
_LIST_RE = re.compile(r"(^|\n)\s*(?:[-•]|\d+[.)])\s+", re.MULTILINE)
_SITE_TERMS = ("site", "página", "pagina", "landing page")


def is_whatsapp_task(messages) -> bool:
    """Detecta chamadas legadas que produzem texto de WhatsApp."""
    texto = "\n".join(
        m.get("content", "") for m in (messages or [])
        if isinstance(m, dict) and isinstance(m.get("content"), str)
    ).lower()
    return any(hint in texto for hint in WHATSAPP_TASK_HINTS)


def with_whatsapp_system(messages):
    """Acrescenta a regra central a prompts legados sem alterar o chamador."""
    msgs = [
        m for m in (messages or [])
        if isinstance(m, dict) and isinstance(m.get("content"), str)
    ]
    if not is_whatsapp_task(msgs):
        return msgs
    if msgs and msgs[0].get("role") == "system" and msgs[0].get("content") == WHATSAPP_SYSTEM:
        return msgs
    return [{"role": "system", "content": WHATSAPP_SYSTEM}, *msgs]


def limpar_texto_whatsapp(texto: str) -> str:
    """Normaliza saída visível sem tentar disfarçar automação ou inserir ruído."""
    if not texto:
        return ""
    texto = _ZERO_WIDTH_RE.sub("", str(texto)).strip()
    if texto.startswith("```"):
        texto = "\n".join(
            linha for linha in texto.splitlines()
            if not linha.strip().startswith("```")
        ).strip()
    texto = texto.strip().strip('"').strip("'").strip()
    texto = texto.replace("**", "").replace("__", "")
    texto = _WHITESPACE_RE.sub(" ", texto)
    return texto.strip()


def mensagem_prospeccao_aceitavel(texto: str, max_palavras: int = 70) -> bool:
    """Barreira final: primeiro contato precisa ser curto, limpo e oferecer site."""
    if not texto:
        return False
    bruto = str(texto).strip()
    baixo = bruto.lower()
    if len(_WHITESPACE_RE.split(bruto)) > max_palavras:
        return False
    if bruto.count("?") > 1:
        return False
    if _EMOJI_RE.search(bruto) or _LIST_RE.search(bruto):
        return False
    if any(marca in bruto for marca in ("**", "```")):
        return False
    if any(cliche in baixo for cliche in PROSPECCAO_CLICHES):
        return False
    if not any(termo in baixo for termo in _SITE_TERMS):
        return False
    return True


def _nota_float(nota):
    try:
        if nota is None or nota == "":
            return None
        return float(str(nota).replace(",", "."))
    except (TypeError, ValueError):
        return None


def fallback_primeiro_contato(
    nome: str = "",
    preview_url: str = "",
    categoria: str = "",
    cidade: str = "",
    nota=None,
    avaliacoes=None,
) -> str:
    """Fallback factual que oferece o site logo no primeiro contato."""
    nome = (nome or "").strip()
    preview_url = (preview_url or "").strip()
    categoria = (categoria or "").strip()
    cidade = (cidade or "").strip()
    nota_num = _nota_float(nota)
    avs = str(avaliacoes).strip() if avaliacoes not in (None, "") else ""

    if nome:
        abertura = f"Oi, tudo bem? Vi a {nome}"
    else:
        abertura = "Oi, tudo bem? Vi o negócio de vocês"

    if nota_num is not None:
        nota_txt = f"{nota_num:.1f}".replace(".", ",")
        if avs and nota_num >= 4.5:
            abertura += f" no Google: {nota_txt} de nota com {avs} avaliações. Vocês estão muito bem avaliados por lá."
        elif avs:
            abertura += f" no Google, com nota {nota_txt} e {avs} avaliações."
        elif nota_num >= 4.5:
            abertura += f" no Google, com nota {nota_txt}. É uma avaliação bem forte."
        else:
            abertura += f" no Google, com nota {nota_txt}."
    elif categoria and cidade:
        abertura += f", {categoria} em {cidade}."
    elif categoria:
        abertura += f", na área de {categoria}."
    elif cidade:
        abertura += f" em {cidade}."
    else:
        abertura += "."

    if preview_url:
        oferta = (
            f" Eu trabalho com criação de sites profissionais e montei uma prévia pra vocês: {preview_url} "
            "A ideia é apresentar bem o negócio e deixar o contato fácil. Quer que eu te explique rapidinho?"
        )
    else:
        oferta = (
            " Eu trabalho com criação de sites profissionais e queria oferecer um site pra vocês, "
            "pra apresentar bem o negócio e deixar o contato fácil. Posso te mostrar uma ideia?"
        )

    return abertura + oferta
