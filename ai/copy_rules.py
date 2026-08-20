"""Regras compartilhadas para textos gerados por IA.

Este módulo mantém as instruções de estilo que precisam ser consistentes entre
prospecção, respostas de WhatsApp e conteúdo de sites. Regras específicas de
cada tarefa continuam perto do respectivo fluxo.
"""
from __future__ import annotations

import re


WHATSAPP_SYSTEM = """Você escreve como uma pessoa brasileira normal conversando pelo WhatsApp.
O texto deve soar espontâneo, simples e direto, não como anúncio, e-mail comercial, copy ou resposta de assistente.
Use português brasileiro comum, frases curtas e pontuação normal.
Não use emoji, Markdown, listas, slogans, elogios genéricos, urgência, pressão ou linguagem corporativa.
Não tente encaixar todos os dados disponíveis. Use um detalhe da empresa só quando ele realmente deixar a conversa mais natural.
Não invente fatos, problemas, benefícios, números, preços, prazos, garantias ou informações sobre a empresa.
Evite clichês de prospecção e palavras como solução, potencializar, alavancar, presença digital, oportunidade, estratégia, excelência, referência e resultados.
Prefira uma ideia por mensagem e no máximo uma pergunta.
Retorne somente o texto que seria enviado no WhatsApp."""


SITE_SYSTEM = """Você escreve textos para o site de um pequeno negócio brasileiro.
A escrita deve ser simples, concreta e informativa, sem linguagem de copywriter e sem frases genéricas de marketing.
Use somente fatos presentes nos dados fornecidos. Nunca invente serviços específicos, preços, anos de experiência, clientes, garantias, certificações, horários, formas de pagamento, avaliações, depoimentos ou números.
Se um dado não existe, omita a afirmação ou use uma frase neutra orientando a pessoa a confirmar pelo contato.
Evite palavras e fórmulas como excelência, referência, qualidade e confiança, atendimento que faz a diferença, compromisso com você, profissionais experientes, satisfação garantida, resultados que conquistam e pronto para dar o próximo passo.
Responda somente no formato solicitado pela tarefa."""


WHATSAPP_TASK_HINTS = (
    "whatsapp", "prospecção", "prospeccao", "follow-up", "followup",
    "mensagem de resposta", "responder o cliente", "mensagem personalizada",
)

_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")


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


def fallback_primeiro_contato(nome: str = "", preview_url: str = "") -> str:
    """Fallback curto e factual para quando a geração da primeira mensagem falha."""
    nome = (nome or "").strip()
    preview_url = (preview_url or "").strip()
    if preview_url:
        if nome:
            return f"Oi, montei uma prévia de site pra {nome} aqui: {preview_url} Quer que eu te mostre o que pensei?"
        return f"Oi, montei uma prévia de site pra vocês aqui: {preview_url} Quer que eu te mostre o que pensei?"
    if nome:
        return f"Oi, tudo certo? Tô falando com o pessoal da {nome}?"
    return "Oi, tudo certo? Tô falando com o responsável por aí?"
