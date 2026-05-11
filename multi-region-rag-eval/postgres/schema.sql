-- Schema for the pgvector-backed routing table.
-- The cluster, database, and the executing role are assumed to exist already.
-- The DB user only needs USAGE on the schema and the privileges below.

CREATE EXTENSION IF NOT EXISTS vector;

-- The embedding column dimensionality is templated by the ingest script so the
-- same DDL works for 1024 or 2000 dimensional vectors.
CREATE TABLE IF NOT EXISTS {table} (
    id                   BIGSERIAL PRIMARY KEY,
    account_name         TEXT NOT NULL,
    product_group        TEXT NOT NULL,
    case_reason          TEXT NOT NULL,
    operational_identity TEXT NOT NULL,
    sales_area           TEXT NOT NULL,
    service_agent_id     TEXT NOT NULL,
    region               TEXT NOT NULL,
    -- Region-specific attributes live in JSONB so that France-only columns
    -- (such as tva_number) and Italy-only columns (such as partita_iva) can
    -- coexist in a single relational table without exploding the column list.
    regional_attrs       JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    embedding            vector({dim}) NOT NULL
);

CREATE INDEX IF NOT EXISTS {table}_region_idx
    ON {table} (region);

CREATE INDEX IF NOT EXISTS {table}_regional_attrs_idx
    ON {table} USING GIN (regional_attrs);

-- HNSW index for cosine similarity. Adjust m / ef_construction for the size of
-- the corpus; the defaults below are conservative for up to ~20k rows.
CREATE INDEX IF NOT EXISTS {table}_embedding_idx
    ON {table} USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
