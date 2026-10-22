"""Run a vector search for one tenant and show how it was routed.

The router picks the flat index (+ tenant_id pre-filter) for a small tenant, or
the tenant's dedicated HNSW view for a large tenant — you pass the SAME query
either way.

    python scripts/query.py "reset my password" --tenant small_0003
    python scripts/query.py "migrate data between regions" --tenant globex
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import tenants, router  # noqa: E402
from lib.client import PROFILE, QUERY_LIMIT  # noqa: E402
from lib.embeddings import embed_query  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Route and run a tenant query.")
    parser.add_argument("query", help="natural-language query text")
    parser.add_argument("--tenant", required=True, help="tenant_id to search within")
    parser.add_argument("--profile", default=PROFILE, choices=list(tenants.PROFILES))
    parser.add_argument("--limit", type=int, default=QUERY_LIMIT)
    parser.add_argument("--fake-embeddings", action="store_true",
                        help="embed the query with the offline backend "
                             "(match how the data was loaded)")
    args = parser.parse_args()

    if args.tenant not in tenants.all_tenant_ids(args.profile):
        print(f"Unknown tenant '{args.tenant}' for profile '{args.profile}'.",
              file=sys.stderr)
        sys.exit(1)

    r = router.route(args.tenant, args.profile)
    print(f"Tenant '{args.tenant}' -> {r.strategy.upper()} index "
          f"'{r.index}' on '{r.namespace}'"
          + (f" (pre-filter tenant_id={r.tenant_id})" if r.strategy == "flat"
             else " (no filter — view is already scoped)"))

    vector = embed_query(args.query, fake=args.fake_embeddings)
    results, _ = router.run_query(vector, args.tenant, args.profile, args.limit)

    print(f"\nTop {len(results)} results for: {args.query!r}\n")
    for i, doc in enumerate(results, 1):
        print(f"  {i:>2}. [{doc['score']:.4f}] {doc.get('category', '')} "
              f"— {doc.get('doc_id', '')}")


if __name__ == "__main__":
    main()
