import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from config import load_mapping, load_settings
from ire_payload import build_ire_payload
from mock_atlas import MockAtlasClient
from normalizer import normalize_inventory
from servicenow_client import ServiceNowIREClient, ServiceNowError, ensure_apply_allowed

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"


def make_atlas_client(settings):
    from atlas_client import AtlasAdminClient

    return AtlasAdminClient(
        org_id=settings.atlas_org_id,
        auth=settings.atlas_auth,
        client_id=settings.atlas_client_id,
        client_secret=settings.atlas_client_secret,
        public_key=settings.atlas_public_key,
        private_key=settings.atlas_private_key,
        items_per_page=settings.atlas_items_per_page,
        timeout=settings.atlas_timeout_seconds,
        max_retries=settings.atlas_max_retries,
    )


def make_source_client(settings):
    if settings.source == "mock":
        return MockAtlasClient()
    if settings.source == "atlas":
        if not settings.atlas_org_id:
            raise SystemExit("DEMO_SOURCE=atlas requires ATLAS_ORG_ID in the environment")
        return make_atlas_client(settings)
    raise SystemExit(f"unknown DEMO_SOURCE: {settings.source}")


def print_summary(records, payload, mapping):
    counts = Counter(r.record_type for r in records)
    print("\n=== Normalized inventory (CMDB-ready records) ===")
    print(f"total records: {len(records)}  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print("\nresource -> proposed CI class:")
    for resource in ("organization", "project", "cluster", "process"):
        cls = mapping.class_mapping(resource)
        print(f"  {resource:<13} -> {cls.ci_class} (parent: {cls.parent or '-'})")
    print("\nrecords:")
    for r in records:
        parent = r.parent_source_id or "-"
        print(f"  [{r.record_type:<12}] {r.source_id}  name={r.name}  class={r.ci_class}  parent={parent}")
    print(f"\n=== IRE payload ===")
    print(f"items: {len(payload['items'])}  relations: {len(payload['relations'])}")
    print("relations:")
    for rel in payload["relations"]:
        print(f"  {rel['parent_id']}  --{rel['type']}-->  {rel['child_id']}")


def write_artifacts(records, payload):
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "normalized_inventory.json", "w", encoding="utf-8") as fh:
        json.dump([r.to_dict() for r in records], fh, indent=2)
    with open(OUTPUT_DIR / "ire_payload.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {OUTPUT_DIR / 'normalized_inventory.json'}")
    print(f"wrote {OUTPUT_DIR / 'ire_payload.json'}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Atlas -> ServiceNow CMDB synchronization demo (read-only by default)"
    )
    parser.add_argument("--source", choices=["mock", "atlas"], default=None,
                        help="inventory source (default: DEMO_SOURCE from .env, or mock)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of Atlas projects synced (mock/live)")
    parser.add_argument("--validate", action="store_true",
                        help="call the ServiceNow IRE /query SIMULATION endpoint (no commits)")
    parser.add_argument("--apply", action="store_true",
                        help="submit to the ServiceNow IRE endpoint for real; requires "
                             "SERVICENOW_ALLOW_WRITES=true as well")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-record listing")
    args = parser.parse_args(argv)

    load_dotenv(HERE / ".env")
    settings = load_settings()
    if args.source:
        settings.source = args.source

    mapping = load_mapping(HERE / settings.mapping_file)
    if mapping.discovery_source != settings.servicenow_discovery_source:
        mapping.discovery_source = settings.servicenow_discovery_source

    print(f"source: {settings.source}  mode: {'APPLY (live write)' if args.apply else 'validate (no commit)' if args.validate else 'dry-run (no ServiceNow calls)'}")

    client = make_source_client(settings)
    records = normalize_inventory(client, mapping, limit=args.limit)
    if not records:
        print("no inventory records found")
        return 1
    payload = build_ire_payload(records, mapping)

    if not args.quiet:
        print_summary(records, payload, mapping)
    else:
        counts = Counter(r.record_type for r in records)
        print(f"{len(records)} records  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    write_artifacts(records, payload)

    if not (args.validate or args.apply):
        print("\ndry-run complete: nothing was sent to ServiceNow. "
              "See output/ for the payload that would be submitted.")
        return 0

    if args.apply:
        ensure_apply_allowed(settings, cli_apply=True)

    try:
        sn = ServiceNowIREClient(
            instance_url=settings.servicenow_instance_url,
            username=settings.servicenow_username,
            password=settings.servicenow_password,
            discovery_source=mapping.discovery_source,
            timeout=settings.servicenow_timeout_seconds,
            max_retries=settings.servicenow_max_retries,
        )
    except ServiceNowError as exc:
        raise SystemExit(f"cannot reach ServiceNow: {exc}")

    if args.apply:
        print("\nsubmitting to ServiceNow IRE (POST /api/now/identifyreconcile) ...")
        result = sn.submit(payload)
        print("IRE response summary:")
        print(json.dumps(result, indent=2)[:4000])
        return 0

    print("\nsimulating against ServiceNow IRE (POST /api/now/identifyreconcile/query, no commits) ...")
    result = sn.simulate(payload)
    print("IRE simulation response summary:")
    print(json.dumps(result, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
