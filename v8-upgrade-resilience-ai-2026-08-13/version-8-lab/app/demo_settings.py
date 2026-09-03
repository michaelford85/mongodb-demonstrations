"""Feature 2 — query settings: guardrails on a query shape, no app deploy.

The offending query is a regex scan over an unindexed `note` field. It is cheap
here because the dataset is tiny; at production scale it is the query that
takes the cluster down.

  7.x style: the only levers are an application change (ship a fix, wait for a
             release) or index filters, which are per-mongod, lost on restart,
             and deprecated in 8.0.
  8.x style: setQuerySettings attaches a persistent, cluster-wide setting to
             the *query shape*. reject:true refuses the shape outright;
             indexHints pins a shape to an index. Both survive restarts and
             need no application change.
"""
from pymongo.errors import OperationFailure

from config import (
    DB_NAME,
    ORDERS_COLLECTION,
    ORDER_DATE_INDEX,
    get_client,
    get_db,
    get_orders,
)
from render import header, pipeline_block, section

# The query shape under discussion: an unindexed regex scan.
BAD_FILTER = {"note": {"$regex": "delivery"}}

_REPRESENTATIVE_QUERY = {
    "find": ORDERS_COLLECTION,
    "filter": BAD_FILTER,
    "$db": DB_NAME,
}


def _explain(filter_doc: dict) -> dict:
    return get_db().command(
        {"explain": {"find": ORDERS_COLLECTION, "filter": filter_doc},
         "verbosity": "executionStats"}
    )


def _plan_summary(explain: dict) -> tuple:
    winning = explain["queryPlanner"]["winningPlan"]
    stage = winning.get("queryPlan", winning)
    stages = []
    while stage:
        stages.append(stage["stage"])
        stage = stage.get("inputStage")
    stats = explain.get("executionStats", {})
    return " -> ".join(stages), stats.get("totalDocsExamined"), stats.get("nReturned")


def _set_settings(settings: dict) -> None:
    get_client().admin.command(
        {"setQuerySettings": _REPRESENTATIVE_QUERY, "settings": settings}
    )


def _remove_settings() -> None:
    try:
        get_client().admin.command({"removeQuerySettings": _REPRESENTATIVE_QUERY})
    except OperationFailure:
        pass


def _list_settings() -> list:
    return list(get_client().admin.aggregate(
        [{"$querySettings": {"showDebugQueryShape": True}}]
    ))


def _try_query() -> None:
    try:
        count = len(list(get_orders().find(BAD_FILTER)))
        print(f"  query ran, returned {count} documents")
    except OperationFailure as exc:
        print(f"  query refused by the server: {exc.details.get('codeName')} "
              f"(code {exc.code})")
        print(f"    {exc.details.get('errmsg')}")


def run(keep: bool = False) -> None:
    header("Feature 2 — query settings: block or pin a query shape")
    print(f"  offending shape: db.{ORDERS_COLLECTION}.find({BAD_FILTER})")

    _remove_settings()

    section("BEFORE (7.x style) — the shape runs, and keeps running")
    plan, examined, returned = _plan_summary(_explain(BAD_FILTER))
    print(f"  plan .......... {plan}")
    print(f"  docs examined . {examined}  (returned {returned})")
    _try_query()
    print("  mitigation .... change the application, or set an index filter")
    print("                  (per-mongod, lost on restart, deprecated in 8.0)")

    section("AFTER (8.x) — reject the shape with setQuerySettings")
    _set_settings({"reject": True,
                   "comment": "unindexed regex scan blocked by platform team"})
    print("  db.adminCommand(")
    pipeline_block({"setQuerySettings": _REPRESENTATIVE_QUERY,
                    "settings": {"reject": True,
                                 "comment": "unindexed regex scan blocked "
                                            "by platform team"}})
    print("  )")
    _try_query()

    section("AFTER (8.x) — or pin the shape to an index instead")
    # setQuerySettings merges into whatever is already registered for the
    # shape, so the reject above has to be cleared first or the query never
    # runs and the pin cannot be observed.
    _remove_settings()
    _set_settings({
        "indexHints": {
            "ns": {"db": DB_NAME, "coll": ORDERS_COLLECTION},
            "allowedIndexes": [ORDER_DATE_INDEX],
        },
        "comment": "restrict shape to order_date index or a collection scan",
    })
    print(f"  the planner may now only consider {ORDER_DATE_INDEX} for this")
    print("  shape; no index covers note, so it falls back to a full scan")
    plan, examined, returned = _plan_summary(_explain(BAD_FILTER))
    print(f"  plan .......... {plan}")
    print(f"  docs examined . {examined}  (returned {returned})")
    _try_query()
    print("  note .......... setQuerySettings merges into the settings already")
    print("                  registered for a shape; the reject above was")
    print("                  removed first so this query could run")

    section("Settings currently registered on the cluster")
    for entry in _list_settings():
        print(f"  queryShapeHash .. {entry.get('queryShapeHash')}")
        print(f"  settings ........ {entry.get('settings')}")
        print(f"  debugQueryShape . {entry.get('debugQueryShape')}")

    section("DIFF")
    print("  scope ............ per-mongod index filter -> cluster-wide setting")
    print("  survives restart . no -> yes")
    print("  app change ....... required -> none")
    print("  granularity ...... collection + index -> query shape hash")

    if keep:
        print("\n  settings left in place; remove them with:")
        print("    python app/main.py clean")
    else:
        _remove_settings()
        print("\n  query settings removed; the cluster is back to its "
              "original state")
