"""
Demonstrates database-per-tenant isolation across three tenant databases
created by setup_tenants.py.

Tenants (all on the same cluster):
  classicflix        — movies before 1980
  millenniumstream   — movies 1980–1999
  modernplex         — movies 2000 and beyond

Sections:
  1. Namespace overview  — all three databases, same collection shape
  2. Data isolation      — same title searched across all tenants; only one
                           has it, the others return zero results
  3. RBAC isolation      — a tenant-scoped credential is used to attempt a
                           cross-tenant read; Atlas rejects it at the server
  4. Connection routing  — how the application selects the right database

Run setup_tenants.py before this script.
Set CLASSICFLIX_PASSWORD, MILLENNIUMSTREAM_PASSWORD, MODERNPLEX_PASSWORD
in .env to enable the RBAC section.
"""

import os
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

# Well-known titles — one per era — used for the data isolation demo.
DEMO_TITLES = [
    ("Apocalypse Now",  "classicflix",      1979),
    ("The Matrix",      "millenniumstream", 1999),
    ("The Dark Knight", "modernplex",       2008),
]


def divider(title):
    print(f"\n{'═' * 62}")
    print(f"  {title}")
    print(f"{'═' * 62}\n")


def build_tenant_uri(base_uri, username, password):
    """Replace credentials in a mongodb+srv URI with tenant-specific ones."""
    p = urlparse(base_uri)
    host_only = p.netloc.split("@", 1)[1]
    new_netloc = f"{quote_plus(username)}:{quote_plus(password)}@{host_only}"
    return urlunparse(p._replace(netloc=new_netloc))


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
    divider("2 — Data isolation: same title searched across all tenants")
    print("  Each title exists in exactly one tenant database.")
    print("  The other two return zero results — not because of a filter,")
    print("  but because the document is simply not in that namespace.\n")

    for title, expected_tenant, year in DEMO_TITLES:
        print(f"  ┌─ \"{title}\"  ({year})")
        for db_name in TENANT_DBS:
            doc = client[db_name].movies.find_one(
                {"title": title},
                {"title": 1, "year": 1, "_id": 0},
            )
            if doc:
                print(f"  │  {db_name:<22}  year={doc.get('year')}  ◀ found here")
            else:
                print(f"  │  {db_name:<22}  — not found")
        print()


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
    print("  A cross-tenant read attempt raises an authorization error —")
    print("  enforcement happens on the server, not in the application.\n")

    # Use classicflix_app to attempt a read against modernplex
    attacker_db = "classicflix"
    target_db   = "modernplex"
    username    = f"{attacker_db}_app"
    password    = PASSWORDS[attacker_db]

    uri           = build_tenant_uri(MONGODB_URI, username, password)
    tenant_client = MongoClient(uri, serverSelectionTimeoutMS=10_000)

    print(f"  Credential : {username}")
    print(f"  Authorized : {attacker_db}  (read-only)")
    print(f"  Attempt    : read from {target_db}.movies\n")

    try:
        doc = tenant_client[target_db].movies.find_one({})
        if doc:
            print("  [UNEXPECTED] A document was returned — verify the user's role scoping.")
        else:
            print("  No document returned.")
    except OperationFailure as e:
        print(f"  ✓  OperationFailure raised as expected:")
        print(f"     \"{e.details.get('errmsg', str(e))}\"")
        print()
        print(f"  Atlas rejected the read before any data was accessed.")
        print(f"  A bug in the application routing logic cannot override this —")
        print(f"  RBAC is the second line of defence after namespace isolation.")

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
    print("  No query ever crosses a tenant boundary.")
    print("  RBAC ensures that even if routing logic has a bug, the credential")
    print("  scoping prevents unauthorized cross-tenant data access.")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=== Multi-Tenancy: Database-per-Tenant Isolation Demo ===")

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)
    check_setup(client)

    section_namespace(client)
    section_data_isolation(client)
    section_rbac(client)
    section_routing(client)

    client.close()


if __name__ == "__main__":
    main()
