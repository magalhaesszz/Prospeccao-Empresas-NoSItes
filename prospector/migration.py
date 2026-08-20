from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def prepare_legacy_database(db) -> None:
    """Prepare a pre-V2 database for the idempotent V2 schema migration.

    Legacy Prospector versions could have a UNIQUE index on the raw phone text.
    Two textual representations of the same number (for example `(62) ...` and
    `+55 62 ...`) are legal under that index but converge to the same E.164 value
    during V2 normalization. Dropping the legacy index *before* normalization
    prevents a transient uniqueness violation.

    We also snapshot each legacy company's original `busca_id` into the V2
    appearance table before deduplication, so consolidating duplicate companies
    does not erase the fact that they appeared in different historical searches.
    The routine is safe to call on an empty database and on every application
    startup; all writes are idempotent.
    """
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute("DROP INDEX IF EXISTS uniq_empresas_telefone")
        cur.execute("SELECT to_regclass('public.empresas'), to_regclass('public.buscas')")
        empresas_table, buscas_table = cur.fetchone()
        if not empresas_table or not buscas_table:
            return

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS busca_empresas (
                busca_id INTEGER NOT NULL REFERENCES buscas(id) ON DELETE CASCADE,
                empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
                is_new INTEGER NOT NULL DEFAULT 0,
                cell_key TEXT,
                matched_by TEXT,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (busca_id, empresa_id)
            )
            """
        )
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='empresas'
                  AND column_name='busca_id'
            )
            """
        )
        if cur.fetchone()[0]:
            cur.execute(
                """
                INSERT INTO busca_empresas (busca_id, empresa_id, is_new, matched_by)
                SELECT busca_id, id, 1, 'legacy_backfill'
                FROM empresas
                WHERE busca_id IS NOT NULL
                ON CONFLICT (busca_id, empresa_id) DO NOTHING
                """
            )
            logger.info("Legacy search appearances prepared before V2 deduplication")
