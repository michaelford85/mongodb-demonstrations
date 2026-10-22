"""Public BEIR benchmark loading and seeded sampling.

Data roles: `corpus` (documents to index), `queries`, and `qrels` (human
relevance judgments). Nothing here touches a model.

Source: the BEIR benchmark's public zip files. Each dataset keeps its own
license (SciFact: CC BY-NC 2.0, i.e. non-commercial; check each dataset's card
before using it beyond a demo). Files are downloaded on demand into `data/`.
"""
from __future__ import annotations

import csv
import io
import json
import random
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lib.config import EvalError

BEIR_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{name}.zip"
MAX_ZIP_BYTES = 200 * 1024 * 1024


class DatasetError(EvalError):
    pass


@dataclass
class Dataset:
    name: str
    corpus: dict[str, dict]          # doc_id -> {"title": str, "text": str}
    queries: dict[str, str]          # query_id -> text
    qrels: dict[str, dict[str, int]]  # query_id -> {doc_id: grade}
    notes: list[str]


def doc_text(doc: dict) -> str:
    """The single document string embedded for BOTH models."""
    title = (doc.get("title") or "").strip()
    body = (doc.get("text") or "").strip()
    return f"{title}. {body}" if title and body else (title or body)


def download_beir(name: str, data_dir: str | Path) -> Path:
    target = Path(data_dir) / f"{name}.zip"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = BEIR_URL.format(name=name)
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (fixed https URL)
            data = resp.read(MAX_ZIP_BYTES + 1)
    except OSError as exc:
        raise DatasetError(f"Could not download {name} from {url}: {exc}") from None
    if len(data) > MAX_ZIP_BYTES:
        raise DatasetError(f"{name}.zip is larger than the {MAX_ZIP_BYTES // 2**20} MB safety limit.")
    target.write_bytes(data)
    return target


def load_beir(name: str, data_dir: str | Path = "data", split: str = "test") -> Dataset:
    """Read only the three needed members from the zip (nothing is extracted to disk)."""
    zpath = download_beir(name, data_dir)
    try:
        with zipfile.ZipFile(zpath) as z:
            def read(member):
                try:
                    return z.read(f"{name}/{member}").decode("utf-8")
                except KeyError:
                    raise DatasetError(f"{zpath.name} is missing {member}; delete it to re-download.") from None
            corpus_raw, queries_raw, qrels_raw = read("corpus.jsonl"), read("queries.jsonl"), read(f"qrels/{split}.tsv")
    except zipfile.BadZipFile:
        raise DatasetError(f"{zpath} is not a valid zip; delete it to re-download.") from None
    return parse_beir(name, corpus_raw, queries_raw, qrels_raw)


def parse_beir(name: str, corpus_raw: str, queries_raw: str, qrels_raw: str) -> Dataset:
    corpus = {}
    for line in corpus_raw.splitlines():
        if line.strip():
            row = json.loads(line)
            corpus[str(row["_id"])] = {"title": row.get("title", ""), "text": row.get("text", "")}
    queries = {}
    for line in queries_raw.splitlines():
        if line.strip():
            row = json.loads(line)
            queries[str(row["_id"])] = row["text"]
    qrels: dict[str, dict[str, int]] = {}
    reader = csv.reader(io.StringIO(qrels_raw), delimiter="\t")
    next(reader, None)  # header: query-id, corpus-id, score
    for row in reader:
        if len(row) >= 3:
            qrels.setdefault(row[0], {})[row[1]] = int(row[2])
    return Dataset(name, corpus, queries, qrels, [])


def sample_dataset(ds: Dataset, num_queries: int, max_docs: int, seed: int) -> Dataset:
    """Seeded sample: N queries that have a relevant doc, plus their relevant docs,
    topped up with random distractors to `max_docs`.

    Every judged-relevant document of a sampled query is always kept, so qrels
    stay complete. The corpus is smaller than the full benchmark, which makes
    retrieval EASIER than the published full-corpus task; compare models only
    against each other, not against published leaderboard numbers.
    """
    rng = random.Random(seed)
    notes = []
    eligible = sorted(q for q, rel in ds.qrels.items()
                      if q in ds.queries and any(g > 0 and d in ds.corpus for d, g in rel.items()))
    if not eligible:
        raise DatasetError("No query has a relevant document in the corpus.")
    if num_queries > len(eligible):
        notes.append(f"Requested {num_queries} queries but only {len(eligible)} are eligible.")
    chosen = sorted(rng.sample(eligible, min(num_queries, len(eligible))))

    qrels = {q: {d: g for d, g in ds.qrels[q].items() if d in ds.corpus} for q in chosen}
    required = sorted({d for rel in qrels.values() for d, g in rel.items() if g > 0})
    if len(required) > max_docs:
        notes.append(f"Corpus size raised from {max_docs} to {len(required)}: "
                     "all relevant documents of the sampled queries must be indexed.")
        max_docs = len(required)
    others = sorted(set(ds.corpus) - set(required))
    extra = rng.sample(others, min(max_docs - len(required), len(others)))
    doc_ids = sorted(required + extra)
    return Dataset(ds.name, {d: ds.corpus[d] for d in doc_ids}, {q: ds.queries[q] for q in chosen}, qrels, notes)
