"""
Banco de dados PostgreSQL (Supabase).
Mesma API pública do SQLite — zero mudanças nos outros módulos.
"""
import os
import logging
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _parse_url(url):
    """Parse DATABASE_URL com suporte a @ na senha."""
    rest     = url.split("://", 1)[1]
    at_idx   = rest.rfind("@")          # último @ separa credenciais do host
    creds    = rest[:at_idx]
    hostpart = rest[at_idx + 1:]

    col      = creds.index(":")
    user     = creds[:col]
    password = creds[col + 1:]

    hp     = hostpart.split("/")
    hprt   = hp[0].split(":")
    host   = hprt[0]
    port   = int(hprt[1]) if len(hprt) > 1 else 5432
    dbname = hp[1].split("?")[0] if len(hp) > 1 else "postgres"

    return dict(host=host, port=port, dbname=dbname, user=user, password=password)


def get_connection():
    params = _parse_url(DATABASE_URL)
    return psycopg2.connect(**params, sslmode="require")


def _all(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _one(cur):
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


# ── Init ──────────────────────────────────────────────────────────────────────

def inicializar_banco():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS buscas (
            id                SERIAL PRIMARY KEY,
            cidade            TEXT    NOT NULL,
            categoria         TEXT    NOT NULL,
            total_encontradas INTEGER DEFAULT 0,
            sem_site          INTEGER DEFAULT 0,
            data_busca        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id               SERIAL PRIMARY KEY,
            busca_id         INTEGER REFERENCES buscas(id),
            nome             TEXT    NOT NULL,
            telefone         TEXT,
            endereco         TEXT,
            email            TEXT,
            tem_site         INTEGER DEFAULT 0,
            site_url         TEXT,
            score            INTEGER DEFAULT 0,
            status           TEXT    DEFAULT 'novo',
            mensagem_enviada INTEGER DEFAULT 0,
            tentativas_envio INTEGER DEFAULT 0,
            erro_envio       TEXT,
            ultimo_contato   TIMESTAMP,
            template_usado   INTEGER,
            data_prospeccao  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for col, defn in [
        ("email",            "TEXT"),
        ("score",            "INTEGER DEFAULT 0"),
        ("status",           "TEXT DEFAULT 'novo'"),
        ("tentativas_envio", "INTEGER DEFAULT 0"),
        ("erro_envio",       "TEXT"),
        ("ultimo_contato",   "TIMESTAMP"),
        ("template_usado",   "INTEGER"),
    ]:
        c.execute(f"ALTER TABLE empresas ADD COLUMN IF NOT EXISTS {col} {defn}")

    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id        SERIAL PRIMARY KEY,
            nome      TEXT NOT NULL,
            mensagem  TEXT NOT NULL,
            ativo     INTEGER DEFAULT 0,
            enviados  INTEGER DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id            SERIAL PRIMARY KEY,
            telefone      TEXT UNIQUE NOT NULL,
            motivo        TEXT,
            adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id         SERIAL PRIMARY KEY,
            empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
            texto      TEXT    NOT NULL,
            criado_em  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id              SERIAL PRIMARY KEY,
            nome            TEXT    NOT NULL DEFAULT 'Agendamento',
            hora_inicio     INTEGER NOT NULL DEFAULT 9,
            hora_fim        INTEGER NOT NULL DEFAULT 18,
            limite_dia      INTEGER NOT NULL DEFAULT 20,
            dias_semana     TEXT    NOT NULL DEFAULT '1,2,3,4,5',
            ativo           INTEGER DEFAULT 1,
            mensagem_custom TEXT,
            total_hoje      INTEGER DEFAULT 0,
            ultima_execucao TIMESTAMP,
            criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_telefone ON empresas(telefone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_status   ON empresas(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notas_empresa     ON notas(empresa_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_tel     ON blacklist(telefone)")

    conn.commit()
    conn.close()
    logger.info("Banco PostgreSQL (Supabase) inicializado.")


# ── Buscas ────────────────────────────────────────────────────────────────────

def criar_busca(cidade, categoria):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO buscas (cidade, categoria) VALUES (%s, %s) RETURNING id",
        (cidade, categoria)
    )
    busca_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return busca_id


def atualizar_contagem_busca(busca_id, total, sem_site):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE buscas SET total_encontradas=%s, sem_site=%s WHERE id=%s",
        (total, sem_site, busca_id)
    )
    conn.commit()
    conn.close()


def listar_historico():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM buscas ORDER BY data_busca DESC")
    rows = _all(c)
    conn.close()
    return rows


# ── Empresas ──────────────────────────────────────────────────────────────────

def salvar_empresa(empresa, busca_id):
    conn = get_connection()
    c = conn.cursor()

    if empresa.get("telefone"):
        c.execute("SELECT id FROM empresas WHERE telefone=%s", (empresa["telefone"],))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]

    c.execute("""
        INSERT INTO empresas
            (busca_id, nome, telefone, endereco, email, tem_site, site_url, score, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'novo')
        RETURNING id
    """, (
        busca_id,
        empresa["nome"],
        empresa.get("telefone"),
        empresa.get("endereco", ""),
        empresa.get("email"),
        1 if empresa.get("tem_site") else 0,
        empresa.get("site_url", ""),
        empresa.get("score", 0),
    ))
    emp_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return emp_id


def buscar_empresa_por_id(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM empresas WHERE id=%s", (empresa_id,))
    row = _one(c)
    conn.close()
    return row


def buscar_todas_empresas(busca_id=None, apenas_sem_mensagem=False, status=None):
    conn = get_connection()
    c = conn.cursor()
    query = "SELECT * FROM empresas WHERE 1=1"
    params = []
    if busca_id:
        query += " AND busca_id=%s"
        params.append(busca_id)
    if apenas_sem_mensagem:
        query += " AND mensagem_enviada=0"
    if status:
        query += " AND status=%s"
        params.append(status)
    query += " ORDER BY score DESC, data_prospeccao DESC"
    c.execute(query, params)
    rows = _all(c)
    conn.close()
    return rows


def atualizar_status_empresa(empresa_id, novo_status):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE empresas SET status=%s, ultimo_contato=CURRENT_TIMESTAMP WHERE id=%s",
        (novo_status, empresa_id)
    )
    conn.commit()
    conn.close()


def marcar_mensagem_enviada(empresa_id, template_id=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE empresas
        SET mensagem_enviada=1, status='contatado',
            ultimo_contato=CURRENT_TIMESTAMP, template_usado=%s
        WHERE id=%s
    """, (template_id, empresa_id))
    conn.commit()
    conn.close()


def registrar_erro_envio(empresa_id, erro):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE empresas
        SET tentativas_envio = tentativas_envio + 1, erro_envio=%s
        WHERE id=%s
    """, (erro, empresa_id))
    conn.commit()
    conn.close()


# ── Templates ─────────────────────────────────────────────────────────────────

def listar_templates():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM templates ORDER BY ativo DESC, criado_em DESC")
    rows = _all(c)
    conn.close()
    return rows


def criar_template(nome, mensagem):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO templates (nome, mensagem) VALUES (%s, %s) RETURNING id",
        (nome, mensagem)
    )
    tid = c.fetchone()[0]
    conn.commit()
    conn.close()
    return tid


def atualizar_template(template_id, nome, mensagem):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE templates SET nome=%s, mensagem=%s WHERE id=%s",
        (nome, mensagem, template_id)
    )
    conn.commit()
    conn.close()


def deletar_template(template_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM templates WHERE id=%s", (template_id,))
    conn.commit()
    conn.close()


def ativar_template(template_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE templates SET ativo=0")
    c.execute("UPDATE templates SET ativo=1 WHERE id=%s", (template_id,))
    conn.commit()
    conn.close()


def get_template_ativo():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM templates WHERE ativo=1 LIMIT 1")
    row = _one(c)
    conn.close()
    return row


def incrementar_enviados_template(template_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE templates SET enviados=enviados+1 WHERE id=%s", (template_id,))
    conn.commit()
    conn.close()


# ── Blacklist ─────────────────────────────────────────────────────────────────

def listar_blacklist():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM blacklist ORDER BY adicionado_em DESC")
    rows = _all(c)
    conn.close()
    return rows


def adicionar_blacklist(telefone, motivo=""):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO blacklist (telefone, motivo) VALUES (%s, %s)",
            (telefone, motivo)
        )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()


def remover_blacklist(blacklist_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM blacklist WHERE id=%s", (blacklist_id,))
    conn.commit()
    conn.close()


def esta_na_blacklist(telefone):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM blacklist WHERE telefone=%s", (telefone,))
    row = c.fetchone()
    conn.close()
    return row is not None


# ── Notas ─────────────────────────────────────────────────────────────────────

def listar_notas(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM notas WHERE empresa_id=%s ORDER BY criado_em DESC",
        (empresa_id,)
    )
    rows = _all(c)
    conn.close()
    return rows


def adicionar_nota(empresa_id, texto):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notas (empresa_id, texto) VALUES (%s, %s) RETURNING id",
        (empresa_id, texto)
    )
    nota_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return nota_id


def deletar_nota(nota_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM notas WHERE id=%s", (nota_id,))
    conn.commit()
    conn.close()


def contar_notas(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM notas WHERE empresa_id=%s", (empresa_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


# ── Webhook / respostas ───────────────────────────────────────────────────────

def buscar_empresa_por_telefone(telefone):
    conn = get_connection()
    c = conn.cursor()
    digitos = "".join(ch for ch in str(telefone or "") if ch.isdigit())
    sufixo  = digitos[-10:] if len(digitos) >= 10 else digitos
    c.execute("""
        SELECT * FROM empresas
        WHERE regexp_replace(telefone, '[^0-9]', '', 'g') LIKE %s
        ORDER BY id DESC LIMIT 1
    """, (f"%{sufixo}",))
    row = _one(c)
    conn.close()
    return row


def marcar_respondeu(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE empresas
        SET status='respondeu', ultimo_contato=CURRENT_TIMESTAMP
        WHERE id=%s AND status NOT IN ('interessado', 'fechado')
    """, (empresa_id,))
    conn.commit()
    conn.close()


# ── Agendamentos ──────────────────────────────────────────────────────────────

def criar_agendamento(nome, hora_inicio, hora_fim, limite_dia, dias_semana, mensagem_custom=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO agendamentos (nome, hora_inicio, hora_fim, limite_dia, dias_semana, mensagem_custom)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (nome, hora_inicio, hora_fim, limite_dia, dias_semana, mensagem_custom))
    ag_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return ag_id


def listar_agendamentos():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM agendamentos ORDER BY criado_em DESC")
    rows = _all(c)
    conn.close()
    return rows


def ativar_agendamento(ag_id, ativo):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE agendamentos SET ativo=%s WHERE id=%s", (1 if ativo else 0, ag_id))
    conn.commit()
    conn.close()


def deletar_agendamento(ag_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM agendamentos WHERE id=%s", (ag_id,))
    conn.commit()
    conn.close()


def atualizar_ultima_execucao(ag_id, total_hoje):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE agendamentos
        SET ultima_execucao=CURRENT_TIMESTAMP, total_hoje=%s
        WHERE id=%s
    """, (total_hoje, ag_id))
    conn.commit()
    conn.close()


def contagem_enviadas_hoje():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM empresas
        WHERE mensagem_enviada=1
          AND ultimo_contato::date = CURRENT_DATE
    """)
    n = c.fetchone()[0] or 0
    conn.close()
    return n


# ── Funil de conversão ────────────────────────────────────────────────────────

def get_funil_conversao():
    conn = get_connection()

    def escalar(q):
        c = conn.cursor()
        c.execute(q)
        row = c.fetchone()
        return row[0] if row and row[0] is not None else 0

    funil = {
        "prospectadas": escalar("SELECT COUNT(*) FROM empresas"),
        "sem_site":     escalar("SELECT COUNT(*) FROM empresas WHERE tem_site=0"),
        "disparadas":   escalar("SELECT COUNT(*) FROM empresas WHERE mensagem_enviada=1"),
        "responderam":  escalar("SELECT COUNT(*) FROM empresas WHERE status='respondeu'"),
        "interessadas": escalar("SELECT COUNT(*) FROM empresas WHERE status='interessado'"),
        "fechadas":     escalar("SELECT COUNT(*) FROM empresas WHERE status='fechado'"),
    }
    conn.close()
    return funil
