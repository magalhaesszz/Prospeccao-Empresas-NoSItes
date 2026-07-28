"""
CRM — agrupa empresas por status e fornece dados para o Kanban.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_connection, contar_notas

COLUNAS_CRM = ["novo", "contatado", "interessado", "fechado", "perdido"]


def _all(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def kanban_por_status():
    """Retorna dict { status: [lista de empresas] } com qtd_notas por empresa."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT e.*, b.cidade, b.categoria
        FROM empresas e
        LEFT JOIN buscas b ON e.busca_id = b.id
        ORDER BY e.score DESC, e.data_prospeccao DESC
    """)
    rows = _all(c)
    conn.close()

    resultado = {s: [] for s in COLUNAS_CRM}
    for emp in rows:
        status = emp.get("status") or "novo"
        if status not in resultado:
            status = "novo"
        emp["qtd_notas"] = contar_notas(emp["id"])
        resultado[status].append(emp)

    return resultado


def resumo_funil():
    """Contagem por status para o dashboard."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as total FROM empresas GROUP BY status")
    rows = _all(c)
    conn.close()

    contagens = {s: 0 for s in COLUNAS_CRM}
    for row in rows:
        s = row["status"] or "novo"
        if s in contagens:
            contagens[s] = row["total"]
    return contagens
