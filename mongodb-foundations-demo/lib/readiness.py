"""Demo-readiness checks: run these before the session starts.

Each check returns {name, ok, detail, fix}. Nothing here writes data and nothing
here reveals a secret — the URI check reports presence only.
"""

from __future__ import annotations

from pymongo.errors import PyMongoError

from lib.mongo_client import (ACCOUNTS, COLLECTIONS, DB_NAME, counts,
                              get_client, get_db, uri_present)
from lib.schema import VALIDATORS, missing_validators
from lib.seed import missing_indexes
from lib.transactions import DEMO_ACCOUNTS, transaction_support

WRITE_ROLES = {"readWrite", "readWriteAnyDatabase", "dbOwner", "root",
               "atlasAdmin", "dbAdminAnyDatabase"}

SEED_HINT = "Seed from the Demo Readiness page, or run `python3 seed_data.py`."


def _row(name: str, ok: bool, detail: str, fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def check_uri() -> dict:
    present = uri_present()
    return _row("MONGODB_URI available", present,
                "Set (value never displayed)" if present else "Not set",
                "" if present else "Copy .env.example to .env and set MONGODB_URI.")


def check_connection() -> dict:
    if not uri_present():
        return _row("Connection", False, "Skipped — no MONGODB_URI",
                    "Set MONGODB_URI first.")
    try:
        get_client().admin.command("ping")
        return _row("Connection", True,
                    "Reachable · target database `{}`".format(DB_NAME))
    except PyMongoError as exc:
        return _row("Connection", False, str(exc),
                    "Check the URI, the database user, and that your IP is on "
                    "the deployment's access list.")


def check_permissions() -> dict:
    """Confirm the connected user can read and write the demo database."""
    try:
        status = get_client()[DB_NAME].command("connectionStatus",
                                               showPrivileges=True)
    except PyMongoError as exc:
        return _row("Database permissions", False, str(exc),
                    "Use a database user with readWrite on `{}`."
                    .format(DB_NAME))

    auth_info = status.get("authInfo", {})
    roles = ["{}@{}".format(r.get("role"), r.get("db"))
             for r in auth_info.get("authenticatedUserRoles", [])]
    role_names = {r.get("role") for r in auth_info.get("authenticatedUserRoles", [])}

    can_write = bool(role_names & WRITE_ROLES)
    if not can_write:
        for priv in auth_info.get("authenticatedUserPrivileges", []):
            resource = priv.get("resource", {})
            scoped = resource.get("db") in ("", DB_NAME) or \
                resource.get("anyResource")
            if scoped and "insert" in priv.get("actions", []):
                can_write = True
                break

    detail = "Roles: {}".format(", ".join(roles) or "none reported")
    return _row("Database permissions", can_write, detail,
                "" if can_write else
                "Grant readWrite on `{}` to this user.".format(DB_NAME))


def check_seed() -> dict:
    try:
        found = counts()
    except PyMongoError as exc:
        return _row("Seed data", False, str(exc), SEED_HINT)
    detail = " · ".join("{}={}".format(k, v) for k, v in found.items())
    ok = all(found.get(name, 0) > 0 for name in COLLECTIONS)
    return _row("Seed data", ok, detail, "" if ok else SEED_HINT)


def check_indexes() -> dict:
    try:
        missing = missing_indexes()
    except PyMongoError as exc:
        return _row("Demo indexes", False, str(exc), SEED_HINT)
    ok = not missing
    return _row("Demo indexes", ok,
                "All 5 present" if ok else "Missing: {}".format(missing),
                "" if ok else SEED_HINT)


def check_validators() -> dict:
    """Confirm every demo collection carries its `$jsonSchema` validator."""
    try:
        missing = missing_validators(get_db())
    except PyMongoError as exc:
        return _row("Schema validators", False, str(exc), SEED_HINT)
    ok = not missing
    return _row("Schema validators", ok,
                "All {} active".format(len(VALIDATORS)) if ok
                else "Missing: {}".format(missing),
                "" if ok else SEED_HINT)


def check_transactions() -> dict:
    support = transaction_support()
    if not support["available"]:
        return _row("Transaction demo", False, support["reason"],
                    "Connect to a replica-set deployment.")
    try:
        present = get_db()[ACCOUNTS].count_documents(
            {"account_number": {"$in": DEMO_ACCOUNTS}})
    except PyMongoError as exc:
        return _row("Transaction demo", False, str(exc), SEED_HINT)
    ok = present == len(DEMO_ACCOUNTS)
    detail = support["reason"] if ok else \
        "Deployment supports transactions, but {}/{} demo accounts exist." \
        .format(present, len(DEMO_ACCOUNTS))
    return _row("Transaction demo", ok, detail, "" if ok else SEED_HINT)


def run_all() -> list:
    rows = [check_uri(), check_connection()]
    if not rows[1]["ok"]:
        skip = "Skipped — no connection"
        rows += [_row(name, False, skip, "Fix the connection first.")
                 for name in ("Database permissions", "Seed data",
                              "Demo indexes", "Schema validators",
                              "Transaction demo")]
        return rows
    return rows + [check_permissions(), check_seed(), check_indexes(),
                   check_validators(), check_transactions()]


def all_ok(rows: list = None) -> bool:
    rows = rows if rows is not None else run_all()
    return all(r["ok"] for r in rows)
