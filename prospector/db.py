from __future__ import annotations

import contextlib
import json
from datetime import datetime
from typing import Any, Iterable

from .identity import canonical_company, company_fingerprint, maps_place_id, normalize_phone, normalize_text


class DatabaseError(RuntimeError):
    pass


class Database:
    def __init__(self, database_url: str):
        self.database_url = (database_url or "").strip()

    def connect(self):
        if not self.database_url:
            raise DatabaseError("DATABASE_URL não configurada")
        try:
            import psycopg2
        except ImportError as exc:
            raise DatabaseError("psycopg2 não instalado") from exc
        return psycopg2.connect(self.database_url, connect_timeout=10)

    @contextlib.contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _rows(cur) -> list[dict]:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    @staticmethod
    def _row(cur) -> dict | None:
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([d[0] for d in cur.description], row))

    def ping(self) -> bool:
        with self.transaction() as conn:
            c = conn.cursor(); c.execute("SELECT 1")
            return c.fetchone()[0] == 1

    def init_schema(self) -> None:
        """Idempotent migration that preserves the legacy empresas/buscas data."""
        statements = [
            """CREATE TABLE IF NOT EXISTS buscas (id SERIAL PRIMARY KEY,cidade TEXT NOT NULL,categoria TEXT NOT NULL,total_encontradas INTEGER DEFAULT 0,sem_site INTEGER DEFAULT 0,data_busca TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS empresas (id SERIAL PRIMARY KEY,busca_id INTEGER REFERENCES buscas(id),nome TEXT NOT NULL,telefone TEXT,endereco TEXT,email TEXT,tem_site INTEGER DEFAULT 0,site_url TEXT,score INTEGER DEFAULT 0,status TEXT DEFAULT 'novo',mensagem_enviada INTEGER DEFAULT 0,tentativas_envio INTEGER DEFAULT 0,erro_envio TEXT,ultimo_contato TIMESTAMP,template_usado INTEGER,data_prospeccao TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS busca_empresas (busca_id INTEGER NOT NULL REFERENCES buscas(id) ON DELETE CASCADE,empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,is_new INTEGER NOT NULL DEFAULT 0,cell_key TEXT,matched_by TEXT,found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY (busca_id,empresa_id))""",
            """CREATE TABLE IF NOT EXISTS coverage_cells (id SERIAL PRIMARY KEY,cidade_norm TEXT NOT NULL,categoria_norm TEXT NOT NULL,cell_key TEXT NOT NULL,lat DOUBLE PRECISION NOT NULL,lng DOUBLE PRECISION NOT NULL,vezes_varrida INTEGER DEFAULT 0,resultados_vistos INTEGER DEFAULT 0,resultados_novos INTEGER DEFAULT 0,ultima_varredura TIMESTAMP,UNIQUE (cidade_norm,categoria_norm,cell_key))""",
            """CREATE TABLE IF NOT EXISTS wa_permissions (telefone TEXT PRIMARY KEY,status TEXT NOT NULL DEFAULT 'unknown',source TEXT,evidence TEXT,granted_at TIMESTAMP,revoked_at TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS wa_events (id BIGSERIAL PRIMARY KEY,empresa_id INTEGER REFERENCES empresas(id) ON DELETE SET NULL,telefone TEXT,provider TEXT,direction TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'text',status TEXT NOT NULL,message_preview TEXT,external_id TEXT,error TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS ai_events (id BIGSERIAL PRIMARY KEY,empresa_id INTEGER REFERENCES empresas(id) ON DELETE SET NULL,provider TEXT,model TEXT,purpose TEXT,status TEXT,latency_ms INTEGER,error TEXT,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS paginas_preview (id SERIAL PRIMARY KEY,empresa_id INTEGER REFERENCES empresas(id) ON DELETE SET NULL,nome_empresa TEXT NOT NULL,slug TEXT UNIQUE NOT NULL,html TEXT NOT NULL,vistas INTEGER DEFAULT 0,criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS notas (id SERIAL PRIMARY KEY,empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,texto TEXT NOT NULL,criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS templates (id SERIAL PRIMARY KEY,nome TEXT NOT NULL,mensagem TEXT NOT NULL,ativo INTEGER DEFAULT 0,enviados INTEGER DEFAULT 0,criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS blacklist (id SERIAL PRIMARY KEY,telefone TEXT UNIQUE NOT NULL,motivo TEXT,adicionado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY,valor TEXT)""",
        ]
        columns = {
            "descricao_google":"TEXT","nota":"REAL","avaliacoes":"INTEGER DEFAULT 0","maps_url":"TEXT","foto_url":"TEXT","fotos_urls":"TEXT",
            "gemini_mensagem":"TEXT","gemini_pagina_slug":"TEXT","place_id":"TEXT","fingerprint":"TEXT","cidade_norm":"TEXT","categoria_norm":"TEXT",
            "primeira_busca_id":"INTEGER","ultima_busca_id":"INTEGER","vezes_encontrada":"INTEGER DEFAULT 1","atualizado_em":"TIMESTAMP DEFAULT CURRENT_TIMESTAMP","wa_eligible":"INTEGER DEFAULT 0",
        }
        with self.transaction() as conn:
            c = conn.cursor()
            for sql in statements: c.execute(sql)
            for name, spec in columns.items(): c.execute(f"ALTER TABLE empresas ADD COLUMN IF NOT EXISTS {name} {spec}")
            for sql in (
                "CREATE INDEX IF NOT EXISTS idx_empresas_status ON empresas(status)",
                "CREATE INDEX IF NOT EXISTS idx_empresas_cidade_norm ON empresas(cidade_norm)",
                "CREATE INDEX IF NOT EXISTS idx_busca_empresas_busca ON busca_empresas(busca_id)",
                "CREATE INDEX IF NOT EXISTS idx_wa_events_created ON wa_events(created_at)",
            ): c.execute(sql)
        self._backfill_identity()
        self.deduplicate()
        with self.transaction() as conn:
            c = conn.cursor()
            for idx, col in (("uniq_empresas_phone_v2","telefone"),("uniq_empresas_place_v2","place_id"),("uniq_empresas_fingerprint_v2","fingerprint")):
                c.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {idx} ON empresas({col}) WHERE {col} IS NOT NULL AND {col} <> ''")

    def _backfill_identity(self) -> None:
        with self.transaction() as conn:
            c = conn.cursor(); c.execute("SELECT id,nome,telefone,endereco,maps_url,busca_id FROM empresas")
            for row in self._rows(c):
                c.execute("""UPDATE empresas SET telefone=%s,place_id=COALESCE(place_id,%s),fingerprint=COALESCE(fingerprint,%s),primeira_busca_id=COALESCE(primeira_busca_id,busca_id),ultima_busca_id=COALESCE(ultima_busca_id,busca_id),vezes_encontrada=GREATEST(COALESCE(vezes_encontrada,1),1) WHERE id=%s""",
                          (normalize_phone(row["telefone"]),maps_place_id(row["maps_url"]),company_fingerprint(row["nome"],row["endereco"]),row["id"]))

    def deduplicate(self) -> dict[str, int]:
        stats = {"telefone":0,"place_id":0,"fingerprint":0}
        with self.transaction() as conn:
            c = conn.cursor()
            for col in stats:
                c.execute(f"SELECT {col},array_agg(id ORDER BY id) FROM empresas WHERE {col} IS NOT NULL AND {col}<>'' GROUP BY {col} HAVING COUNT(*)>1")
                for _, ids in c.fetchall():
                    keep, *losers = ids
                    for loser in losers:
                        c.execute("UPDATE notas SET empresa_id=%s WHERE empresa_id=%s",(keep,loser))
                        c.execute("UPDATE paginas_preview SET empresa_id=%s WHERE empresa_id=%s",(keep,loser))
                        c.execute("""INSERT INTO busca_empresas (busca_id,empresa_id,is_new,cell_key,matched_by,found_at) SELECT busca_id,%s,0,cell_key,matched_by,found_at FROM busca_empresas WHERE empresa_id=%s ON CONFLICT (busca_id,empresa_id) DO NOTHING""",(keep,loser))
                        c.execute("DELETE FROM busca_empresas WHERE empresa_id=%s",(loser,))
                        c.execute("""UPDATE empresas k SET mensagem_enviada=GREATEST(COALESCE(k.mensagem_enviada,0),COALESCE(l.mensagem_enviada,0)),tentativas_envio=COALESCE(k.tentativas_envio,0)+COALESCE(l.tentativas_envio,0),vezes_encontrada=COALESCE(k.vezes_encontrada,1)+COALESCE(l.vezes_encontrada,1),ultimo_contato=GREATEST(k.ultimo_contato,l.ultimo_contato),atualizado_em=CURRENT_TIMESTAMP FROM empresas l WHERE k.id=%s AND l.id=%s""",(keep,loser))
                        c.execute("DELETE FROM empresas WHERE id=%s",(loser,)); stats[col]+=1
        return stats

    def create_run(self, city: str, category: str) -> int:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("INSERT INTO buscas (cidade,categoria) VALUES (%s,%s) RETURNING id",(city,category)); return c.fetchone()[0]

    def finish_run(self, run_id: int, total: int, without_site: int) -> None:
        with self.transaction() as conn:
            conn.cursor().execute("UPDATE buscas SET total_encontradas=%s,sem_site=%s WHERE id=%s",(total,without_site,run_id))

    def upsert_company(self, company: dict, run_id: int, city: str, category: str, cell_key: str | None=None) -> dict:
        d=canonical_company(company)
        if not d.get("nome"): return {"id":None,"is_new":False,"matched_by":"invalid"}
        city_n, cat_n = normalize_text(city), normalize_text(category)
        with self.transaction() as conn:
            c=conn.cursor(); existing=None; matched=None
            for col,val in (("telefone",d.get("telefone")),("place_id",d.get("place_id")),("fingerprint",d.get("fingerprint"))):
                if not val: continue
                c.execute(f"SELECT id FROM empresas WHERE {col}=%s LIMIT 1",(val,)); row=c.fetchone()
                if row: existing=row[0]; matched=col; break
            photos=d.get("fotos_urls") if isinstance(d.get("fotos_urls"),str) else json.dumps(d.get("fotos_urls") or [])
            if existing:
                c.execute("""UPDATE empresas SET nome=COALESCE(NULLIF(%s,''),nome),telefone=COALESCE(%s,telefone),endereco=COALESCE(NULLIF(%s,''),endereco),email=COALESCE(NULLIF(%s,''),email),tem_site=%s,site_url=COALESCE(NULLIF(%s,''),site_url),score=GREATEST(COALESCE(score,0),%s),descricao_google=COALESCE(NULLIF(%s,''),descricao_google),nota=COALESCE(%s,nota),avaliacoes=GREATEST(COALESCE(avaliacoes,0),COALESCE(%s,0)),maps_url=COALESCE(NULLIF(%s,''),maps_url),foto_url=COALESCE(NULLIF(%s,''),foto_url),fotos_urls=COALESCE(NULLIF(%s,''),fotos_urls),place_id=COALESCE(%s,place_id),fingerprint=COALESCE(%s,fingerprint),cidade_norm=%s,categoria_norm=%s,ultima_busca_id=%s,vezes_encontrada=COALESCE(vezes_encontrada,1)+1,atualizado_em=CURRENT_TIMESTAMP WHERE id=%s""",
                          (d.get("nome"),d.get("telefone"),d.get("endereco"),d.get("email"),1 if d.get("tem_site") else 0,d.get("site_url"),int(d.get("score") or 0),d.get("descricao_google"),d.get("nota"),d.get("avaliacoes"),d.get("maps_url"),d.get("foto_url"),photos,d.get("place_id"),d.get("fingerprint"),city_n,cat_n,run_id,existing))
                company_id,is_new=existing,False
            else:
                c.execute("""INSERT INTO empresas (busca_id,nome,telefone,endereco,email,tem_site,site_url,score,status,descricao_google,nota,avaliacoes,maps_url,foto_url,fotos_urls,place_id,fingerprint,cidade_norm,categoria_norm,primeira_busca_id,ultima_busca_id,vezes_encontrada) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'novo',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) RETURNING id""",
                          (run_id,d.get("nome"),d.get("telefone"),d.get("endereco"),d.get("email"),1 if d.get("tem_site") else 0,d.get("site_url"),int(d.get("score") or 0),d.get("descricao_google"),d.get("nota"),int(d.get("avaliacoes") or 0),d.get("maps_url"),d.get("foto_url"),photos,d.get("place_id"),d.get("fingerprint"),city_n,cat_n,run_id,run_id))
                company_id,is_new,matched=c.fetchone()[0],True,"new"
            c.execute("""INSERT INTO busca_empresas (busca_id,empresa_id,is_new,cell_key,matched_by) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (busca_id,empresa_id) DO UPDATE SET cell_key=COALESCE(busca_empresas.cell_key,EXCLUDED.cell_key),matched_by=COALESCE(busca_empresas.matched_by,EXCLUDED.matched_by)""",(run_id,company_id,1 if is_new else 0,cell_key,matched))
            return {"id":company_id,"is_new":is_new,"matched_by":matched}

    def record_coverage(self, city: str, category: str, cell, seen: int, new: int) -> None:
        with self.transaction() as conn:
            conn.cursor().execute("""INSERT INTO coverage_cells (cidade_norm,categoria_norm,cell_key,lat,lng,vezes_varrida,resultados_vistos,resultados_novos,ultima_varredura) VALUES (%s,%s,%s,%s,%s,1,%s,%s,CURRENT_TIMESTAMP) ON CONFLICT (cidade_norm,categoria_norm,cell_key) DO UPDATE SET vezes_varrida=coverage_cells.vezes_varrida+1,resultados_vistos=coverage_cells.resultados_vistos+EXCLUDED.resultados_vistos,resultados_novos=coverage_cells.resultados_novos+EXCLUDED.resultados_novos,ultima_varredura=CURRENT_TIMESTAMP,lat=EXCLUDED.lat,lng=EXCLUDED.lng""",(normalize_text(city),normalize_text(category),cell.key,cell.lat,cell.lng,seen,new))

    def coverage_history(self, city: str, category: str) -> dict[str,int]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT cell_key,vezes_varrida FROM coverage_cells WHERE cidade_norm=%s AND categoria_norm=%s",(normalize_text(city),normalize_text(category))); return {a:int(b or 0) for a,b in c.fetchall()}

    def run_results(self, run_id: int, include_known: bool=False) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); sql="SELECT e.*,be.is_new,be.matched_by,be.cell_key FROM busca_empresas be JOIN empresas e ON e.id=be.empresa_id WHERE be.busca_id=%s" + ("" if include_known else " AND be.is_new=1") + " ORDER BY be.is_new DESC,e.score DESC,e.nome"; c.execute(sql,(run_id,)); return self._rows(c)

    def run_summary(self, run_id: int) -> dict:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM buscas WHERE id=%s",(run_id,)); run=self._row(c)
            if not run: return {}
            c.execute("SELECT COUNT(*) found,COUNT(*) FILTER (WHERE is_new=1) new,COUNT(*) FILTER (WHERE is_new=0) known FROM busca_empresas WHERE busca_id=%s",(run_id,)); run.update(self._row(c) or {}); return run

    def list_runs(self, limit: int=30) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("""SELECT b.*,COUNT(be.empresa_id) found,COUNT(be.empresa_id) FILTER (WHERE be.is_new=1) new,COUNT(be.empresa_id) FILTER (WHERE be.is_new=0) known FROM buscas b LEFT JOIN busca_empresas be ON be.busca_id=b.id GROUP BY b.id ORDER BY b.data_busca DESC LIMIT %s""",(max(1,min(limit,200)),)); return self._rows(c)

    def list_companies(self, *, q: str="", status: str="", city: str="", eligible: str="", limit: int=100, offset: int=0) -> list[dict]:
        sql="SELECT * FROM empresas WHERE 1=1"; params:list[Any]=[]
        if q: sql+=" AND (nome ILIKE %s OR telefone ILIKE %s OR endereco ILIKE %s)"; token=f"%{q}%"; params += [token,token,token]
        if status: sql+=" AND status=%s"; params.append(status)
        if city: sql+=" AND cidade_norm=%s"; params.append(normalize_text(city))
        if eligible in {"0","1"}: sql+=" AND wa_eligible=%s"; params.append(int(eligible))
        sql+=" ORDER BY score DESC,atualizado_em DESC NULLS LAST,id DESC LIMIT %s OFFSET %s"; params += [max(1,min(limit,500)),max(0,offset)]
        with self.transaction() as conn:
            c=conn.cursor(); c.execute(sql,params); return self._rows(c)

    def get_company(self, company_id: int) -> dict | None:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM empresas WHERE id=%s",(company_id,)); return self._row(c)

    def update_company_status(self, company_id: int, status: str) -> bool:
        if status not in {"novo","qualificado","contatado","interessado","fechado","perdido","arquivado"}: raise ValueError("status inválido")
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("UPDATE empresas SET status=%s,atualizado_em=CURRENT_TIMESTAMP WHERE id=%s",(status,company_id)); return c.rowcount==1

    def set_permission(self, phone: str, status: str, source: str, evidence: str="") -> None:
        phone=normalize_phone(phone)
        if not phone: raise ValueError("telefone inválido")
        if status not in {"opted_in","opted_out","unknown"}: raise ValueError("status de permissão inválido")
        granted="CURRENT_TIMESTAMP" if status=="opted_in" else "NULL"; revoked="CURRENT_TIMESTAMP" if status=="opted_out" else "NULL"
        with self.transaction() as conn:
            c=conn.cursor(); c.execute(f"""INSERT INTO wa_permissions (telefone,status,source,evidence,granted_at,revoked_at,updated_at) VALUES (%s,%s,%s,%s,{granted},{revoked},CURRENT_TIMESTAMP) ON CONFLICT (telefone) DO UPDATE SET status=EXCLUDED.status,source=EXCLUDED.source,evidence=EXCLUDED.evidence,granted_at={granted},revoked_at={revoked},updated_at=CURRENT_TIMESTAMP""",(phone,status,source,evidence[:1000])); c.execute("UPDATE empresas SET wa_eligible=%s WHERE telefone=%s",(1 if status=="opted_in" else 0,phone))

    def get_permission(self, phone: str | None) -> dict | None:
        phone=normalize_phone(phone)
        if not phone: return None
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM wa_permissions WHERE telefone=%s",(phone,)); return self._row(c)

    def is_blacklisted(self, phone: str | None) -> bool:
        phone=normalize_phone(phone)
        if not phone: return False
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT 1 FROM blacklist WHERE telefone=%s LIMIT 1",(phone,)); return c.fetchone() is not None

    def add_blacklist(self, phone: str, reason: str="") -> bool:
        phone=normalize_phone(phone)
        if not phone: raise ValueError("telefone inválido")
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("INSERT INTO blacklist (telefone,motivo) VALUES (%s,%s) ON CONFLICT (telefone) DO UPDATE SET motivo=EXCLUDED.motivo",(phone,reason[:300])); c.execute("UPDATE empresas SET wa_eligible=0 WHERE telefone=%s",(phone,))
        return True

    def list_blacklist(self, limit: int=200) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM blacklist ORDER BY adicionado_em DESC LIMIT %s",(max(1,min(limit,1000)),)); return self._rows(c)

    def outbound_count_today(self) -> int:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT COUNT(*) FROM wa_events WHERE direction='out' AND status='sent' AND created_at::date=CURRENT_DATE"); return int(c.fetchone()[0])

    def last_outbound_for_phone(self, phone: str) -> datetime | None:
        phone=normalize_phone(phone)
        if not phone: return None
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT MAX(created_at) FROM wa_events WHERE direction='out' AND status='sent' AND telefone=%s",(phone,)); return c.fetchone()[0]

    def log_wa_event(self, *, company_id: int|None, phone: str|None, provider: str, direction: str, status: str, preview: str="", error: str="", external_id: str="", kind: str="text") -> int:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("INSERT INTO wa_events (empresa_id,telefone,provider,direction,kind,status,message_preview,error,external_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",(company_id,normalize_phone(phone) if phone else None,provider,direction,kind,status,preview[:500],error[:500],external_id[:200])); return c.fetchone()[0]

    def recent_wa_events(self, limit: int=100) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM wa_events ORDER BY created_at DESC LIMIT %s",(max(1,min(limit,500)),)); return self._rows(c)

    def log_ai_event(self, *, company_id: int|None, provider: str, model: str, purpose: str, status: str, latency_ms: int, error: str="") -> None:
        with self.transaction() as conn:
            conn.cursor().execute("INSERT INTO ai_events (empresa_id,provider,model,purpose,status,latency_ms,error) VALUES (%s,%s,%s,%s,%s,%s,%s)",(company_id,provider,model,purpose,status,latency_ms,error[:500]))

    def save_preview(self, company_id: int, name: str, slug: str, html: str) -> None:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("INSERT INTO paginas_preview (empresa_id,nome_empresa,slug,html) VALUES (%s,%s,%s,%s) ON CONFLICT (slug) DO UPDATE SET html=EXCLUDED.html,nome_empresa=EXCLUDED.nome_empresa",(company_id,name,slug,html)); c.execute("UPDATE empresas SET gemini_pagina_slug=%s WHERE id=%s",(slug,company_id))

    def get_preview(self, slug: str) -> dict | None:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("UPDATE paginas_preview SET vistas=vistas+1 WHERE slug=%s",(slug,)); c.execute("SELECT * FROM paginas_preview WHERE slug=%s",(slug,)); return self._row(c)

    def add_note(self, company_id: int, text: str) -> int:
        text=(text or "").strip()
        if not text: raise ValueError("nota vazia")
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("INSERT INTO notas (empresa_id,texto) VALUES (%s,%s) RETURNING id",(company_id,text[:4000])); return c.fetchone()[0]

    def list_notes(self, company_id: int) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM notas WHERE empresa_id=%s ORDER BY criado_em DESC",(company_id,)); return self._rows(c)

    def list_templates(self) -> list[dict]:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("SELECT * FROM templates ORDER BY ativo DESC,criado_em DESC"); return self._rows(c)

    def save_template(self, name: str, message: str, active: bool=False) -> int:
        if not name.strip() or not message.strip(): raise ValueError("nome e mensagem são obrigatórios")
        with self.transaction() as conn:
            c=conn.cursor()
            if active: c.execute("UPDATE templates SET ativo=0")
            c.execute("INSERT INTO templates (nome,mensagem,ativo) VALUES (%s,%s,%s) RETURNING id",(name.strip()[:120],message.strip()[:5000],1 if active else 0)); return c.fetchone()[0]

    def delete_template(self, template_id: int) -> bool:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("DELETE FROM templates WHERE id=%s",(template_id,)); return c.rowcount==1

    def dashboard(self) -> dict:
        with self.transaction() as conn:
            c=conn.cursor(); c.execute("""SELECT COUNT(*) total,COUNT(*) FILTER (WHERE data_prospeccao::date=CURRENT_DATE) novos_hoje,COUNT(*) FILTER (WHERE tem_site=0) sem_site,COUNT(*) FILTER (WHERE wa_eligible=1) wa_elegiveis,COUNT(*) FILTER (WHERE status='interessado') interessados,COUNT(*) FILTER (WHERE status='fechado') fechados FROM empresas"""); out=self._row(c) or {}
            for key,sql in (("buscas","SELECT COUNT(*) FROM buscas"),("celulas_cobertas","SELECT COUNT(*) FROM coverage_cells"),("mensagens_enviadas","SELECT COUNT(*) FROM wa_events WHERE direction='out' AND status='sent'"),("respostas","SELECT COUNT(*) FROM wa_events WHERE direction='in'")):
                c.execute(sql); out[key]=c.fetchone()[0]
            return out

    def export_companies(self) -> Iterable[dict]:
        return self.list_companies(limit=500)
