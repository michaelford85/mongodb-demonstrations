#!/usr/bin/env python3
"""
Download a subset of Amazon product data from HuggingFace and load into MongoDB.

Usage:
    python scripts/load_data.py [--limit 5000] [--drop]

    --limit   Max products to load per category (default: 5000)
    --drop    Drop the collection before loading

Requires: pip install datasets pymongo python-dotenv
"""

import os
import sys
import argparse
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")

CATEGORIES = {
    "Electronics": "0core_meta_Electronics",
    "Home_and_Kitchen": "0core_meta_Home_and_Kitchen",
    "Clothing_Shoes_and_Jewelry": "0core_meta_Clothing_Shoes_and_Jewelry",
}


def get_image_url(images_field) -> str | None:
    if not images_field:
        return None
    for img in images_field:
        if isinstance(img, dict):
            url = img.get("large") or img.get("hi_res") or img.get("thumb")
            if url:
                return url
        elif isinstance(img, str) and img.startswith("http"):
            return img
    return None


def transform(item: dict, category: str) -> dict | None:
    title = (item.get("title") or "").strip()
    if not title:
        return None

    description = " ".join(item.get("description") or []).strip()
    features = [f for f in (item.get("features") or []) if isinstance(f, str) and f.strip()]
    features_text = " ".join(features).strip()

    if not description and not features_text:
        return None

    price = item.get("price")
    try:
        price = float(price) if price else None
    except (ValueError, TypeError):
        price = None

    return {
        "asin": item.get("parent_asin") or item.get("asin"),
        "title": title,
        "description": description,
        "features": features,
        "features_text": features_text,
        "category": category,
        "subcategories": item.get("categories") or [],
        "price": price,
        "rating": item.get("average_rating"),
        "rating_count": item.get("rating_number"),
        "image_url": get_image_url(item.get("images")),
        "store": item.get("store"),
    }


def main():
    parser = argparse.ArgumentParser(description="Load Amazon product data into MongoDB")
    parser.add_argument("--limit", type=int, default=5000, help="Max products per category (default: 5000)")
    parser.add_argument("--drop", action="store_true", help="Drop collection before loading")
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: datasets library not found. Run: pip install datasets", file=sys.stderr)
        sys.exit(1)

    uri = os.getenv("MONGODB_URI")
    cert = os.getenv("MONGODB_CERT")
    db_name = os.getenv("DB_NAME", "ecommerce_demo")
    coll_name = os.getenv("COLLECTION_NAME", "products")

    if cert:
        mongo = MongoClient(uri, tls=True, tlsCertificateKeyFile=cert)
    else:
        mongo = MongoClient(uri)

    coll = mongo[db_name][coll_name]

    if args.drop:
        print(f"Dropping {db_name}.{coll_name}...")
        coll.drop()

    existing = coll.count_documents({})
    if existing > 0 and not args.drop:
        print(f"Collection already has {existing:,} documents. Use --drop to reload.")
        sys.exit(0)

    total_inserted = 0

    for category, hf_name in CATEGORIES.items():
        print(f"\nLoading {category} ({hf_name})...")

        try:
            ds = load_dataset(
                "McAuley-Lab/Amazon-Reviews-2023",
                hf_name,
                streaming=True,
                split="full",
                trust_remote_code=True,
            )
        except Exception as e:
            print(f"  ERROR loading {hf_name}: {e}", file=sys.stderr)
            continue

        batch: list[dict] = []
        loaded = 0

        for item in ds:
            if loaded >= args.limit:
                break

            product = transform(item, category)
            if product is None:
                continue

            batch.append(product)
            loaded += 1

            if len(batch) >= 500:
                result = coll.insert_many(batch, ordered=False)
                total_inserted += len(result.inserted_ids)
                print(f"  {total_inserted:,} products inserted so far...")
                batch = []

        if batch:
            result = coll.insert_many(batch, ordered=False)
            total_inserted += len(result.inserted_ids)

        print(f"  Done: {loaded:,} products from {category}")

    print(f"\n✓ Total products loaded: {total_inserted:,}")
    print("Next step: python scripts/create_indexes.py")
    print("Then:      python scripts/add_embeddings.py")


if __name__ == "__main__":
    main()
