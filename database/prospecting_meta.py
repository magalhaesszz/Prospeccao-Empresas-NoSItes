"""Metadados auxiliares da prospecção, sem alterar a API pública do banco legado.

Este módulo é aditivo: usa as tabelas existentes de empresas/buscas e cria apenas
uma tabela de cobertura territorial. Nenhuma coluna/tabela antiga é removida.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from utils.identity import company_identity, normalize_text

logger = logging.getLogger(__name__)
_schema_lock = threading.Lock()
_schema_ready = False


@dataclass(frozen=True)
class ExistingCompany:
    id: int
    nome: str
    telefone: str | None
    endereco: str
    maps_url: str
    status: str
    mensagem_enviada: int


def _db():
    from database.db import get_connection
    return get_connection()


def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        conn = _db()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prospeccao_cobertura (
                    cidade_norm    TEXT NOT NULL,
                    categoria_norm TEXT NOT NULL,
                    cell_key       TEXT NOT NULL,
                    scans          INTEGER NOT NULL DEFAULT 0,
                    resultados     INTEGER NOT NULL DEFAULT 0,
                    atualizado_em  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (cidade_norm, categoria_norm, cell_key)
                )
            """)
            conn.commit()
            _schema_ready = True
        finally:
            conn.close()


def coverage_history(cidade: str, categoria: str) -> dict[str, int]:
    ensure_schema()
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT cell_key, scans FROM prospeccao_cobertura
               WHERE cidade_norm=%s AND categoria_norm=%s""",
            (normalize_text(cidade), normalize_text(categoria)),
        )
        return {str(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    finally:
        conn.close()


def record_coverage(cidade: str, categoria: str, cell_key: str, resultados: int) -> None:
    if not cell_key:
        return
    ensure_schema()
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prospeccao_cobertura
                (cidade_norm, categoria_norm, cell_key, scans, resultados, atualizado_em)
            VALUES (%s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (cidade_norm, categoria_norm, cell_key)
            DO UPDATE SET
                scans = prospeccao_cobertura.scans + 1,
                resultados = EXCLUDED.resultados,
                atualizado_em = CURRENT_TIMESTAMP
            """,
            (normalize_text(cidade), normalize_text(categoria), cell_key, int(resultados or 0)),
        )
        conn.commit()
    finally:
        conn.close()


def load_identity_index() -> dict[str, dict[str, ExistingCompany]]:
    """Carrega empresas uma vez por busca e indexa por três identidades estáveis."""
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, nome, telefone, endereco, maps_url, status, mensagem_enviada
               FROM empresas"""
        )
        by_phone: dict[str, ExistingCompany] = {}
        by_place: dict[str, ExistingCompany] = {}
        by_fp: dict[str, ExistingCompany] = {}
        for row in cur.fetchall():
            company = ExistingCompany(
                id=int(row[0]),
                nome=row[1] or "",
                telefone=row[2],
                endereco=row[3] or "",
                maps_url=row[4] or "",
                status=row[5] or "novo",
                mensagem_enviada=int(row[6] or 0),
            )
            ident = company_identity({
                "nome": company.nome,
                "telefone": company.telefone,
                "endereco": company.endereco,
                "maps_url": company.maps_url,
            })
            if ident.get("phone"):
                by_phone.setdefault(ident["phone"], company)
            if ident.get("place_id"):
                by_place.setdefault(ident["place_id"], company)
            if ident.get("fingerprint"):
                by_fp.setdefault(ident["fingerprint"], company)
        return {"phone": by_phone, "place_id": by_place, "fingerprint": by_fp}
    finally:
        conn.close()


def find_existing(company: dict, index: dict[str, dict[str, ExistingCompany]]) -> ExistingCompany | None:
    ident = company_identity(company)
    for key in ("phone", "place_id", "fingerprint"):
        value = ident.get(key)
        if value and value in index.get(key, {}):
            return index[key][value]
    return None


def adapt_known_company(company: dict, existing: ExistingCompany) -> dict:
    """Faz o save legado reconhecer um match novo sem esconder o lead na tela."""
    company["_duplicado"] = True
    company["_existing_id"] = existing.id
    company["mensagem_enviada"] = existing.mensagem_enviada
    company["status"] = existing.status

    # salvar_empresa() legado reconhece telefone OU maps_url. Quando o match veio
    # por place-id/fingerprint, reaproveita uma chave antiga para evitar novo INSERT.
    if existing.telefone:
        company["telefone"] = existing.telefone
    elif existing.maps_url:
        company["maps_url"] = existing.maps_url
    return company
