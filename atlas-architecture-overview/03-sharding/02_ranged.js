// ─────────────────────────────────────────────────────────────────────────────
// 02 — Ranged shard key (anti-pattern demo)
//
// Connect with:
//   mongosh "$SHARDED_URI"
//   load("03-sharding/02_ranged.js")
//
// Sharding on a monotonically-increasing field (created_at, ObjectId, auto-
// increment id) is the canonical sharding anti-pattern. Every new write
// targets the chunk holding the maximum key value, so 100 % of insert load
// lands on one shard. The other shards sit idle.
//
// Run this AFTER 01_hashed.js so the contrast is obvious in chunk_map.py.
// ─────────────────────────────────────────────────────────────────────────────

const db_name = "architecture_demo";
const coll_name = "events";
const ns = `${db_name}.${coll_name}`;

print(`\n--- 02_ranged.js: ${ns} ---`);

const dbh = db.getSiblingDB(db_name);

sh.enableSharding(db_name);

const collInfo = dbh.getCollectionInfos({ name: coll_name })[0];
if (collInfo && collInfo.options && collInfo.options.shardKey) {
    print("Collection is already sharded — dropping to re-shard on created_at.");
    print("Re-run ../03-sharding/seed.py afterwards to repopulate.");
    dbh[coll_name].drop();
}

// Range-based shard on created_at. With monotonically-increasing data the
// balancer will eventually split & migrate chunks, but new inserts continue
// to pile onto whichever shard owns the [max, MaxKey) chunk.
sh.shardCollection(ns, { created_at: 1 });

print("\nShard key now: { created_at: 1 } (range)");
print("Re-seed (seed.py) to insert new monotonic data and watch chunk_map.py");
print("— one shard's doc count will grow while others stay flat. That is the");
print("hotspot effect; this is why hashed sharding is usually the right default.");
