"""Generate the synthetic DocsCo knowledge base.

    python data/build_corpus.py              # writes data/knowledge_base.json
    python data/build_corpus.py --count 500

Output is deterministic for a given --count and --seed, so everyone in a
workshop ends up with byte-identical data. No network access, no real content.
"""
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import topics  # noqa: E402

OUT_FILE = Path(__file__).parent / "knowledge_base.json"


def _article(doc_id: int, kind: str, title: str, body: str,
             category: str, product: str, audience: str) -> dict:
    return {
        "doc_id": f"KB-{doc_id:04d}",
        "kind": kind,
        "title": title,
        "body": body,
        "category": category,
        "product": product,
        "audience": audience,
    }


def generate(count: int, seed: int) -> list:
    rng = random.Random(seed)
    articles = []
    next_id = 1

    for group, kind in ((topics.SHOWCASE, "showcase"), (topics.DECOY, "decoy")):
        for spec in group:
            articles.append(_article(
                next_id, kind, spec["title"], spec["body"],
                spec["category"], spec["product"], spec["audience"],
            ))
            next_id += 1

    combos = [
        (c, p, a)
        for c in topics.CATEGORIES
        for p in topics.PRODUCTS
        for a in topics.AUDIENCES
    ]
    rng.shuffle(combos)

    filler_needed = max(count - len(articles), 0)
    for i in range(filler_needed):
        category, product, audience = combos[i % len(combos)]
        variant = topics.FILLER_VARIANTS[i % len(topics.FILLER_VARIANTS)]
        title = topics.FILLER_TITLES[category].format(
            product=product, audience=audience)
        body = topics.FILLER_TEMPLATES[category].format(
            product=product, audience=audience, variant=variant)
        # Past the first pass through `combos` the same tuple recurs, so tag the
        # title with a revision to keep every document distinguishable.
        revision = i // len(combos)
        if revision:
            title = f"{title} (revision {revision + 1})"
        articles.append(_article(
            next_id, "filler", title, body, category, product, audience))
        next_id += 1

    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the DocsCo corpus.")
    parser.add_argument("--count", type=int, default=300,
                        help="total documents to generate (default: 300)")
    parser.add_argument("--seed", type=int, default=8,
                        help="RNG seed for reproducible output (default: 8)")
    args = parser.parse_args()

    articles = generate(args.count, args.seed)
    OUT_FILE.write_text(json.dumps(articles, indent=2) + "\n")

    by_kind = {}
    for doc in articles:
        by_kind[doc["kind"]] = by_kind.get(doc["kind"], 0) + 1
    print(f"Wrote {len(articles)} articles to {OUT_FILE}")
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(by_kind.items())))
    print("\nNext: python app/ingest.py")


if __name__ == "__main__":
    main()
