"""Pre-flight check 2 — index inventory and 7.x-to-8.0 feature exposure.

Answers, per collection:
  * how many indexes are there, and are any of them unused?
  * do any use index types whose validation or behaviour changed in 8.0?
  * is anything relying on behaviour that 8.0 deprecates or tightens?

Read-only: only find, aggregate, and listIndexes style commands are issued.
The checks are deliberately shallow and cheap so this is safe to run against a
production replica. Anything it flags is a prompt to investigate, not a verdict.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pymongo.errors import OperationFailure, PyMongoError  # noqa: E402

from _common import (  # noqa: E402
    footer,
    get_client,
    header,
    kv,
    note,
    ok,
    section,
    table,
    target_databases,
    warn,
)

# MongoDB allows at most 64 indexes per collection; warn before you hit it.
INDEX_LIMIT = 64
INDEX_WARN_THRESHOLD = 30

SPECIAL_INDEX_TYPES = {
    "2d": "8.0 rejects malformed geospatial query input that 7.x accepted",
    "2dsphere": "8.0 rejects malformed geospatial query input that 7.x accepted",
    "text": "review text index usage; Atlas Search is the strategic option",
}


def _index_report(coll) -> tuple:
    """Return (rows, findings) describing one collection's indexes."""
    rows, findings = [], []
    ns = f"{coll.database.name}.{coll.name}"

    indexes = list(coll.list_indexes())
    usage = {}
    try:
        for stat in coll.aggregate([{"$indexStats": {}}]):
            usage[stat["name"]] = stat.get("accesses", {}).get("ops", 0)
    except OperationFailure:
        pass  # $indexStats needs indexStats privilege; counts stay blank

    if len(indexes) >= INDEX_WARN_THRESHOLD:
        findings.append(
            f"{ns} has {len(indexes)} of the {INDEX_LIMIT} allowed indexes"
        )

    for index in indexes:
        keys = index["key"]
        types = {str(v) for v in keys.values() if isinstance(v, str)}
        flags = []
        for special, reason in SPECIAL_INDEX_TYPES.items():
            if special in types:
                flags.append(special)
                findings.append(f"{ns} index {index['name']} is {special}: {reason}")
        if index.get("partialFilterExpression"):
            flags.append("partial")
        if index.get("expireAfterSeconds") is not None:
            flags.append("ttl")
        if index.get("hidden"):
            flags.append("hidden")

        ops = usage.get(index["name"])
        if ops == 0 and index["name"] != "_id_":
            flags.append("unused-since-restart")
            findings.append(
                f"{ns} index {index['name']} shows 0 accesses since the last "
                f"process restart; confirm before carrying it into 8.0"
            )

        rows.append({
            "index": index["name"],
            "keys": ", ".join(f"{k}:{v}" for k, v in keys.items()),
            "ops": "-" if ops is None else ops,
            "flags": ",".join(flags) or "-",
        })
    return rows, findings


def _undefined_scan(coll, sample_size: int) -> int:
    """Count sampled docs holding a top-level `undefined` value.

    8.0 changed how null and undefined compare in $eq, $in, and $lookup, so
    stored undefined values are the most likely source of silent result drift.
    """
    pipeline = [
        {"$sample": {"size": sample_size}},
        {"$project": {"types": {"$map": {
            "input": {"$objectToArray": "$$ROOT"},
            "as": "kv",
            "in": {"$type": "$$kv.v"},
        }}}},
        {"$match": {"types": "undefined"}},
        {"$count": "n"},
    ]
    result = list(coll.aggregate(pipeline))
    return result[0]["n"] if result else 0


def _index_filters(db, coll_name: str) -> list:
    """Index filters are deprecated in 8.0; query settings replace them."""
    try:
        return db.command({"planCacheListFilters": coll_name}).get("filters", [])
    except OperationFailure:
        return []


def _stray_bucket_collections(db) -> list:
    """system.buckets.* namespaces without time series options block upgrades."""
    try:
        return [
            info["name"]
            for info in db.list_collections(filter={"$and": [
                {"name": {"$regex": r"^system\.buckets"}},
                {"options.timeseries": {"$exists": False}},
            ]})
        ]
    except OperationFailure:
        return []


def _stored_javascript(db) -> int:
    """Stored server-side JS; $where/$function/$accumulator are deprecated."""
    try:
        return db["system.js"].count_documents({})
    except OperationFailure:
        return 0


def _inspect_database(name: str, sample_size: int) -> list:
    findings = []
    db = get_client()[name]

    try:
        collections = sorted(
            info["name"]
            for info in db.list_collections()
            if not info["name"].startswith("system.")
            and info.get("type") != "view"
        )
    except OperationFailure as exc:
        warn(f"cannot list collections in {name}: {exc.details.get('errmsg')}")
        return findings

    section(f"Database: {name}")
    kv("collections inspected", len(collections))

    stray = _stray_bucket_collections(db)
    if stray:
        findings.append(
            f"{name} has system.buckets namespaces that are not time series "
            f"collections ({', '.join(stray)}); drop or rename them per the "
            f"8.0 release notes"
        )
        warn(findings[-1])

    js_count = _stored_javascript(db)
    if js_count:
        findings.append(
            f"{name}.system.js holds {js_count} stored function(s); server-side "
            f"JavaScript is deprecated in 8.0"
        )
        warn(findings[-1])

    for coll_name in collections:
        coll = db[coll_name]
        print()
        print(f"  {name}.{coll_name}")

        try:
            count = coll.estimated_document_count()
        except OperationFailure:
            count = "unknown"
        kv("estimated documents", count)

        rows, index_findings = _index_report(coll)
        findings.extend(index_findings)
        table(rows, ["index", "keys", "ops", "flags"])

        filters = _index_filters(db, coll_name)
        if filters:
            findings.append(
                f"{name}.{coll_name} has {len(filters)} index filter(s); index "
                f"filters are deprecated in 8.0 — migrate to query settings"
            )
            warn(findings[-1])

        try:
            undefined = _undefined_scan(coll, sample_size)
        except OperationFailure:
            undefined = None
        if undefined:
            findings.append(
                f"{name}.{coll_name} has {undefined} of {sample_size} sampled "
                f"documents containing an undefined value; 8.0 changed how "
                f"null and undefined compare in $eq, $in, and $lookup"
            )
            warn(findings[-1])
        elif undefined == 0:
            ok(f"no undefined values in a {sample_size} document sample")

    return findings


def run(databases: list, sample_size: int) -> list:
    findings = []
    header("Check 2 — index inventory and 7.x-to-8.0 feature exposure")
    note("read-only inspection; sampled checks are indicative, not exhaustive")

    names = target_databases(databases)
    if not names:
        warn("no non-system databases found to inspect")
        return findings

    kv("databases targeted", ", ".join(names))
    kv("sample size per collection", sample_size)

    for name in names:
        findings.extend(_inspect_database(name, sample_size))

    footer(findings)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report index inventory and 8.0 feature exposure (read-only)."
    )
    parser.add_argument(
        "--db", action="append", dest="databases",
        help="database to inspect; repeatable. Defaults to DB_NAMES, then to "
             "every non-system database.",
    )
    parser.add_argument(
        "--sample-size", type=int, default=200,
        help="documents to sample per collection for the undefined-value check "
             "(default: 200)",
    )
    args = parser.parse_args()

    try:
        run(args.databases, args.sample_size)
    except PyMongoError as exc:
        sys.exit(f"Could not query the cluster: {exc}")


if __name__ == "__main__":
    main()
