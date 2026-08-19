"""Utilidades de variação editorial e tempo de digitação do WhatsApp.

Não altera a assinatura da mensagem com caracteres invisíveis. Variações de
texto devem ser explícitas no template via spintax `{a|b|c}`.
"""
import random
import re

_SPINTAX_RE = re.compile(r"\{([^{}]*)\}")


def expandir_spintax(texto):
    """Resolve `{a|b|c}` escolhendo uma opção aleatória."""
    if not texto or "{" not in texto:
        return texto or ""

    def _troca(m):
        return random.choice(m.group(1).split("|"))

    atual = texto
    for _ in range(20):
        if "{" not in atual:
            break
        novo = _SPINTAX_RE.sub(_troca, atual)
        if novo == atual:
            break
        atual = novo
    return atual


def humanizar_mensagem(texto, variar_invisivel=False):
    """Compatibilidade: aplica somente spintax; não injeta caracteres ocultos."""
    return expandir_spintax(texto)


def delay_digitacao(texto):
    """Delay visual de digitação, limitado, para respostas/conversas."""
    n = len(texto or "")
    base = min(5000, max(800, int(n * 30)))
    return max(600, base + random.randint(-250, 500))
