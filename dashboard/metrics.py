"""
Métricas agregadas para o dashboard.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_connection
from crm.pipeline import resumo_funil


def _all(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def obter_stats():
    """Retorna todos os dados para renderizar o dashboard."""
    conn = get_connection()

    def escalar(query, params=()):
        c = conn.cursor()
        c.execute(query, params)
        row = c.fetchone()
        return row[0] if row and row[0] is not None else 0

    def query_all(query, params=()):
        c = conn.cursor()
        c.execute(query, params)
        return _all(c)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    kpis = {
        "total_prospectadas": escalar("SELECT COUNT(*) FROM empresas"),
        "sem_site":           escalar("SELECT COUNT(*) FROM empresas WHERE tem_site=0"),
        "enviadas":           escalar("SELECT COUNT(*) FROM empresas WHERE mensagem_enviada=1"),
        "interessados":       escalar("SELECT COUNT(*) FROM empresas WHERE status='interessado'"),
        "fechados":           escalar("SELECT COUNT(*) FROM empresas WHERE status='fechado'"),
        "blacklist":          escalar("SELECT COUNT(*) FROM blacklist"),
    }

    # ── CRM por status ────────────────────────────────────────────────────────
    crm = resumo_funil()

    # ── Prospecções por dia — PostgreSQL syntax ───────────────────────────────
    por_dia = query_all("""
        SELECT
            data_prospeccao::date AS data,
            COUNT(*) AS total
        FROM empresas
        WHERE data_prospeccao >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY data_prospeccao::date
        ORDER BY data_prospeccao::date
    """)
    por_dia = [{"data": str(r["data"]), "total": r["total"]} for r in por_dia]

    # ── Top categorias ────────────────────────────────────────────────────────
    top_categorias = query_all("""
        SELECT b.categoria, COUNT(e.id) as total
        FROM empresas e
        JOIN buscas b ON e.busca_id = b.id
        GROUP BY b.categoria
        ORDER BY total DESC
        LIMIT 6
    """)

    # ── Top cidades ───────────────────────────────────────────────────────────
    top_cidades = query_all("""
        SELECT b.cidade, COUNT(e.id) as total
        FROM empresas e
        JOIN buscas b ON e.busca_id = b.id
        GROUP BY b.cidade
        ORDER BY total DESC
        LIMIT 6
    """)

    # ── Distribuição site vs sem-site ─────────────────────────────────────────
    com_site    = escalar("SELECT COUNT(*) FROM empresas WHERE tem_site=1")
    sem_site    = kpis["sem_site"]
    score_medio = escalar("SELECT AVG(score) FROM empresas WHERE score > 0")

    # ── Erros de envio ────────────────────────────────────────────────────────
    erros = query_all("""
        SELECT nome, telefone, erro_envio, tentativas_envio
        FROM empresas
        WHERE erro_envio IS NOT NULL AND erro_envio != ''
        ORDER BY tentativas_envio DESC
        LIMIT 10
    """)

    conn.close()

    return {
        "kpis":           kpis,
        "crm":            crm,
        "por_dia":        por_dia,
        "top_categorias": top_categorias,
        "top_cidades":    top_cidades,
        "distribuicao":   {"com_site": com_site, "sem_site": sem_site},
        "score_medio":    round(float(score_medio), 1) if score_medio else 0,
        "erros":          erros,
    }
