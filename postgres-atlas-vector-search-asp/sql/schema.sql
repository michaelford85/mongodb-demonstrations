-- Synthetic demo schema for PostgreSQL CDC.
-- Applied by scripts/seed_postgres.py. No real data, no real names.

CREATE TABLE IF NOT EXISTS demo_schema.knowledge_items (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type  TEXT        NOT NULL CHECK (entity_type IN ('article', 'faq')),
    title        TEXT        NOT NULL,
    body         TEXT        NOT NULL,
    tags         TEXT        NOT NULL DEFAULT '',
    department   TEXT        NOT NULL DEFAULT 'general',
    author       TEXT        NOT NULL DEFAULT 'demo-author',
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_items_type_idx
    ON demo_schema.knowledge_items (entity_type);

-- Logical replication needs a REPLICA IDENTITY so DMS CDC can emit the
-- full row image on UPDATE and DELETE events.
ALTER TABLE demo_schema.knowledge_items REPLICA IDENTITY FULL;
