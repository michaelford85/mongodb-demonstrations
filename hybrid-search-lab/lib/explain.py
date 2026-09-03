"""Turn a pipeline into a copy-pasteable mongosh snippet.

The GUI shows this next to every result set so you can drop into mongosh
and run the identical aggregation against the same cluster and namespace.
"""
import json

from lib.client import DB_NAME, COLLECTION_NAME


def to_mongosh(pipeline: list) -> str:
    """Render a pipeline as a `db.getSiblingDB(...).coll.aggregate([...])` call."""
    body = json.dumps(pipeline, indent=2)
    # json emits `true`/`false`/`null` which mongosh (JS) also accepts, so the
    # snippet is valid as-is. Indent the pipeline body one level for readability.
    body = "\n".join("  " + line for line in body.splitlines())
    return (
        f'use {DB_NAME}\n\n'
        f'db.{COLLECTION_NAME}.aggregate(\n{body}\n)'
    )


# Short, plain-language explanation of each stage, keyed by its operator.
STAGE_NOTES = {
    "$search": "Atlas Search BM25 — ranks docs by literal word overlap in the plot.",
    "$vectorSearch": "Atlas Vector Search — Atlas embeds your query text with the "
                     "autoEmbed model and finds the nearest plot vectors by cosine "
                     "similarity. No client-side embedding.",
    "$rankFusion": "Runs the semantic and keyword pipelines, ranks each result set "
                   "independently, then fuses the ranks (RRF). Weights tune each "
                   "leg's contribution.",
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
