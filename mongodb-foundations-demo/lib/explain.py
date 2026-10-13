"""Render a search pipeline as a copy-pasteable mongosh snippet.

The Search & RAG sections show this next to every result set so a presenter can
drop into mongosh and run the identical aggregation against the same cluster and
namespace — the clearest way to prove the GUI is not hiding anything.
"""

from __future__ import annotations

import json

from lib.mongo_client import DB_NAME
from lib.search_config import KNOWLEDGE


def to_mongosh(pipeline: list, collection: str = KNOWLEDGE) -> str:
    """Render a pipeline as a `db.<coll>.aggregate([...])` call for mongosh."""
    body = json.dumps(pipeline, indent=2)
    # json emits true/false/null, which mongosh (JS) also accepts, so the
    # snippet is valid as-is. Indent the body one level for readability.
    body = "\n".join("  " + line for line in body.splitlines())
    return "use {}\n\ndb.{}.aggregate(\n{}\n)".format(DB_NAME, collection, body)


# Short, plain-language explanation of each stage, keyed by its operator.
STAGE_NOTES = {
    "$search": "Atlas Search BM25 — ranks chunks by literal word overlap in the "
               "text field.",
    "$vectorSearch": "Atlas Vector Search — Atlas embeds your query text with the "
                     "autoEmbed model and finds the nearest chunk vectors by "
                     "cosine similarity. No client-side embedding.",
    "$rankFusion": "Runs the semantic and keyword pipelines, ranks each result "
                   "set independently, then fuses the ranks (RRF). Weights tune "
                   "each leg's contribution.",
    "$project": "Shapes the output and surfaces the relevance score via $meta.",
    "$limit": "Caps how many documents flow onward.",
}


def stage_notes(pipeline: list) -> list:
    """Return (operator, note) pairs for the top-level stages of a pipeline."""
    notes = []
    for stage in pipeline:
        op = next(iter(stage))
        notes.append((op, STAGE_NOTES.get(op, "")))
    return notes
