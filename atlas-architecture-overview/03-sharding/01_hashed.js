// ─────────────────────────────────────────────────────────────────────────────
// 01 — Hashed shard key
//
// Connect with:
//   mongosh "$SHARDED_URI"
// then load this script in the shell:
//   load("03-sharding/01_hashed.js")
//
// Hashed sharding distributes documents uniformly across shards regardless of
// the data's natural skew. It is the right default for high-cardinality keys
// where you don't need range-based locality (e.g. customer_id, order_id).
//
// Trade-off: range queries (e.g. "all events for customer X in date range Y")
// must scatter-gather across every shard.
// ─────────────────────────────────────────────────────────────────────────────

const db_name = "architecture_demo";
const coll_name = "events";
const ns = `${db_name}.${coll_name}`;

print(`\n--- 01_hashed.js: ${ns} ---`);

// Ensure we start from a clean, unsharded collection.
// Drop only the collection; keep the seeded data by re-running seed.py if needed.
const dbh = db.getSiblingDB(db_name);

// Enable sharding on the database (idempotent).
sh.enableSharding(db_name);

// If the collection is already sharded, we have to drop it to change the key.
const collInfo = dbh.getCollectionInfos({ name: coll_name })[0];
if (collInfo && collInfo.options && collInfo.options.shardKey) {
    print("Collection is already sharded — dropping to re-shard with a hashed key.");
    print("Re-run ../03-sharding/seed.py afterwards to repopulate.");
    dbh[coll_name].drop();
}

// Shard on a hashed customer_id. Atlas auto-splits hashed collections into
// initial chunks across all shards, so distribution is immediately balanced.
sh.shardCollection(ns, { customer_id: "hashed" });

print("\nShard key now: { customer_id: 'hashed' }");
print("Watch chunk_map.py — counts should be close to equal across all shards.");
print("Run sh.status() for the full picture.");
