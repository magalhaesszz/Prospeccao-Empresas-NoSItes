"""
Banco de dados SQLite — schema completo com CRM, templates, blacklist e notas.
Suporta migração incremental (não apaga dados existentes).
"""
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

# Em produção: defina DB_PATH=/data/prospector.db e monte um volume Railway em /data
# Localmente: usa prospector.db na raiz do projeto
# Em produção: defina DB_PATH=/data/prospector.db e monte um volume Railway em /data
# Localmente: usa prospector.db na raiz do projeto
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prospector.db")
)
_db_dir = os.path.dirname(DB_PATH)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # melhor concorrência
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def inicializar_banco():
    """Cria tabelas e colunas novas sem apagar dados existentes."""
    conn = get_connection()
    c = conn.cursor()

    # ── Buscas ───────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS buscas (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            cidade            TEXT    NOT NULL,
            categoria         TEXT    NOT NULL,
            total_encontradas INTEGER DEFAULT 0,
            sem_site          INTEGER DEFAULT 0,
            data_busca        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Empresas ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            busca_id         INTEGER,
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
            data_prospeccao  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (busca_id) REFERENCES buscas(id)
        )
    """)

    # Migração incremental — adiciona colunas se não existirem
    _adicionar_coluna(c, "empresas", "email",            "TEXT")
    _adicionar_coluna(c, "empresas", "score",            "INTEGER DEFAULT 0")
    _adicionar_coluna(c, "empresas", "status",           "TEXT DEFAULT 'novo'")
    _adicionar_coluna(c, "empresas", "tentativas_envio", "INTEGER DEFAULT 0")
    _adicionar_coluna(c, "empresas", "erro_envio",       "TEXT")
    _adicionar_coluna(c, "empresas", "ultimo_contato",   "TIMESTAMP")
    _adicionar_coluna(c, "empresas", "template_usado",   "INTEGER")

    # ── Templates de mensagem ────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            nome       TEXT NOT NULL,
            mensagem   TEXT NOT NULL,
            ativo      INTEGER DEFAULT 0,
            enviados   INTEGER DEFAULT 0,
            criado_em  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Blacklist ────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            telefone      TEXT UNIQUE NOT NULL,
            motivo        TEXT,
            adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Notas de CRM ─────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            texto      TEXT    NOT NULL,
            criado_em  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
        )
    """)

    # Índices
    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_telefone ON empresas(telefone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_status   ON empresas(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notas_empresa     ON notas(empresa_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_tel     ON blacklist(telefone)")

    conn.commit()
    conn.close()
    logger.info("Banco inicializado: %s", DB_PATH)


def _adicionar_coluna(cursor, tabela, coluna, definicao):
    """Adiciona coluna se não existir — idempotente."""
    try:
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
    except sqlite3.OperationalError:
        pass  # coluna já existe


# ── Buscas ───────────────────────────────────────────────────────────────────

def criar_busca(cidade, categoria):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO buscas (cidade, categoria) VALUES (?, ?)", (cidade, categoria))
    busca_id = c.lastrowid
    conn.commit()
    conn.close()
    return busca_id


def atualizar_contagem_busca(busca_id, total, sem_site):
    conn = get_connection()
    conn.execute(
        "UPDATE buscas SET total_encontradas=?, sem_site=? WHERE id=?",
        (total, sem_site, busca_id)
    )
    conn.commit()
    conn.close()


def listar_historico():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM buscas ORDER BY data_busca DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Empresas ──────────────────────────────────────────────────────────────────

def salvar_empresa(empresa, busca_id):
    """Salva empresa. Evita duplicata por telefone. Retorna ID."""
    conn = get_connection()
    c = conn.cursor()

    if empresa.get("telefone"):
        c.execute("SELECT id FROM empresas WHERE telefone=?", (empresa["telefone"],))
        existente = c.fetchone()
        if existente:
            conn.close()
            return existente["id"]

    c.execute("""
        INSERT INTO empresas
            (busca_id, nome, telefone, endereco, email, tem_site, site_url, score, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'novo')
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
    emp_id = c.lastrowid
    conn.commit()
    conn.close()
    return emp_id


def buscar_empresa_por_id(empresa_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_todas_empresas(busca_id=None, apenas_sem_mensagem=False, status=None):
    conn = get_connection()
    query = "SELECT * FROM empresas WHERE 1=1"
    params = []
    if busca_id:
        query += " AND busca_id=?"
        params.append(busca_id)
    if apenas_sem_mensagem:
        query += " AND mensagem_enviada=0"
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY score DESC, data_prospeccao DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def atualizar_status_empresa(empresa_id, novo_status):
    conn = get_connection()
    conn.execute(
        "UPDATE empresas SET status=?, ultimo_contato=CURRENT_TIMESTAMP WHERE id=?",
        (novo_status, empresa_id)
    )
    conn.commit()
    conn.close()


def marcar_mensagem_enviada(empresa_id, template_id=None):
    conn = get_connection()
    conn.execute("""
        UPDATE empresas
        SET mensagem_enviada=1, status='contatado',
            ultimo_contato=CURRENT_TIMESTAMP, template_usado=?
        WHERE id=?
    """, (template_id, empresa_id))
    conn.commit()
    conn.close()


def registrar_erro_envio(empresa_id, erro):
    conn = get_connection()
    conn.execute("""
        UPDATE empresas
        SET tentativas_envio = tentativas_envio + 1, erro_envio=?
        WHERE id=?
    """, (erro, empresa_id))
    conn.commit()
    conn.close()


# ── Templates ─────────────────────────────────────────────────────────────────

def listar_templates():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM templates ORDER BY ativo DESC, criado_em DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def criar_template(nome, mensagem):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO templates (nome, mensagem) VALUES (?, ?)", (nome, mensagem))
    tid = c.lastrowid
    conn.commit()
    conn.close()
    return tid


def atualizar_template(template_id, nome, mensagem):
    conn = get_connection()
    conn.execute(
        "UPDATE templates SET nome=?, mensagem=? WHERE id=?",
        (nome, mensagem, template_id)
    )
    conn.commit()
    conn.close()


def deletar_template(template_id):
    conn = get_connection()
    conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()


def ativar_template(template_id):
    conn = get_connection()
    conn.execute("UPDATE templates SET ativo=0")
    conn.execute("UPDATE templates SET ativo=1 WHERE id=?", (template_id,))
    conn.commit()
    conn.close()


def get_template_ativo():
    """Retorna o template ativo ou None."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM templates WHERE ativo=1 LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def incrementar_enviados_template(template_id):
    conn = get_connection()
    conn.execute("UPDATE templates SET enviados=enviados+1 WHERE id=?", (template_id,))
    conn.commit()
    conn.close()


# ── Blacklist ─────────────────────────────────────────────────────────────────

def listar_blacklist():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM blacklist ORDER BY adicionado_em DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def adicionar_blacklist(telefone, motivo=""):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO blacklist (telefone, motivo) VALUES (?, ?)",
            (telefone, motivo)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # já existe
    finally:
        conn.close()


def remover_blacklist(blacklist_id):
    conn = get_connection()
    conn.execute("DELETE FROM blacklist WHERE id=?", (blacklist_id,))
    conn.commit()
    conn.close()


def esta_na_blacklist(telefone):
    conn = get_connection()
    row = conn.execute("SELECT id FROM blacklist WHERE telefone=?", (telefone,)).fetchone()
    conn.close()
    return row is not None


# ── Notas ─────────────────────────────────────────────────────────────────────

def listar_notas(empresa_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notas WHERE empresa_id=? ORDER BY criado_em DESC",
        (empresa_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def adicionar_nota(empresa_id, texto):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO notas (empresa_id, texto) VALUES (?, ?)",
        (empresa_id, texto)
    )
    nota_id = c.lastrowid
    conn.commit()
    conn.close()
    return nota_id


def deletar_nota(nota_id):
    conn = get_connection()
    conn.execute("DELETE FROM notas WHERE id=?", (nota_id,))
    conn.commit()
    conn.close()


def contar_notas(empresa_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as n FROM notas WHERE empresa_id=?", (empresa_id,)
    ).fetchone()
    conn.close()
    return row["n"] if row else 0
