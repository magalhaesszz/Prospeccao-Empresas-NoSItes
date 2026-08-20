import os

import pytest

from prospector.db import Database
from prospector.migration import prepare_legacy_database

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL required")


def reset_public(db):
    with db.transaction() as conn:
        c = conn.cursor()
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")


def test_schema_and_cross_run_deduplication():
    db = Database(os.environ["DATABASE_URL"])
    reset_public(db)
    prepare_legacy_database(db)
    db.init_schema()
    r1 = db.create_run("Goiânia", "Clínica")
    a = db.upsert_company(
        {"nome": "Clínica A", "telefone": "(62) 99999-1234", "endereco": "Rua 1, 10", "tem_site": False, "score": 80},
        r1,
        "Goiânia",
        "Clínica",
        "c1",
    )
    assert a["is_new"] is True
    r2 = db.create_run("Goiânia", "Clínica")
    b = db.upsert_company(
        {"nome": "Clinica A", "telefone": "+55 62 99999-1234", "endereco": "Rua 1 10", "tem_site": False, "score": 85},
        r2,
        "Goiânia",
        "Clínica",
        "c2",
    )
    assert b["id"] == a["id"]
    assert b["is_new"] is False
    assert len(db.run_results(r2, include_known=True)) == 1
    assert db.run_results(r2, include_known=False) == []


def test_migrates_legacy_schema_with_raw_phone_duplicates_and_preserves_history():
    db = Database(os.environ["DATABASE_URL"])
    reset_public(db)
    with db.transaction() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE buscas (
              id SERIAL PRIMARY KEY, cidade TEXT NOT NULL, categoria TEXT NOT NULL,
              total_encontradas INTEGER DEFAULT 0, sem_site INTEGER DEFAULT 0,
              data_busca TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE empresas (
              id SERIAL PRIMARY KEY, busca_id INTEGER REFERENCES buscas(id), nome TEXT NOT NULL,
              telefone TEXT, endereco TEXT, email TEXT, tem_site INTEGER DEFAULT 0, site_url TEXT,
              score INTEGER DEFAULT 0, status TEXT DEFAULT 'novo', mensagem_enviada INTEGER DEFAULT 0,
              tentativas_envio INTEGER DEFAULT 0, erro_envio TEXT, ultimo_contato TIMESTAMP,
              template_usado INTEGER, data_prospeccao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute("CREATE UNIQUE INDEX uniq_empresas_telefone ON empresas(telefone) WHERE telefone IS NOT NULL AND telefone <> ''")
        c.execute(
            "CREATE TABLE notas (id SERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE, texto TEXT NOT NULL, criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        c.execute("INSERT INTO buscas (cidade,categoria) VALUES ('Goiânia','Clínica'),('Goiânia','Clínica') RETURNING id")
        run_ids = [row[0] for row in c.fetchall()]
        c.execute(
            "INSERT INTO empresas (busca_id,nome,telefone,endereco) VALUES (%s,'Clínica A','(62) 99999-1234','Rua 1, 10') RETURNING id",
            (run_ids[0],),
        )
        first = c.fetchone()[0]
        c.execute(
            "INSERT INTO empresas (busca_id,nome,telefone,endereco) VALUES (%s,'Clinica A','+55 62 99999-1234','Rua 1 10') RETURNING id",
            (run_ids[1],),
        )
        second = c.fetchone()[0]
        c.execute("INSERT INTO notas (empresa_id,texto) VALUES (%s,'nota do duplicado')", (second,))

    prepare_legacy_database(db)
    db.init_schema()

    with db.transaction() as conn:
        c = conn.cursor()
        c.execute("SELECT id,telefone,vezes_encontrada FROM empresas ORDER BY id")
        companies = c.fetchall()
        assert len(companies) == 1
        kept_id, phone, seen = companies[0]
        assert kept_id == first
        assert phone == "+5562999991234"
        assert seen >= 2

        c.execute("SELECT COUNT(*) FROM busca_empresas WHERE empresa_id=%s", (kept_id,))
        assert c.fetchone()[0] == 2

        c.execute("SELECT empresa_id,texto FROM notas")
        assert c.fetchone() == (kept_id, "nota do duplicado")

        c.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='empresas' AND indexname='uniq_empresas_phone_v2'"
        )
        assert c.fetchone() is not None
