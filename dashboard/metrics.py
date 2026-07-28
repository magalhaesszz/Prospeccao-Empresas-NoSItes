"""
Métricas agregadas para o dashboard.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_connection
from crm.pipeline import resumo_funil


def obter_stats():
    """Retorna todos os dados necessários para renderizar o dashboard."""
    conn = get_connection()

    # ── KPIs ─────────────────────────────────────────────────────────────────
    def escalar(query, params=()):
        return conn.execute(query, params).fetchone()[0] or 0

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

    # ── Prospecções por dia (últimos 30 dias) ─────────────────────────────────
    rows_dia = conn.execute("""
        SELECT DATE(data_prospeccao) as data, COUNT(*) as total
        FROM empresas
        WHERE data_prospeccao >= DATE('now', '-30 days')
        GROUP BY DATE(data_prospeccao)
        ORDER BY data
    """).fetchall()
    por_dia = [{"data": r["data"], "total": r["total"]} for r in rows_dia]

    # ── Top categorias ────────────────────────────────────────────────────────
    rows_cat = conn.execute("""
        SELECT b.categoria, COUNT(e.id) as total
        FROM empresas e
        JOIN buscas b ON e.busca_id = b.id
        GROUP BY b.categoria
        ORDER BY total DESC
        LIMIT 6
    """).fetchall()
    top_categorias = [{"categoria": r["categoria"], "total": r["total"]} for r in rows_cat]

    # ── Top cidades ──────────────────────────────────────────────────────────
    rows_cid = conn.execute("""
        SELECT b.cidade, COUNT(e.id) as total
        FROM empresas e
        JOIN buscas b ON e.busca_id = b.id
        GROUP BY b.cidade
        ORDER BY total DESC
        LIMIT 6
    """).fetchall()
    top_cidades = [{"cidade": r["cidade"], "total": r["total"]} for r in rows_cid]

    # ── Distribuição site vs sem-site ─────────────────────────────────────────
    com_site = escalar("SELECT COUNT(*) FROM empresas WHERE tem_site=1")
    sem_site  = kpis["sem_site"]

    # ── Score médio ───────────────────────────────────────────────────────────
    score_medio = escalar("SELECT AVG(score) FROM empresas WHERE score > 0")

    # ── Erros de envio ────────────────────────────────────────────────────────
    rows_erros = conn.execute("""
        SELECT nome, telefone, erro_envio, tentativas_envio
        FROM empresas
        WHERE erro_envio IS NOT NULL AND erro_envio != ''
        ORDER BY tentativas_envio DESC
        LIMIT 10
    """).fetchall()
    erros = [dict(r) for r in rows_erros]

    conn.close()

    return {
        "kpis":           kpis,
        "crm":            crm,
        "por_dia":        por_dia,
        "top_categorias": top_categorias,
        "top_cidades":    top_cidades,
        "distribuicao":   {"com_site": com_site, "sem_site": sem_site},
        "score_medio":    round(score_medio, 1) if score_medio else 0,
        "erros":          erros,
    }
