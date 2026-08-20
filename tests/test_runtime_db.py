import pytest

from prospector.db import DatabaseError
from prospector.runtime_db import parse_database_url


def test_parser_preserves_raw_at_sign_in_legacy_password():
    params = parse_database_url("postgresql://prospector:p@ss:w0rd@db.example.com:5432/prod")
    assert params["user"] == "prospector"
    assert params["password"] == "p@ss:w0rd"
    assert params["host"] == "db.example.com"
    assert params["port"] == 5432
    assert params["dbname"] == "prod"
    assert params["sslmode"] == "require"


def test_parser_decodes_percent_encoded_credentials():
    params = parse_database_url("postgres://user:p%40ss%23word@pooler.example.com:6543/postgres?sslmode=verify-full")
    assert params["password"] == "p@ss#word"
    assert params["port"] == 6543
    assert params["sslmode"] == "verify-full"


def test_local_database_uses_ssl_prefer_for_ci_and_development():
    params = parse_database_url("postgresql://postgres:postgres@localhost:5432/prospector")
    assert params["sslmode"] == "prefer"


def test_invalid_url_fails_with_clear_error():
    with pytest.raises(DatabaseError):
        parse_database_url("not-a-postgres-url")
