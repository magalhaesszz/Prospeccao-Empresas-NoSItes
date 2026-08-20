from __future__ import annotations

from urllib.parse import parse_qs, unquote

from .db import Database, DatabaseError


def parse_database_url(url: str) -> dict:
    """Parse a Postgres URL while tolerating legacy unescaped credentials.

    The old Prospector deliberately used the *last* ``@`` as the credentials/
    host separator because existing production passwords may contain a raw ``@``.
    Standard URI parsers interpret that character as a delimiter unless it is
    percent-encoded. Keeping this behavior makes the V2 deployment backwards
    compatible without exposing or rewriting the secret.
    """
    value = (url or "").strip()
    if "://" not in value:
        raise DatabaseError("DATABASE_URL inválida: protocolo ausente")

    _, rest = value.split("://", 1)
    at = rest.rfind("@")
    if at <= 0:
        raise DatabaseError("DATABASE_URL inválida: credenciais/host ausentes")

    credentials = rest[:at]
    host_and_path = rest[at + 1 :]
    colon = credentials.find(":")
    if colon <= 0:
        raise DatabaseError("DATABASE_URL inválida: usuário/senha ausentes")

    user = unquote(credentials[:colon])
    password = unquote(credentials[colon + 1 :])

    host_port, slash, path = host_and_path.partition("/")
    if not slash or not host_port:
        raise DatabaseError("DATABASE_URL inválida: database ausente")

    if host_port.startswith("["):
        closing = host_port.find("]")
        if closing == -1:
            raise DatabaseError("DATABASE_URL inválida: host IPv6 malformado")
        host = host_port[1:closing]
        tail = host_port[closing + 1 :]
        port = int(tail[1:]) if tail.startswith(":") and tail[1:] else 5432
    elif ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError as exc:
            raise DatabaseError("DATABASE_URL inválida: porta inválida") from exc
    else:
        host, port = host_port, 5432

    database, _, query = path.partition("?")
    database = unquote(database or "postgres")
    query_params = parse_qs(query, keep_blank_values=True)
    explicit_ssl = (query_params.get("sslmode") or [""])[0].strip()
    local_hosts = {"localhost", "127.0.0.1", "::1", "db"}
    sslmode = explicit_ssl or ("prefer" if host.lower() in local_hosts else "require")

    return {
        "host": host,
        "port": port,
        "dbname": database,
        "user": user,
        "password": password,
        "sslmode": sslmode,
    }


class RuntimeDatabase(Database):
    """Production DB connection preserving the legacy URL/SSL behavior."""

    def connect(self):
        if not self.database_url:
            raise DatabaseError("DATABASE_URL não configurada")
        try:
            import psycopg2
        except ImportError as exc:
            raise DatabaseError("psycopg2 não instalado") from exc
        params = parse_database_url(self.database_url)
        return psycopg2.connect(**params, connect_timeout=10)
