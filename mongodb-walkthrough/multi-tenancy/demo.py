"""
Demonstrates database-per-tenant isolation across three tenant databases
created by setup_tenants.py.

Tenants (all on the same cluster):
  classicflix        — movies before 1980
  millenniumstream   — movies 1980–1999
  modernplex         — movies 2000 and beyond

Sections:
  1. Namespace overview  — all three databases, same collection shape
  2. Data isolation      — same query run against all tenants with admin
                           credentials; data exists in only one namespace
  3. RBAC isolation      — scoped credential succeeds on its own database,
                           then fails with OperationFailure on another
  4. Connection routing  — how the application selects the right database
  5. Summary             — two-layer isolation model recap

Run setup_tenants.py before this script.
Set CLASSICFLIX_PASSWORD, MILLENNIUMSTREAM_PASSWORD, MODERNPLEX_PASSWORD
in .env to enable the RBAC section.
"""

import os
import re
import sys
from urllib.parse import urlparse, urlunparse, quote_plus
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ["MONGODB_URI"]

TENANT_DBS = ["classicflix", "millenniumstream", "modernplex"]

PASSWORDS = {
    "classicflix":      os.environ.get("CLASSICFLIX_PASSWORD", ""),
    "millenniumstream": os.environ.get("MILLENNIUMSTREAM_PASSWORD", ""),
    "modernplex":       os.environ.get("MODERNPLEX_PASSWORD", ""),
}

# Well-known titles — one per era — for the data isolation demo.
DEMO_TITLES = [
    ("Apocalypse Now",  "classicflix",      1979),
    ("The Matrix",      "millenniumstream", 1999),
    ("The Dark Knight", "modernplex",       2008),
]


def divider(title):
    print(f"\n{'═' * 62}")
    print(f"  {title}")
    print(f"{'═' * 62}\n")


def sub_divider(title):
    print(f"\n  {'─' * 56}")
    print(f"  {title}")
    print(f"  {'─' * 56}\n")


def build_tenant_uri(base_uri, username, password):
    """Replace credentials in a mongodb+srv URI with tenant-specific ones."""
    p = urlparse(base_uri)
    host_only = p.netloc.split("@", 1)[1]
    new_netloc = f"{quote_plus(username)}:{quote_plus(password)}@{host_only}"
    return urlunparse(p._replace(netloc=new_netloc))


def clean_errmsg(errmsg):
    """
    Trim the verbose internal fields from a MongoDB authorization error,
    leaving just the human-readable portion before lsid / $clusterTime.
    """
    # Truncate at the first internal field that adds no demo value
    trimmed = re.sub(r',\s*(lsid|\\$clusterTime|$db)\b.*', ' }', errmsg)
    # Collapse multiple spaces
    return re.sub(r'  +', ' ', trimmed)


def check_setup(client):
    missing = [db for db in TENANT_DBS if db not in client.list_database_names()]
    if missing:
        print("ERROR: The following tenant databases were not found:")
        for db in missing:
            print(f"  · {db}")
        print("\nRun setup_tenants.py first.")
        sys.exit(1)


# ── Section 1: Namespace overview ──────────────────────────────────

def section_namespace(client):
    divider("1 — Namespace overview")
    print("  Three tenant databases, each with the same collection shape,")
    print("  all running on the same Atlas cluster.\n")
    print(f"  {'Database':<22}  {'Collection':<12}  Documents")
    print(f"  {'─' * 22}  {'─' * 12}  ─────────")
    for db_name in TENANT_DBS:
        db = client[db_name]
        for coll_name in sorted(db.list_collection_names()):
            count = db[coll_name].estimated_document_count()
            print(f"  {db_name:<22}  {coll_name:<12}  {count:>9,}")
        print()


# ── Section 2: Data isolation ───────────────────────────────────────

def section_data_isolation(client):
    divider("2 — Data isolation: same query, three namespaces")

    print("  The query below is run against all three tenant databases")
    print("  using admin credentials — nothing prevents the reads.")
    print("  Each title exists in exactly one namespace because that is")
    print("  where the data lives, not because a filter excludes it.\n")
    print("  Connection : admin credentials  (full cluster access)")

    for title, expected_tenant, year in DEMO_TITLES:
        query_str = f'db["<tenant>"].movies.find_one({{"title": "{title}"}})'
        print(f"\n  Query      : {query_str}\n")
        for db_name in TENANT_DBS:
            doc = client[db_name].movies.find_one(
                {"title": title},
                {"title": 1, "year": 1, "_id": 0},
            )
            if doc:
                result_str = f"{{'title': '{doc['title']}', 'year': {doc['year']}}}"
                print(f"  {db_name:<22}  → {result_str}  ◀ found")
            else:
                print(f"  {db_name:<22}  → None  (document does not exist in this namespace)")


# ── Section 3: RBAC isolation ───────────────────────────────────────

def section_rbac(client):
    divider("3 — RBAC isolation: credential-scoped access")

    if not all(PASSWORDS.values()):
        missing = [k for k, v in PASSWORDS.items() if not v]
        print("  Skipped — the following passwords are not set in .env:")
        for m in missing:
            print(f"    · {m.upper()}_PASSWORD")
        print("\n  Add them and re-run to see credential-level enforcement.")
        return

    print("  Each tenant user is scoped at the Atlas level to a single database.")
    print("  Unlike namespace isolation (where data simply isn't there), RBAC")
    print("  actively rejects unauthorised reads — the server refuses the command")
    print("  before any data is touched.\n")
    print("  We use classicflix_app for both steps below.\n")

    attacker_db = "classicflix"
    target_db   = "modernplex"
    username    = f"{attacker_db}_app"
    password    = PASSWORDS[attacker_db]
    uri         = build_tenant_uri(MONGODB_URI, username, password)

    tenant_client = MongoClient(uri, serverSelectionTimeoutMS=10_000)

    # ── Step 1: authorised read (should succeed) ────────────────────
    sub_divider("Step 1 — Authorised read (own database)")

    auth_title = "Apocalypse Now"
    print(f"  Credential : {username}")
    print(f"  Authorized : {attacker_db}  (read-only)")
    print(f'  Query      : db["{attacker_db}"].movies.find_one({{"title": "{auth_title}"}})\n')

    doc = tenant_client[attacker_db].movies.find_one(
        {"title": auth_title},
        {"title": 1, "year": 1, "_id": 0},
    )
    if doc:
        result_str = f"{{'title': '{doc['title']}', 'year': {doc['year']}}}"
        print(f"  Result     : {result_str}  ✓  authorised read succeeded")
    else:
        print(f"  Result     : None  (document not found — check setup)")

    # ── Step 2: cross-tenant read (should fail) ─────────────────────
    sub_divider("Step 2 — Cross-tenant read attempt (different database)")

    print(f"  Credential : {username}  (unchanged)")
    print(f"  Authorized : {attacker_db}  (read-only)")
    print(f'  Query      : db["{target_db}"].movies.find_one({{}})\n')

    try:
        doc = tenant_client[target_db].movies.find_one({})
        if doc:
            print("  [UNEXPECTED] A document was returned — verify the user's role scoping.")
        else:
            print("  Result     : None  (unexpected — verify role scoping)")
    except OperationFailure as e:
        raw_msg  = e.details.get("errmsg", str(e))
        clean_msg = clean_errmsg(raw_msg)
        print(f"  Result     : OperationFailure  ✓\n")
        print(f"  Error      : \"{clean_msg}\"\n")
        print(f"  Atlas rejected the command before any data was accessed.")
        print(f"  This is enforced at the server — application routing bugs")
        print(f"  cannot bypass it.")

    tenant_client.close()


# ── Section 4: Connection routing ───────────────────────────────────

def section_routing(client):
    divider("4 — Connection routing pattern")

    host = urlparse(MONGODB_URI).netloc.split("@", 1)[1]

    print("  The application resolves a database name from the tenant context")
    print("  (a JWT claim, a subdomain, or an API key lookup) and calls")
    print("  client[db_name] — one line of routing logic.\n")
    print(f"  {'Tenant':<22}  URI")
    print(f"  {'─' * 22}  {'─' * 36}")
    for db_name in TENANT_DBS:
        print(f"  {db_name:<22}  mongodb+srv://<{db_name}_app>:***@{host}/{db_name}")
    print()
    print("  Each connection string carries the tenant's scoped credential.")
    print("  The database name in the URI is the routing primitive — no")
    print("  tenant-awareness is needed anywhere in the query layer itself.")


# ── Section 5: Summary ───────────────────────────────────────────────

def section_summary():
    divider("5 — Two-layer isolation model")

    print(f"  {'Layer':<16}  {'Mechanism':<28}  What happens on a wrong-tenant read")
    print(f"  {'─' * 16}  {'─' * 28}  {'─' * 36}")
    print(f"  {'1 — Namespace':<16}  {'Data lives in separate DBs':<28}  Query returns None — data is not there")
    print(f"  {'2 — RBAC':<16}  {'Credential scoped to one DB':<28}  OperationFailure — server rejects the")
    print(f"  {'':<16}  {'':<28}  command before any data is touched")
    print()
    print("  Layer 1 protects against accidental cross-tenant reads when")
    print("  application routing is correct.")
    print()
    print("  Layer 2 protects against cross-tenant reads even when it isn't —")
    print("  a misrouted request, a bug, or a compromised credential cannot")
    print("  return another tenant's data.")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=== Multi-Tenancy: Database-per-Tenant Isolation Demo ===")

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    check_setup(client)

    section_namespace(client)
    section_data_isolation(client)
    section_rbac(client)
    section_routing(client)
    section_summary()

    client.close()


if __name__ == "__main__":
    main()
