"""
Gerenciamento de templates de mensagem.
Seleciona template manual ativo ou usa o fallback curto e factual do sistema.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.copy_rules import fallback_primeiro_contato
from database.db import get_template_ativo


def obter_mensagem(nome_empresa, template_id=None):
    """
    Retorna a mensagem formatada para uma empresa.
    Prioridade: template_id passado > template ativo no banco > fallback natural.
    Retorna (mensagem, template_id_usado).

    Templates criados pelo usuário não são reescritos silenciosamente.
    """
    template = None

    if template_id:
        from database.db import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM templates WHERE id=%s", (template_id,))
        cols = [d[0] for d in c.description]
        row = c.fetchone()
        conn.close()
        if row:
            template = dict(zip(cols, row))

    if not template:
        template = get_template_ativo()

    if template:
        mensagem = template["mensagem"].replace("{NOME_DA_EMPRESA}", nome_empresa)
        return mensagem, template["id"]

    return fallback_primeiro_contato(nome_empresa), None


def preview_template(mensagem_raw, nome_exemplo="Barbearia do João"):
    """Retorna preview formatado com nome de exemplo."""
    return mensagem_raw.replace("{NOME_DA_EMPRESA}", nome_exemplo)
