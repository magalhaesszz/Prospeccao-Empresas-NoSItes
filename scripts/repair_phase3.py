"""Fase 3: separa identidade da empresa do histórico de buscas."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path, old, new):
    text = read(path)
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: esperado 1 trecho, encontrado {n}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Schema e backfill automático no startup.
# ---------------------------------------------------------------------------
replace_once(
    "database/db.py",
    '    c.execute("""\n'
    '        CREATE TABLE IF NOT EXISTS templates (\n',
    '    # Relação N:N: empresa única, mas presente em várias buscas.\n'
    '    c.execute("""\n'
    '        CREATE TABLE IF NOT EXISTS busca_empresas (\n'
    '            busca_id      INTEGER NOT NULL REFERENCES buscas(id) ON DELETE CASCADE,\n'
    '            empresa_id    INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,\n'
    '            encontrado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n'
    '            PRIMARY KEY (busca_id, empresa_id)\n'
    '        )\n'
    '    """)\n'
    '    c.execute("""\n'
    '        INSERT INTO busca_empresas (busca_id, empresa_id)\n'
    '        SELECT busca_id, id FROM empresas WHERE busca_id IS NOT NULL\n'
    '        ON CONFLICT DO NOTHING\n'
    '    """)\n'
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_busca_empresas_empresa ON busca_empresas(empresa_id)")\n\n'
    '    c.execute("""\n'
    '        CREATE TABLE IF NOT EXISTS templates (\n',
)

# Dedup de maps_url passa a considerar URL canônica (sem querystring).
replace_once(
    "database/db.py",
    '    ranked = (\n'
    '        f"(SELECT id, MIN(id) OVER (PARTITION BY {coluna}) AS keep_id "\n'
    '        f"FROM empresas WHERE {coluna} IS NOT NULL AND {coluna} <> \'\')"\n'
    '    )\n'
    '    # Repointa filhos do perdedor -> vencedor (evita perder notas por CASCADE)\n',
    '    chave = "split_part(maps_url, \'?\', 1)" if coluna == "maps_url" else coluna\n'
    '    ranked = (\n'
    '        f"(SELECT id, MIN(id) OVER (PARTITION BY {chave}) AS keep_id "\n'
    '        f"FROM empresas WHERE {coluna} IS NOT NULL AND {coluna} <> \'\')"\n'
    '    )\n'
    '    # Preserva a presença do registro perdedor em todas as buscas históricas.\n'
    '    c.execute(\n'
    '        f"INSERT INTO busca_empresas (busca_id, empresa_id) "\n'
    '        f"SELECT DISTINCT be.busca_id, r.keep_id "\n'
    '        f"FROM busca_empresas be JOIN {ranked} r ON be.empresa_id = r.id "\n'
    '        f"WHERE r.id <> r.keep_id ON CONFLICT DO NOTHING"\n'
    '    )\n'
    '    # Repointa filhos do perdedor -> vencedor (evita perder notas por CASCADE)\n',
)

# Helper transacional de associação.
replace_once(
    "database/db.py",
    'def salvar_empresa(empresa, busca_id):\n',
    'def _associar_empresa_busca(c, busca_id, empresa_id):\n'
    '    if not busca_id or not empresa_id:\n'
    '        return\n'
    '    c.execute(\n'
    '        "INSERT INTO busca_empresas (busca_id, empresa_id) VALUES (%s, %s) "\n'
    '        "ON CONFLICT DO NOTHING",\n'
    '        (busca_id, empresa_id),\n'
    '    )\n\n\n'
    'def salvar_empresa(empresa, busca_id):\n',
)

# Empresa existente: associa à nova busca antes de retornar.
replace_once(
    "database/db.py",
    '    if existente:\n'
    '        conn.close()\n'
    '        empresa["_duplicado"]       = True\n'
    '        empresa["mensagem_enviada"] = existente[1]\n'
    '        empresa["status"]           = existente[2]\n'
    '        return existente[0]\n',
    '    if existente:\n'
    '        _associar_empresa_busca(c, busca_id, existente[0])\n'
    '        conn.commit()\n'
    '        conn.close()\n'
    '        empresa["_duplicado"]       = True\n'
    '        empresa["mensagem_enviada"] = existente[1]\n'
    '        empresa["status"]           = existente[2]\n'
    '        return existente[0]\n',
)

# Empresa nova: também registra na associação N:N.
replace_once(
    "database/db.py",
    '    if row:\n'
    '        conn.commit()\n'
    '        conn.close()\n'
    '        return row[0]\n',
    '    if row:\n'
    '        _associar_empresa_busca(c, busca_id, row[0])\n'
    '        conn.commit()\n'
    '        conn.close()\n'
    '        return row[0]\n',
)

# Conflito concorrente: associa o vencedor antes de fechar a conexão.
replace_once(
    "database/db.py",
    '    conn.commit()\n'
    '    existente = _buscar_existente(c, tel, maps_url)\n'
    '    conn.close()\n'
    '    if existente:\n'
    '        empresa["_duplicado"]       = True\n'
    '        empresa["mensagem_enviada"] = existente[1]\n'
    '        empresa["status"]           = existente[2]\n'
    '        return existente[0]\n',
    '    conn.commit()\n'
    '    existente = _buscar_existente(c, tel, maps_url)\n'
    '    if existente:\n'
    '        _associar_empresa_busca(c, busca_id, existente[0])\n'
    '        conn.commit()\n'
    '    conn.close()\n'
    '    if existente:\n'
    '        empresa["_duplicado"]       = True\n'
    '        empresa["mensagem_enviada"] = existente[1]\n'
    '        empresa["status"]           = existente[2]\n'
    '        return existente[0]\n',
)

# Consultas por busca agora usam a tabela de associação, não o busca_id legado.
replace_once(
    "database/db.py",
    '    query = "SELECT * FROM empresas WHERE 1=1"\n'
    '    params = []\n'
    '    if busca_id:\n'
    '        query += " AND busca_id=%s"\n'
    '        params.append(busca_id)\n',
    '    query = "SELECT e.* FROM empresas e WHERE 1=1"\n'
    '    params = []\n'
    '    if busca_id:\n'
    '        query += " AND EXISTS (SELECT 1 FROM busca_empresas be WHERE be.empresa_id=e.id AND be.busca_id=%s)"\n'
    '        params.append(busca_id)\n',
)

# Enriquecimento de uma busca também inclui empresas que já existiam antes.
replace_once(
    "app.py",
    '    if busca_id:\n'
    '        query += " AND e.busca_id=%s"\n'
    '        params.append(busca_id)\n',
    '    if busca_id:\n'
    '        query += " AND EXISTS (SELECT 1 FROM busca_empresas be WHERE be.empresa_id=e.id AND be.busca_id=%s)"\n'
    '        params.append(busca_id)\n',
)

print("Fase 3 aplicada com sucesso.")
