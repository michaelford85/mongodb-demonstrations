-- Demo SQL run against the Iceberg table via Trino (`make query`).
-- Each statement is separated by a line containing only "-- @@".

-- Total rows currently visible in the analytical table.
SELECT count(*) AS total_orders FROM iceberg.demo.orders;
-- @@

-- The memorable "live" order that was streamed from Atlas.
-- Replace the id if you pass a custom --order-id to `make demo`.
SELECT order_id, account_id, symbol, side, quantity, price, order_status,
       source_updated_at, iceberg_ingested_at
FROM iceberg.demo.orders
WHERE order_id LIKE 'LIVE-%'
ORDER BY iceberg_ingested_at DESC
LIMIT 5;
-- @@

-- Analytical aggregation: trading volume and notional value by symbol.
SELECT symbol,
       count(*)                         AS order_count,
       sum(quantity)                    AS total_shares,
       round(sum(quantity * price), 2)  AS notional_value,
       round(avg(price), 2)             AS avg_price
FROM iceberg.demo.orders
GROUP BY symbol
ORDER BY notional_value DESC;
-- @@

-- Fill status breakdown by side.
SELECT side, order_status, count(*) AS orders
FROM iceberg.demo.orders
GROUP BY side, order_status
ORDER BY side, order_status;
