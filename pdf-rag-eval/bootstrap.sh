#!/usr/bin/env bash
# Bootstrap the pdf-rag-eval pipeline end-to-end against an empty Atlas
# cluster and an empty Cosmos container. Idempotent enough to re-run, but
# wipes local data/ and re-ingests both backends every time.
#
# Assumes pdf-rag-eval/.env is fully populated and the sibling
# cosmosdb-cluster-provisioning + this folder's infra/ have already been
# applied.
#
# Usage:
#   ./bootstrap.sh                  # full pipeline + verification
#   ./bootstrap.sh --skip-clean     # keep existing data/ artifacts and PDFs
#   ./bootstrap.sh --with-smoke     # also run the three smoke-test commands
#   ./bootstrap.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SKIP_CLEAN=0
WITH_SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --skip-clean) SKIP_CLEAN=1 ;;
    --with-smoke) WITH_SMOKE=1 ;;
    -h|--help)
      sed -n '2,15p' "$0"
      exit 0
      ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    OK\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m   !! %s\033[0m\n' "$*"; }

# --- 1. Python env -----------------------------------------------------------

step "Python environment"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  ok "created .venv"
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "deps installed ($(python3 -c 'import sys; print(sys.version.split()[0])') in $(which python3))"

# --- 2. .env sanity check ----------------------------------------------------

step "Validate .env via config.load_settings()"
python3 - <<'PY'
from config import load_settings
s = load_settings()
print(f"    voyage           : {s.voyage_model} @ {s.embed_dim}d")
print(f"    cosmos           : {s.cosmos_database}.{s.cosmos_container}")
print(f"    atlas            : {s.mongo_db}.{s.mongo_collection}  (index={s.atlas_vector_index})")
print(f"    blob container   : {s.azure_storage_container}")
PY

# --- 3. Wipe stale local artifacts ------------------------------------------

if [[ "$SKIP_CLEAN" -eq 0 ]]; then
  step "Wipe stale data/ (old-schema PDFs and chunks.jsonl)"
  rm -rf data/source_pdfs data/chunks.jsonl data/pdf_manifest.jsonl
  ok "data/ cleaned"
else
  warn "skipping data/ wipe (--skip-clean). Existing artifacts may use old schema."
fi

# --- 4. Pipeline -------------------------------------------------------------

step "Generate synthetic PDFs"
python3 generate_pdfs.py

step "Upload PDFs to Azure Blob (--overwrite for idempotent re-runs)"
python3 upload_blobs.py --overwrite

step "Extract, chunk, embed (calls Voyage AI)"
python3 embed_and_load.py

step "Ingest into Cosmos"
python3 -m cosmos.ingest

step "Ingest into Atlas (--drop)"
python3 -m mongodb.ingest --drop

step "Create Atlas Vector Search index (blocking until queryable)"
python3 -m mongodb.create_index --wait

# --- 5. Post-ingest verification --------------------------------------------

step "Verify ingest counts and index state"
python3 - <<'PY'
from azure.cosmos import CosmosClient
from pymongo import MongoClient
from config import load_settings

s = load_settings()

coll = MongoClient(s.mongo_uri)[s.mongo_db][s.mongo_collection]
atlas_n = coll.count_documents({})
atlas_idx = [(i["name"], i.get("queryable")) for i in coll.list_search_indexes()]
print(f"    atlas chunks     : {atlas_n}")
print(f"    atlas indexes    : {atlas_idx}")

c = CosmosClient(s.cosmos_endpoint, credential=s.cosmos_key)
cont = c.get_database_client(s.cosmos_database).get_container_client(s.cosmos_container)
cosmos_n = list(cont.query_items(
    "SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
))[0]
print(f"    cosmos chunks    : {cosmos_n}")

if atlas_n != cosmos_n:
    raise SystemExit(f"!! count mismatch: atlas={atlas_n} cosmos={cosmos_n}")
queryable = any(name == s.atlas_vector_index and ok for name, ok in atlas_idx)
if not queryable:
    raise SystemExit(f"!! atlas index {s.atlas_vector_index} is not queryable yet")
print("    counts match; atlas index is queryable.")
PY

# --- 6. Optional smoke test --------------------------------------------------

if [[ "$WITH_SMOKE" -eq 1 ]]; then
  step "Smoke test: product_match (atlas)"
  python3 -m compare.product_match "industrial battery 12V" --k 3 --only atlas

  step "Smoke test: product_match (cosmos)"
  python3 -m compare.product_match "industrial battery 12V" --k 3 --only cosmos

  step "Smoke test: batch_throughput (100 rows, 5s query)"
  python3 -m compare.batch_throughput --rows 100 --workers 4 --duration 5
fi

step "Done."
echo "    Next: python -m compare.product_match \"...\" or compare.batch_throughput at larger --rows."
