"""Compatibilidade entre status do CRM e controle de mensagens enviadas.

O app já usa `status='contatado'` para indicar que uma empresa foi abordada.
Este módulo garante que essa ação também ligue `mensagem_enviada`, evitando
que um contato feito manualmente volte para a fila de disparo automático.
"""
from __future__ import annotations


def install_contact_status_compat():
    from database import db

    atual = db.atualizar_status_empresa
    if getattr(atual, "_contact_status_compat", False):
        return

    original = atual

    def atualizar_status_empresa(empresa_id, novo_status):
        if novo_status != "contatado":
            return original(empresa_id, novo_status)

        conn = db.get_connection()
        c = conn.cursor()
        c.execute(
            """
            UPDATE empresas
            SET status='contatado',
                mensagem_enviada=1,
                ultimo_contato=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (empresa_id,),
        )
        conn.commit()
        conn.close()

    atualizar_status_empresa._contact_status_compat = True
    db.atualizar_status_empresa = atualizar_status_empresa
