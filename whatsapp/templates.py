"""
Gerenciamento de templates de mensagem.
Seleciona template ativo ou fallback do config.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from database.db import get_template_ativo


def obter_mensagem(nome_empresa, template_id=None):
    """
    Retorna a mensagem formatada para uma empresa.
    Prioridade: template_id passado > template ativo no banco > config.py
    Retorna (mensagem, template_id_usado)
    """
    template = None

    if template_id:
        from database.db import get_connection
        conn = get_connection()
        row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        conn.close()
        if row:
            template = dict(row)

    if not template:
        template = get_template_ativo()

    if template:
        try:
            mensagem = template["mensagem"].format(NOME_DA_EMPRESA=nome_empresa)
            return mensagem, template["id"]
        except KeyError:
            pass

    # Fallback: mensagem do config
    mensagem = CONFIG["mensagem_whatsapp"].format(NOME_DA_EMPRESA=nome_empresa)
    return mensagem, None


def preview_template(mensagem_raw, nome_exemplo="Barbearia do João"):
    """Retorna preview formatado com nome de exemplo."""
    try:
        return mensagem_raw.format(NOME_DA_EMPRESA=nome_exemplo)
    except Exception:
        return mensagem_raw
