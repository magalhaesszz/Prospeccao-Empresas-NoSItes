"""
Pequenas variações de envio para WhatsApp.

A função mantém suporte a spintax de templates manuais e calcula um tempo de
"digitando..." proporcional ao texto. Ela não altera o conteúdo com caracteres
invisíveis, erros propositais ou qualquer técnica para disfarçar a origem da
mensagem.
"""
import random
import re


_SPINTAX_RE = re.compile(r"\{([^{}]*)\}")
_ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def expandir_spintax(texto):
    """Resolve `{a|b|c}` escolhendo uma opção aleatória."""
    if not texto or "{" not in texto:
        return texto or ""

    def _troca(m):
        opcoes = m.group(1).split("|")
        return random.choice(opcoes)

    atual = texto
    for _ in range(20):
        if "{" not in atual:
            break
        anterior = atual
        atual = _SPINTAX_RE.sub(_troca, atual)
        if atual == anterior:
            break
    return atual


def humanizar_mensagem(texto, variar_invisivel=False):
    """Aplica apenas spintax e remove caracteres invisíveis existentes.

    `variar_invisivel` é mantido na assinatura por compatibilidade com chamadas
    antigas, mas não produz nenhuma alteração invisível no conteúdo.
    """
    del variar_invisivel
    msg = expandir_spintax(texto)
    return _ZERO_WIDTH_RE.sub("", msg or "")


def delay_digitacao(texto):
    """Milissegundos de 'digitando...' proporcionais ao tamanho, com jitter."""
    n = len(texto or "")
    base = min(6000, max(1200, int(n * 45)))
    jitter = random.randint(-400, 800)
    return max(800, base + jitter)
