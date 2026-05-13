// ─────────────────────────────────────────────────────────────────────────────
// 03 — Zoned shard key (location-aware routing)
//
// Connect with:
//   mongosh "$SHARDED_URI"
//   load("03-sharding/03_zoned.js")
//
// On a GEOSHARDED Atlas cluster, each shard already lives in its own zone
// ("Zone 1", "Zone 2", ...) created at deploy time by the Terraform in
// ../atlas-sharded-cluster-provisioning. This script uses a compound shard
// key whose prefix is `location` and pins:
//
//   location = "EU"  →  Zone 1   (the EU shard)
//   location = "US"  →  Zone 2   (the US shard)
//
// The result: documents (and queries that include `location`) are routed to
// the geographically appropriate shard with no application changes.
//
// Note: this configures sharding-level zones directly via sh.updateZoneKeyRange.
// It does NOT register a Global Writes collection through the Atlas Admin API,
// so the Atlas UI's "Global Writes" tab may still show no configured
// collections. The routing behaviour at the cluster level is identical.
// ─────────────────────────────────────────────────────────────────────────────

const db_name = "architecture_demo";
const coll_name = "events";
const ns = `${db_name}.${coll_name}`;

print(`\n--- 03_zoned.js: ${ns} ---`);

const dbh = db.getSiblingDB(db_name);

sh.enableSharding(db_name);

const collInfo = dbh.getCollectionInfos({ name: coll_name })[0];
if (collInfo && collInfo.options && collInfo.options.shardKey) {
    print("Collection is already sharded — dropping to re-shard on { location, customer_id }.");
    print("Re-run ../03-sharding/seed.py afterwards to repopulate.");
    dbh[coll_name].drop();
}

// Compound key: location prefix gives us zone routing; customer_id suffix
// gives us cardinality within each zone.
sh.shardCollection(ns, { location: 1, customer_id: 1 });

// Inspect the zones the GEOSHARDED cluster came up with.
const shards = db.getSiblingDB("config").shards.find().toArray();
print("\nDiscovered shards and their zones:");
shards.forEach(s => {
    print(`  ${s._id}  tags=${JSON.stringify(s.tags || [])}`);
});

// Pin EU documents to Zone 1 and US documents to Zone 2.
// These zone names match the Terraform variable `cluster_type = "GEOSHARDED"`
// which assigns "Zone 1", "Zone 2", … to each replication_specs block.
sh.updateZoneKeyRange(
    ns,
    { location: "EU", customer_id: MinKey },
    { location: "EU", customer_id: MaxKey },
    "Zone 1",
);
sh.updateZoneKeyRange(
    ns,
    { location: "US", customer_id: MinKey },
    { location: "US", customer_id: MaxKey },
    "Zone 2",
);

print("\nShard key now: { location: 1, customer_id: 1 }");
print("Zone ranges:");
print("  location='EU' → Zone 1");
print("  location='US' → Zone 2");
print("\nWatch chunk_map.py: the balancer will migrate EU docs to the EU shard");
print("and US docs to the US shard. Migration takes ~1-2 min for 100 k docs.");
print("\nVerify routing once balanced:");
print("  db.events.find({ location: 'EU' }).explain().queryPlanner.winningPlan.shards");
