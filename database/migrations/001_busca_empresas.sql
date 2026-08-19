-- Uma empresa é única no CRM, mas pode aparecer em várias prospecções.
CREATE TABLE IF NOT EXISTS busca_empresas (
    busca_id      INTEGER NOT NULL REFERENCES buscas(id) ON DELETE CASCADE,
    empresa_id    INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    encontrado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (busca_id, empresa_id)
);

-- Backfill do modelo legado (empresas.busca_id).
INSERT INTO busca_empresas (busca_id, empresa_id)
SELECT busca_id, id
FROM empresas
WHERE busca_id IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_busca_empresas_empresa
    ON busca_empresas(empresa_id);
