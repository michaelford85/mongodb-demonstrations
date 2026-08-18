-- Reference DDL for the demo Iceberg table (Trino Iceberg-connector syntax).
--
-- NOTE: `make backfill` creates this table via PyIceberg the first time it runs,
-- so you do NOT need to run this by hand. It is kept here to document the schema
-- and to allow manual creation if you prefer to drive everything from SQL.

CREATE SCHEMA IF NOT EXISTS iceberg.demo;

CREATE TABLE IF NOT EXISTS iceberg.demo.orders (
    order_id            VARCHAR,   -- unique business key (used for idempotent writes)
    account_id          VARCHAR,   -- synthetic account, no PII
    symbol              VARCHAR,   -- traded security, e.g. MDB, AAPL
    side                VARCHAR,   -- BUY | SELL
    quantity            BIGINT,    -- share count
    price               DOUBLE,    -- execution price
    order_time          TIMESTAMP(6) WITH TIME ZONE,  -- when the order was placed
    order_status        VARCHAR,   -- NEW | PARTIALLY_FILLED | FILLED | CANCELLED
    source_updated_at   TIMESTAMP(6) WITH TIME ZONE,  -- Atlas write time (from change event)
    iceberg_ingested_at TIMESTAMP(6) WITH TIME ZONE   -- when the pipeline wrote it to Iceberg
)
WITH (
    format = 'PARQUET'
);
