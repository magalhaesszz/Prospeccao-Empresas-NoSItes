import os,pytest
from prospector.db import Database
@pytest.mark.skipif(not os.getenv("DATABASE_URL"),reason="DATABASE_URL required")
def test_schema_and_cross_run_deduplication():
    db=Database(os.environ["DATABASE_URL"])
    with db.transaction() as conn:
        c=conn.cursor();c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    db.init_schema();r1=db.create_run("Goiânia","Clínica");a=db.upsert_company({"nome":"Clínica A","telefone":"(62) 99999-1234","endereco":"Rua 1, 10","tem_site":False,"score":80},r1,"Goiânia","Clínica","c1");assert a["is_new"] is True;r2=db.create_run("Goiânia","Clínica");b=db.upsert_company({"nome":"Clinica A","telefone":"+55 62 99999-1234","endereco":"Rua 1 10","tem_site":False,"score":85},r2,"Goiânia","Clínica","c2");assert b["id"]==a["id"];assert b["is_new"] is False;assert len(db.run_results(r2,include_known=True))==1;assert db.run_results(r2,include_known=False)==[]
