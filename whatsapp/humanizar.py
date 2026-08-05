"""
Humanização anti-ban do disparo.

Objetivo: fazer cada mensagem parecer digitada por uma pessoa, não um robô de
disparo em massa. WhatsApp restringe/bane números quando detecta o padrão de
"disparo": mensagens idênticas byte-a-byte enviadas em rajada, sem digitação.

Recursos:
  - Spintax `{opção A|opção B|opção C}` — cada mensagem sai com texto diferente.
  - Variação invisível — insere caracteres de largura zero para que duas
    mensagens nunca tenham a mesma assinatura, mesmo com o mesmo texto visível.
  - Tempo de digitação — calcula um "delay" (ms) proporcional ao tamanho do
    texto para a Evolution mostrar "digitando..." antes de enviar.
"""
import random
import re

# Caracteres invisíveis (largura zero). Inseridos entre palavras para quebrar a
# assinatura da mensagem sem alterar o que o destinatário lê.
_ZERO_WIDTH = ["​", "‌", "⁠"]  # ZWSP, ZWNJ, WORD JOINER

_SPINTAX_RE = re.compile(r"\{([^{}]*)\}")


def expandir_spintax(texto):
    """Resolve `{a|b|c}` escolhendo uma opção aleatória. Suporta aninhamento
    resolvendo de dentro para fora até não sobrar chaves."""
    if not texto or "{" not in texto:
        return texto or ""

    def _troca(m):
        opcoes = m.group(1).split("|")
        return random.choice(opcoes)

    # Resolve iterativamente os grupos mais internos (sem chaves dentro).
    anterior = None
    atual = texto
    # Limite de segurança para evitar loop em texto malformado.
    for _ in range(20):
        if "{" not in atual:
            break
        anterior = atual
        atual = _SPINTAX_RE.sub(_troca, atual)
        if atual == anterior:  # não houve progresso (chaves desbalanceadas)
            break
    return atual


def _inserir_invisiveis(texto, quantidade=None):
    """Insere caracteres de largura zero em limites de palavra aleatórios.
    Não altera o texto visível; só quebra a assinatura binária da mensagem."""
    if not texto:
        return texto
    # Posições possíveis: depois de um espaço simples, desde que o próximo
    # caractere não seja marcador de formatação do WhatsApp (* _ ~ `) — inserir
    # um invisível ali quebraria o negrito/itálico.
    posicoes = [
        m.end() for m in re.finditer(r" ", texto)
        if m.end() < len(texto) and texto[m.end()] not in "*_~`"
    ]
    if not posicoes:
        return texto
    if quantidade is None:
        quantidade = random.randint(1, min(3, len(posicoes)))
    escolhidas = sorted(random.sample(posicoes, min(quantidade, len(posicoes))),
                        reverse=True)
    chars = list(texto)
    for pos in escolhidas:
        chars.insert(pos, random.choice(_ZERO_WIDTH))
    return "".join(chars)


def humanizar_mensagem(texto, variar_invisivel=True):
    """Aplica spintax e variação invisível. Retorna texto pronto para envio."""
    msg = expandir_spintax(texto)
    if variar_invisivel:
        msg = _inserir_invisiveis(msg)
    return msg


def delay_digitacao(texto):
    """Milissegundos de 'digitando...' proporcionais ao tamanho, com teto e
    jitter humano. Evita rajada instantânea que denuncia robô."""
    n = len(texto or "")
    # ~45ms por caractere, com piso de 1.2s e teto de 6s.
    base = min(6000, max(1200, int(n * 45)))
    jitter = random.randint(-400, 800)
    return max(800, base + jitter)
