"""Operational catalog reads and writes — the MongoDB 101 half of the demo.

One collection (`pcs_products`) holds three product types whose attributes
differ by design. Structured filters, sorting, and pagination are built here as
plain query documents so a presenter can read them out loud, and the same filter
fragment is reused by every search mode in `lib/search.py`.

Writes go through `save_product`, which validates input, stamps `updated_at`,
and appends a small audit document to `pcs_product_events`.
"""

from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from lib.atlas_client import (CATEGORIES, PRODUCT_TYPES, STATUSES,
                              TYPE_ATTRIBUTE, events, products)

PAGE_SIZE = 6

SORT_OPTIONS = {
    "Recently updated": [("updated_at", DESCENDING)],
    "Name (A–Z)": [("name", ASCENDING)],
    "Price (low → high)": [("price.amount", ASCENDING)],
    "Price (high → low)": [("price.amount", DESCENDING)],
}

# Fields the UI never needs to render, and never wants to ship over the wire.
LIST_PROJECTION = {"embedding": 0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_filter(filters: dict | None) -> dict:
    """Turn UI filter selections into a single MongoDB query document.

    Handles the four structured filters the demo advertises: product type,
    category, availability status, price range, plus the one type-specific
    attribute that only exists on documents of that type.
    """
    f = filters or {}
    query: dict = {}
    if f.get("product_type"):
        query["product_type"] = f["product_type"]
    if f.get("category"):
        query["category"] = f["category"]
    if f.get("status"):
        query["status"] = f["status"]

    price: dict = {}
    if f.get("price_min") is not None:
        price["$gte"] = float(f["price_min"])
    if f.get("price_max") is not None:
        price["$lte"] = float(f["price_max"])
    if price:
        query["price.amount"] = price

    # The type-specific attribute is only meaningful once a type is chosen —
    # the attribute path itself does not exist on the other product types.
    attr_value = f.get("type_attribute")
    if attr_value and f.get("product_type") in TYPE_ATTRIBUTE:
        path = TYPE_ATTRIBUTE[f["product_type"]][0]
        query[path] = attr_value
    return query


def type_attribute_options(product_type: str | None) -> tuple[str, list[str]]:
    """Label + allowed values for the currently selected type's attribute."""
    if product_type in TYPE_ATTRIBUTE:
        _, label, options = TYPE_ATTRIBUTE[product_type]
        return label, options
    return "Type-specific attribute", []


def price_bounds() -> tuple[float, float]:
    """Min/max catalog price, used to bound the price-range slider."""
    rows = list(products().aggregate([
        {"$group": {"_id": None, "lo": {"$min": "$price.amount"},
                    "hi": {"$max": "$price.amount"}}}]))
    if not rows or rows[0].get("lo") is None:
        return 0.0, 1000.0
    return float(rows[0]["lo"]), float(rows[0]["hi"])


def list_products(filters: dict | None = None, *, sort: str = "Recently updated",
                  page: int = 1, page_size: int = PAGE_SIZE) -> dict:
    """One page of filtered, sorted products plus the total match count."""
    query = build_filter(filters)
    total = products().count_documents(query)
    cursor = (products().find(query, LIST_PROJECTION)
              .sort(SORT_OPTIONS.get(sort, SORT_OPTIONS["Recently updated"]))
              .skip(max(page - 1, 0) * page_size)
              .limit(page_size))
    return {"items": list(cursor), "total": total, "query": query,
            "page": page, "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size)}


def get_product(product_id: str) -> dict | None:
    return products().find_one({"product_id": product_id}, LIST_PROJECTION)


def catalog_stats() -> dict:
    """Counts by type and status for the overview dashboard."""
    by_type = {r["_id"]: r["n"] for r in products().aggregate([
        {"$group": {"_id": "$product_type", "n": {"$sum": 1}}}])}
    by_status = {r["_id"]: r["n"] for r in products().aggregate([
        {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    return {
        "total": products().count_documents({}),
        "by_type": {t: by_type.get(t, 0) for t in PRODUCT_TYPES},
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "embedded": products().count_documents({"embedding": {"$exists": True}}),
        "events": events().count_documents({}),
    }


def distinct_field_paths(limit: int = 60) -> dict[str, list[str]]:
    """Top-level field names present per product type.

    Reads a sample of documents and reports which fields each type actually
    carries — the concrete evidence that one collection holds several shapes.
    """
    shapes: dict[str, set[str]] = {}
    for doc in products().find({}, LIST_PROJECTION).limit(limit):
        shapes.setdefault(doc.get("product_type", "unknown"), set()).update(
            k for k in doc if k != "_id")
    return {t: sorted(v) for t, v in sorted(shapes.items())}


# ── Writes (create / edit) ─────────────────────────────────────────────────

def validate_product(payload: dict) -> list[str]:
    """Return a list of human-readable validation errors (empty when valid)."""
    errors: list[str] = []
    ptype = payload.get("product_type")
    if not (payload.get("name") or "").strip():
        errors.append("Name is required.")
    if not (payload.get("sku") or "").strip():
        errors.append("SKU is required.")
    if ptype not in PRODUCT_TYPES:
        errors.append(f"Product type must be one of {PRODUCT_TYPES}.")
    elif payload.get("category") not in CATEGORIES[ptype]:
        errors.append(f"Category must be one of {CATEGORIES[ptype]} for "
                      f"{ptype}.")
    if payload.get("status") not in STATUSES:
        errors.append(f"Status must be one of {STATUSES}.")
    amount = (payload.get("price") or {}).get("amount")
    if amount is None or float(amount) < 0:
        errors.append("Price must be zero or greater.")
    if not (payload.get("summary") or "").strip():
        errors.append("Summary is required — it is what keyword search matches.")
    return errors


def next_product_id() -> str:
    """Next id in the PCS-#### series, derived from what is already stored."""
    last = products().find_one({"product_id": {"$regex": r"^PCS-\d+$"}},
                               {"product_id": 1},
                               sort=[("product_id", DESCENDING)])
    if not last:
        return "PCS-1001"
    return f"PCS-{int(last['product_id'].split('-')[1]) + 1}"


def save_product(payload: dict, *, author: str = "Studio user") -> dict:
    """Validate, embed, upsert a product document and record an audit event.

    Raises ``ValueError`` with all validation problems so the form can show them
    together. Embedding failures never block the write — the product is stored
    without a vector and the caller is told, so keyword search still finds it.
    """
    errors = validate_product(payload)
    if errors:
        raise ValueError(" ".join(errors))

    doc = {k: v for k, v in payload.items() if v is not None}
    product_id = doc.get("product_id") or next_product_id()
    doc["product_id"] = product_id
    doc["updated_at"] = _now()

    embed_error = None
    try:
        from lib.embeddings import get_embedder, product_text

        embedder = get_embedder()
        doc["embedding"] = embedder.embed_documents([product_text(doc)])[0]
        doc["embedding_provider"] = embedder.provider
        doc["embedding_dim"] = len(doc["embedding"])
    except Exception as e:  # noqa: BLE001 — a write must not fail on embedding
        embed_error = str(e)

    existed = products().count_documents({"product_id": product_id}, limit=1) > 0
    saved = products().find_one_and_update(
        {"product_id": product_id},
        {"$set": doc, "$setOnInsert": {"created_at": _now(), "source": "studio"}},
        upsert=True, projection=LIST_PROJECTION,
        return_document=ReturnDocument.AFTER)

    action = "updated" if existed else "created"
    events().insert_one({
        "product_id": product_id, "action": action, "author": author,
        "at": _now(), "fields": sorted(k for k in doc if k != "embedding"),
    })
    return {"product": saved, "action": action, "embed_error": embed_error}


def recent_events(limit: int = 10) -> list[dict]:
    return list(events().find({}, {"_id": 0}).sort("at", DESCENDING).limit(limit))


# ── Presentation helpers ───────────────────────────────────────────────────

def business_view(doc: dict) -> list[tuple[str, str]]:
    """A readable, type-aware business summary of a stored product document."""
    price = doc.get("price") or {}
    rows = [
        ("Product", f"{doc.get('name', '—')} ({doc.get('sku', '—')})"),
        ("Type", (doc.get("product_type") or "").replace("_", " ").title()),
        ("Category", doc.get("category", "—")),
        ("Availability", (doc.get("status") or "—").title()),
        ("Price", f"{price.get('amount', 0):,.2f} {price.get('currency', '')} "
                  f"{price.get('unit', '')}".strip()),
        ("Summary", doc.get("summary", "—")),
    ]
    specs = doc.get("specs") or {}
    if specs:
        rows.append(("Power source", specs.get("power_source", "—")))
        rows.append(("Weight", f"{specs.get('weight_kg', '—')} kg"))
        rows.append(("Warranty", f"{specs.get('warranty_months', '—')} months"))
    if doc.get("lead_time_days") is not None:
        rows.append(("Lead time", f"{doc['lead_time_days']} days"))
    pack = doc.get("pack") or {}
    if pack:
        rows.append(("Pack", f"{pack.get('units_per_pack', '—')} × "
                             f"{pack.get('unit_size', '—')}"))
    handling = doc.get("handling") or {}
    if handling:
        rows.append(("Hazard class", handling.get("hazard_class", "—")))
        rows.append(("Storage", handling.get("storage", "—")))
        rows.append(("Shelf life",
                     f"{handling.get('shelf_life_months', '—')} months"))
    coverage = doc.get("coverage") or {}
    if coverage:
        rows.append(("Response tier", coverage.get("response_tier", "—")))
        rows.append(("On-site", "Yes" if coverage.get("on_site") else "No"))
        rows.append(("Cover hours", coverage.get("hours", "—")))
    term = doc.get("term") or {}
    if term:
        rows.append(("Term", f"{term.get('months', '—')} months"
                             + (" · auto-renew" if term.get("auto_renew") else "")))
    if doc.get("entitlements"):
        rows.append(("Includes", ", ".join(doc["entitlements"])))
    stock = doc.get("stock") or {}
    if stock:
        rows.append(("Stock on hand", f"{stock.get('on_hand', 0)} "
                                      f"({stock.get('warehouse', '—')})"))
    return rows
