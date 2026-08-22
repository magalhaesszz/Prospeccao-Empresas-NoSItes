"""
Banco de dados PostgreSQL (Supabase).
Mesma API pública do SQLite — zero mudanças nos outros módulos.
"""
import os
import re
import logging
import psycopg2
import psycopg2.extras

try:
    import phonenumbers
except Exception:  # lib opcional; cai no fallback regex
    phonenumbers = None

logger = logging.getLogger(__name__)


def normalizar_telefone(raw):
    """Normaliza telefone para E164 (+55...). Usa phonenumbers; fallback regex.
    Retorna None se inválido/curto demais — evita dedup falso em lixo."""
    if not raw:
        return None
    raw = str(raw).strip()
    if phonenumbers is not None:
        try:
            num = phonenumbers.parse(raw, "BR")
            if phonenumbers.is_valid_number(num):
                return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        except Exception:
            pass
    # Fallback: só dígitos
    if raw.startswith("+"):
        d = "+" + re.sub(r"\D", "", raw)
        return d if len(d) >= 12 else None
    d = re.sub(r"\D", "", raw)
    if len(d) < 10:
        return None
    if d.startswith("55") and len(d) >= 12:
        return f"+{d}"
    return f"+55{d}"

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não definida. Configure a variável de ambiente antes de iniciar."
    )


def _parse_url(url):
    """Parse DATABASE_URL com suporte a @ na senha."""
    if "://" not in url:
        raise ValueError(f"DATABASE_URL inválida (sem '://'): {url[:80]}")
    rest     = url.split("://", 1)[1]
    at_idx   = rest.rfind("@")
    if at_idx == -1:
        raise ValueError("DATABASE_URL inválida: '@' não encontrado nas credenciais.")
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
    try:
        params = _parse_url(DATABASE_URL)
    except (ValueError, IndexError) as e:
        raise RuntimeError(f"DATABASE_URL malformada: {e}") from e
    return psycopg2.connect(**params, sslmode="require", connect_timeout=10)


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
        ("email",              "TEXT"),
        ("score",              "INTEGER DEFAULT 0"),
        ("status",             "TEXT DEFAULT 'novo'"),
        ("tentativas_envio",   "INTEGER DEFAULT 0"),
        ("erro_envio",         "TEXT"),
        ("ultimo_contato",     "TIMESTAMP"),
        ("template_usado",     "INTEGER"),
        ("descricao_google",   "TEXT"),
        ("nota",               "REAL"),
        ("avaliacoes",         "INTEGER DEFAULT 0"),
        ("gemini_mensagem",    "TEXT"),
        ("gemini_pagina_slug", "TEXT"),
        ("maps_url",           "TEXT"),
        ("foto_url",           "TEXT"),
        ("fotos_urls",         "TEXT"),
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS paginas_preview (
            id           SERIAL PRIMARY KEY,
            empresa_id   INTEGER REFERENCES empresas(id) ON DELETE SET NULL,
            nome_empresa TEXT    NOT NULL,
            slug         TEXT    UNIQUE NOT NULL,
            html         TEXT    NOT NULL,
            vistas       INTEGER DEFAULT 0,
            criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs_geracao (
            id        TEXT PRIMARY KEY,
            status    TEXT NOT NULL DEFAULT 'gerando',
            slug      TEXT,
            url       TEXT,
            erro      TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_preview_slug ON paginas_preview(slug)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_telefone ON empresas(telefone)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_empresas_status   ON empresas(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notas_empresa     ON notas(empresa_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_tel     ON blacklist(telefone)")

    # Limpa registros com dados sabidamente inválidos (resquícios de bug do scraper)
    c.execute("""
        DELETE FROM empresas
        WHERE nome IS NULL
           OR LOWER(TRIM(nome)) IN ('results', 'google maps', 'google', '')
           OR (nome ~ '^Results' AND telefone IS NULL AND endereco = '')
    """)

    # Remove duplicatas ANTES de criar índices UNIQUE (senão a criação falha)
    rem_tel  = _dedup_por_coluna(c, "telefone")
    rem_maps = _dedup_por_coluna(c, "maps_url")
    if rem_tel or rem_maps:
        logger.info("Dedup: removidas %d por telefone, %d por maps_url.", rem_tel, rem_maps)

    # Commit do dedup ANTES dos índices: se um CREATE INDEX falhar, o rollback
    # não pode desfazer a limpeza já feita.
    conn.commit()

    # Índices UNIQUE parciais (ignoram NULL/vazio) — dedup atômico à prova de race
    for nome_idx, coluna in (("uniq_empresas_telefone", "telefone"),
                             ("uniq_empresas_maps_url", "maps_url")):
        try:
            c.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {nome_idx} "
                f"ON empresas({coluna}) WHERE {coluna} IS NOT NULL AND {coluna} <> ''"
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning("Falha ao criar índice %s (duplicatas residuais?): %s", nome_idx, e)

    conn.close()
    logger.info("Banco PostgreSQL (Supabase) inicializado.")


def _dedup_por_coluna(c, coluna):
    """Remove duplicatas de empresas por `coluna` (telefone/maps_url), mantendo
    o registro mais antigo (menor id). Repointa notas e páginas de preview dos
    perdedores para o vencedor antes de apagar. `coluna` é confiável (hardcoded)."""
    if coluna not in ("telefone", "maps_url"):
        raise ValueError("coluna inválida para dedup")
    ranked = (
        f"(SELECT id, MIN(id) OVER (PARTITION BY {coluna}) AS keep_id "
        f"FROM empresas WHERE {coluna} IS NOT NULL AND {coluna} <> '')"
    )
    # Repointa filhos do perdedor -> vencedor (evita perder notas por CASCADE)
    c.execute(
        f"UPDATE notas n SET empresa_id = r.keep_id "
        f"FROM {ranked} r WHERE n.empresa_id = r.id AND r.id <> r.keep_id"
    )
    c.execute(
        f"UPDATE paginas_preview p SET empresa_id = r.keep_id "
        f"FROM {ranked} r WHERE p.empresa_id = r.id AND r.id <> r.keep_id"
    )
    c.execute(
        f"DELETE FROM empresas e USING {ranked} r WHERE e.id = r.id AND r.id <> r.keep_id"
    )
    return c.rowcount


def limpar_duplicatas():
    """Executa a deduplicação manualmente. Retorna dict com contagens."""
    conn = get_connection()
    c = conn.cursor()
    rem_tel  = _dedup_por_coluna(c, "telefone")
    rem_maps = _dedup_por_coluna(c, "maps_url")
    conn.commit()
    conn.close()
    return {"por_telefone": rem_tel, "por_maps_url": rem_maps, "total": rem_tel + rem_maps}


def limpar_empresas_invalidas():
    """Remove manualmente registros com dados inválidos do scraper."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        DELETE FROM empresas
        WHERE nome IS NULL
           OR LOWER(TRIM(nome)) IN ('results', 'google maps', 'google', '')
           OR (nome ~ '^Results' AND telefone IS NULL AND endereco = '')
    """)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted


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

def _buscar_existente(c, tel, maps_url):
    """Retorna (id, mensagem_enviada, status) se já houver empresa com o mesmo
    telefone ou maps_url; senão None."""
    if tel:
        c.execute("SELECT id, mensagem_enviada, status FROM empresas WHERE telefone=%s", (tel,))
        row = c.fetchone()
        if row:
            return row
    if maps_url:
        c.execute("SELECT id, mensagem_enviada, status FROM empresas WHERE maps_url=%s", (maps_url,))
        row = c.fetchone()
        if row:
            return row
    return None


def salvar_empresa(empresa, busca_id):
    conn = get_connection()
    c = conn.cursor()

    # Normaliza chaves de deduplicação
    tel = normalizar_telefone(empresa.get("telefone"))
    empresa["telefone"] = tel  # guarda já normalizado
    maps_url = (empresa.get("maps_url") or "").strip() or None

    # 1) Já existe? (telefone OU maps_url)
    existente = _buscar_existente(c, tel, maps_url)
    if existente:
        # Atualiza nota/avaliacoes se a nova raspagem trouxe dados melhores
        nova_nota = empresa.get("nota")
        novos_avs = empresa.get("avaliacoes") or None
        if nova_nota or novos_avs:
            c.execute("""
                UPDATE empresas
                SET nota      = COALESCE(%s, nota),
                    avaliacoes = COALESCE(%s, NULLIF(avaliacoes, 0))
                WHERE id = %s
            """, (nova_nota, novos_avs, existente[0]))
            conn.commit()
        conn.close()
        empresa["_duplicado"]       = True
        empresa["mensagem_enviada"] = existente[1]
        empresa["status"]           = existente[2]
        return existente[0]

    # 2) Insere com proteção atômica contra corrida (índices UNIQUE parciais)
    c.execute("""
        INSERT INTO empresas
            (busca_id, nome, telefone, endereco, email, tem_site, site_url, score, status,
             descricao_google, nota, avaliacoes, maps_url, foto_url, fotos_urls)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'novo', %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (
        busca_id,
        empresa["nome"],
        tel,
        empresa.get("endereco", ""),
        empresa.get("email"),
        1 if empresa.get("tem_site") else 0,
        empresa.get("site_url", ""),
        empresa.get("score", 0),
        empresa.get("descricao_google"),
        empresa.get("nota"),
        empresa.get("avaliacoes") or None,
        maps_url,
        empresa.get("foto_url", ""),
        empresa.get("fotos_urls", "[]"),
    ))
    row = c.fetchone()
    if row:
        conn.commit()
        conn.close()
        return row[0]

    # 3) Conflito (outra busca inseriu no meio do caminho) -> retorna o existente
    conn.commit()
    existente = _buscar_existente(c, tel, maps_url)
    conn.close()
    if existente:
        empresa["_duplicado"]       = True
        empresa["mensagem_enviada"] = existente[1]
        empresa["status"]           = existente[2]
        return existente[0]
    return None


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


# ── Landing Pages Preview ─────────────────────────────────────────────────────

def criar_pagina_preview(empresa_id, nome_empresa, slug, html):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO paginas_preview (empresa_id, nome_empresa, slug, html)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (empresa_id, nome_empresa, slug, html))
    pid = c.fetchone()[0]
    conn.commit()
    conn.close()
    return pid


def buscar_pagina_por_slug(slug):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM paginas_preview WHERE slug=%s", (slug,))
    row = _one(c)
    conn.close()
    return row


def registrar_vista_pagina(slug):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE paginas_preview SET vistas=vistas+1 WHERE slug=%s", (slug,))
    conn.commit()
    conn.close()


def listar_paginas_preview():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id,empresa_id,nome_empresa,slug,vistas,criado_em FROM paginas_preview ORDER BY criado_em DESC")
    rows = _all(c)
    conn.close()
    return rows


def deletar_pagina_preview(pid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM paginas_preview WHERE id=%s", (pid,))
    conn.commit()
    conn.close()


# ── Jobs de geração de página ─────────────────────────────────────────────────

def criar_job(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO jobs_geracao (id, status) VALUES (%s, 'gerando') ON CONFLICT (id) DO NOTHING", (job_id,))
    conn.commit()
    conn.close()


def atualizar_job_ok(job_id, slug, url):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs_geracao SET status='ok', slug=%s, url=%s WHERE id=%s", (slug, url, job_id))
    conn.commit()
    conn.close()


def atualizar_job_erro(job_id, erro):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE jobs_geracao SET status='erro', erro=%s WHERE id=%s", (erro[:500], job_id))
    conn.commit()
    conn.close()


def buscar_job(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs_geracao WHERE id=%s", (job_id,))
    row = _one(c)
    conn.close()
    return row


def limpar_jobs_antigos():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM jobs_geracao WHERE criado_em < NOW() - INTERVAL '24 hours'")
    conn.commit()
    conn.close()


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


def upsert_lead_whatsapp(telefone, nome=None):
    """Garante que um contato do WhatsApp esteja no CRM ao responder.
    - Se já existe (por telefone): promove para 'interessado' (não rebaixa
      'fechado'/'perdido'/'interessado'); atualiza ultimo_contato e nome se vazio.
    - Se não existe: cria um lead novo já como 'interessado'.
    Retorna (empresa_id, criado_novo: bool).
    """
    digitos = "".join(ch for ch in str(telefone or "") if ch.isdigit())
    if len(digitos) < 8:
        return None, False
    sufixo = digitos[-10:] if len(digitos) >= 10 else digitos
    nome = (nome or "").strip()

    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT id, status, nome FROM empresas
            WHERE regexp_replace(telefone, '[^0-9]', '', 'g') LIKE %s
            ORDER BY id DESC LIMIT 1
        """, (f"%{sufixo}",))
        row = _one(c)

        if row:
            eid    = row["id"]
            status = (row["status"] or "novo")
            novo_status = status if status in ("interessado", "fechado", "perdido") else "interessado"
            c.execute("""
                UPDATE empresas
                SET status=%s,
                    ultimo_contato=CURRENT_TIMESTAMP,
                    nome = CASE WHEN (nome IS NULL OR TRIM(nome)='' OR LOWER(nome) IN ('results','google maps'))
                                AND %s <> '' THEN %s ELSE nome END
                WHERE id=%s
            """, (novo_status, nome, nome, eid))
            conn.commit()
            return eid, False

        c.execute("""
            INSERT INTO empresas (nome, telefone, status, ultimo_contato)
            VALUES (%s, %s, 'interessado', CURRENT_TIMESTAMP)
            RETURNING id
        """, (nome or ("+" + digitos), telefone))
        novo = _one(c)
        conn.commit()
        return (novo["id"] if novo else None), True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


# ── Configurações (kv genérico) ───────────────────────────────────────────────

def get_config(chave, default=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT valor FROM configuracoes WHERE chave=%s", (chave,))
    row = _one(c)
    conn.close()
    if not row:
        return default
    return row["valor"] if isinstance(row, dict) else row[0]


def set_config(chave, valor):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO configuracoes (chave, valor) VALUES (%s, %s)
        ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor
    """, (chave, str(valor)))
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
