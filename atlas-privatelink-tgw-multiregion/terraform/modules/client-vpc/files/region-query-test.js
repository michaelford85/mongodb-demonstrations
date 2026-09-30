/*
 * Explicit per-region read test, run by `atlas-plink-query` on the lab's test VM.
 *
 * The point of the lab is that one VM in region A reaches Atlas nodes in two
 * regions over PrivateLink. A connection string alone does not prove that: the
 * driver would happily serve every read from the nearest node. So this script
 * pins each read to a named node with a read preference tag, and then confirms
 * from the server's own explain output which host actually answered.
 *
 * Two targets, both secondaries, both queried explicitly:
 *   1. the secondary in the PRIMARY's region   - the same-region PrivateLink path
 *   2. a secondary in a DIFFERENT region       - the cross-region path, which
 *      only works if Transit Gateway peering and both sets of routes are right
 *
 * Atlas tags every replica set member with its provider and region, which is
 * what makes the targeting possible.
 *
 * Reads nothing from the environment except two optional, non-secret names.
 * Credentials are handled by mongosh itself and never appear here.
 */

var TEST_DB = "atlas_plink_demo";
var TEST_COLL = "probe";

try {
  if (typeof process !== "undefined" && process.env) {
    TEST_DB = process.env.ATLAS_PLINK_DB || TEST_DB;
    TEST_COLL = process.env.ATLAS_PLINK_COLL || TEST_COLL;
  }
} catch (e) {
  // Fall back to the defaults.
}

function line() {
  print("--------------------------------------------------------------------");
}

/*
 * rs.conf() reports members as "host:port"; explain().serverInfo.host reports
 * the bare hostname. Compare on the hostname alone, and fall back to the first
 * DNS label in case a server reports a short name.
 */
function hostOnly(value) {
  return String(value || "")
    .split(":")[0]
    .toLowerCase();
}

function firstLabel(value) {
  return hostOnly(value).split(".")[0];
}

function sameHost(a, b) {
  if (!a || !b) {
    return false;
  }
  if (hostOnly(a) === hostOnly(b)) {
    return true;
  }
  return firstLabel(a) === firstLabel(b);
}

function fail(message) {
  print("");
  print("FAILED: " + message);
  quit(1);
}

// ── Topology ─────────────────────────────────────────────────────────────────

var hello = db.getSiblingDB("admin").runCommand({ hello: 1 });

line();
print("Atlas PrivateLink multi-region query test");
line();
print("replica set   : " + hello.setName);
print("entry node    : " + hello.me);
print("primary       : " + hello.primary);
print("test namespace: " + TEST_DB + "." + TEST_COLL);
print("");

var conf;
var status;

try {
  conf = rs.conf();
  status = rs.status();
} catch (e) {
  fail(
    "could not read the replica set configuration: " +
      e.message +
      "\nThe database user needs the clusterMonitor role (or atlasAdmin) to see " +
      "member regions."
  );
}

var stateByHost = {};
status.members.forEach(function (m) {
  stateByHost[m.name] = m.stateStr;
});

var members = conf.members.map(function (m) {
  var tags = m.tags || {};
  return {
    host: m.host,
    region: tags.region || null,
    provider: tags.provider || null,
    nodeType: tags.nodeType || null,
    state: stateByHost[m.host] || "UNKNOWN"
  };
});

print("Replica set members");
members.forEach(function (m) {
  print(
    "  " +
      m.host +
      "  " +
      m.state +
      "  " +
      (m.provider || "?") +
      "/" +
      (m.region || "?")
  );
});
print("");

var primaryMember = members.filter(function (m) {
  return m.state === "PRIMARY";
})[0];

if (!primaryMember) {
  fail("no PRIMARY visible in rs.status().");
}

if (!primaryMember.region) {
  fail(
    "replica set members carry no region tag, so per-region targeting is not " +
      "possible. Atlas normally tags every member with provider and region; a " +
      "self-managed replica set would need those tags added by hand."
  );
}

var primaryRegion = primaryMember.region;

var sameRegionSecondary = members.filter(function (m) {
  return m.state === "SECONDARY" && m.region === primaryRegion;
})[0];

var remoteRegionSecondary = members.filter(function (m) {
  return m.state === "SECONDARY" && m.region !== primaryRegion;
})[0];

if (!sameRegionSecondary) {
  fail(
    "no SECONDARY in the primary's region (" +
      primaryRegion +
      "). This lab expects at least two electable nodes there."
  );
}

if (!remoteRegionSecondary) {
  fail(
    "no SECONDARY outside the primary's region (" +
      primaryRegion +
      "). This lab expects a multi-region replica set - the cross-region path " +
      "is the whole point."
  );
}

// ── Seed one document through the primary ────────────────────────────────────

var runId = "atlas-plink-" + new Date().toISOString();
var seeded = false;

try {
  db.getSiblingDB(TEST_DB)
    .getCollection(TEST_COLL)
    .insertOne(
      {
        _id: runId,
        createdAt: new Date(),
        writtenVia: hello.me,
        note: "written by the atlas-privatelink-tgw-multiregion lab"
      },
      { writeConcern: { w: "majority", wtimeout: 20000 } }
    );
  seeded = true;
  print("Seeded " + TEST_DB + "." + TEST_COLL + " with _id " + runId);
  print("Write concern majority, so every secondary below has it durably.");
} catch (e) {
  print("WARNING: could not write the probe document: " + e.message);
  print("The reads below still run; they just will not return a document.");
}
print("");

// ── One explicit read per target region ──────────────────────────────────────

function readFromRegion(label, member) {
  var region = member.region;
  var coll = db.getSiblingDB(TEST_DB).getCollection(TEST_COLL);
  var result = {
    label: label,
    region: region,
    expectedHost: member.host,
    servedBy: null,
    servedByRegion: null,
    servedByState: null,
    found: 0,
    millis: null,
    error: null
  };

  line();
  print(label);
  print("  target region : " + region);
  print("  expected node : " + member.host + " (" + member.state + ")");

  try {
    // Pin every read on this connection to a secondary carrying Atlas's
    // region tag. Nothing else in the session can quietly serve it instead.
    db.getMongo().setReadPref("secondary", [{ region: region }]);

    var attempt = 0;
    var docs = [];
    var plan = null;

    while (attempt < 20) {
      attempt++;
      plan = coll.find({ _id: runId }).explain("executionStats");
      docs = coll.find({ _id: runId }).toArray();
      if (!seeded || docs.length > 0) {
        break;
      }
      sleep(500);
    }

    result.servedBy = plan && plan.serverInfo ? plan.serverInfo.host : null;
    result.found = docs.length;
    result.millis =
      plan && plan.executionStats ? plan.executionStats.executionTimeMillis : null;

    var total = coll.countDocuments({});

    print("  served by     : " + (result.servedBy || "unknown"));
    print("  query         : find({_id: <this run>}) on a secondary in " + region);
    print("  documents     : " + result.found + " of this run, " + total + " in the collection");
    print("  exec time     : " + result.millis + " ms");
    if (attempt > 1) {
      print("  replication   : document appeared after " + attempt + " attempts");
    }
  } catch (e) {
    result.error = e.message;
    print("  ERROR         : " + e.message);
  } finally {
    db.getMongo().setReadPref("primary");
  }

  if (result.servedBy) {
    var servedMatches = members.filter(function (m) {
      return sameHost(m.host, result.servedBy);
    });

    if (servedMatches.length === 1) {
      result.servedByRegion = servedMatches[0].region;
      result.servedByState = servedMatches[0].state;
    } else if (servedMatches.length > 1) {
      // Shouldn't happen on Atlas, where every member has its own hostname.
      var distinct = {};
      servedMatches.forEach(function (m) {
        distinct[m.region] = true;
      });
      result.servedByRegion =
        Object.keys(distinct).length === 1 ? servedMatches[0].region : null;
      result.servedByState = servedMatches[0].state;
    } else {
      print(
        "  NOTE          : " +
          result.servedBy +
          " does not match any member in rs.conf()"
      );
    }
    print("  served region : " + (result.servedByRegion || "unknown"));
  }

  var ok =
    !result.error &&
    result.servedBy !== null &&
    result.servedByRegion === region &&
    !sameHost(result.servedBy, primaryMember.host) &&
    (!seeded || result.found === 1);

  print("  result        : " + (ok ? "PASS" : "FAIL"));
  result.ok = ok;
  return result;
}

var results = [];

results.push(
  readFromRegion(
    "1. Secondary in the PRIMARY's region - same-region PrivateLink path",
    sameRegionSecondary
  )
);

results.push(
  readFromRegion(
    "2. Secondary in a DIFFERENT region - cross-region path over Transit Gateway peering",
    remoteRegionSecondary
  )
);

// ── Summary ──────────────────────────────────────────────────────────────────

line();
print("Summary");
line();
results.forEach(function (r) {
  print(
    "  " +
      (r.ok ? "PASS" : "FAIL") +
      "  " +
      r.region +
      "  served by " +
      (r.servedBy || "nothing") +
      (r.error ? "  (" + r.error + ")" : "")
  );
});
print("");
print("Both rows PASS means this VM read from an Atlas node in each region,");
print("over AWS PrivateLink only, with the cross-region read crossing the");
print("inter-region Transit Gateway peering.");
print("");

var failures = results.filter(function (r) {
  return !r.ok;
}).length;

quit(failures === 0 ? 0 : 1);
