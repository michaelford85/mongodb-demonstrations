"""Synthetic guidance corpus for the CropTrace Knowledge Assistant.

Short, invented product-guidance and residue-risk notes. This is the *only*
corpus the Knowledge Assistant is allowed to ground answers on — retrieval runs
over these notes, and any Claude answer is constrained to the retrieved subset.
Nothing here is real agronomic advice; it exists to make retrieval concrete.
"""

from __future__ import annotations

NOTES = [
    {"note_id": "KN-001", "crop": "Grape", "category": "Fungicide",
     "title": "Downy mildew pressure after wet springs",
     "body": "Sustained leaf wetness and warm nights raise downy mildew "
             "pressure on grapevines. Guidance favours protectant fungicide "
             "timing before rain events and respecting the pre-harvest "
             "interval so residue stays below the MRL at harvest."},
    {"note_id": "KN-002", "crop": "Apple", "category": "Insecticide",
     "title": "Codling moth timing and residue windows",
     "body": "Codling moth control is most effective at egg hatch. Late-season "
             "applications risk elevated residue at harvest; prefer earlier "
             "windows or biocontrol options as harvest approaches."},
    {"note_id": "KN-003", "crop": "Strawberry", "category": "Biocontrol",
     "title": "Biocontrol as a low-residue option near harvest",
     "body": "For strawberries close to harvest, biological products with "
             "short pre-harvest intervals help keep residue low while managing "
             "botrytis pressure under humid conditions."},
    {"note_id": "KN-004", "crop": "Tomato", "category": "Fungicide",
     "title": "Early blight and pre-harvest interval discipline",
     "body": "Early blight on tomato is managed with rotation and protectant "
             "coverage. Track the pre-harvest interval carefully; back-to-back "
             "late sprays are the most common driver of elevated residue."},
    {"note_id": "KN-005", "crop": "Lettuce", "category": "Herbicide",
     "title": "Residual herbicides and leafy-crop residue risk",
     "body": "Leafy crops concentrate residue on the harvested part. Prefer "
             "pre-plant residual herbicides over late post-emergence passes to "
             "reduce residue risk on lettuce heads at harvest."},
    {"note_id": "KN-006", "crop": "Potato", "category": "Insecticide",
     "title": "Colorado beetle and tuber residue",
     "body": "Foliar insecticide for Colorado beetle rarely drives tuber "
             "residue, but haulm-timing and product choice still matter for "
             "worker re-entry intervals and overall label compliance."},
    {"note_id": "KN-007", "crop": "Grape", "category": "Biocontrol",
     "title": "Restricted-status products near harvest",
     "body": "When a product moves to restricted status, review any planned "
             "late-season treatments. Substitute a low-residue biocontrol or "
             "extend the interval so predicted residue stays under the MRL."},
    {"note_id": "KN-008", "crop": "Apple", "category": "Fungicide",
     "title": "Scab management without stacking residue",
     "body": "Apple scab needs consistent early coverage. Avoid stacking "
             "multiple late fungicide applications of the same chemistry, which "
             "raises both resistance pressure and residue at harvest."},
    {"note_id": "KN-009", "crop": "Tomato", "category": "Insecticide",
     "title": "Whitefly pressure and humidity",
     "body": "Whitefly thrives in warm, humid tunnels. Rotate modes of action "
             "and prefer options with short pre-harvest intervals when fruit is "
             "already sizing to protect the residue profile at harvest."},
    {"note_id": "KN-010", "crop": "Strawberry", "category": "Fungicide",
     "title": "Botrytis and canopy management",
     "body": "Botrytis risk rises with dense canopy and free moisture. Combine "
             "canopy airflow with well-timed protectant sprays, respecting the "
             "pre-harvest interval to keep residue low on ripe fruit."},
    {"note_id": "KN-011", "crop": "Potato", "category": "Herbicide",
     "title": "Weed control timing in potato",
     "body": "Pre-emergence weed control reduces the need for late passes. "
             "Late herbicide applications near haulm destruction can raise "
             "residue concerns and complicate the harvest window."},
    {"note_id": "KN-012", "crop": "Lettuce", "category": "Biocontrol",
     "title": "Beneficials for aphid pressure in leafy crops",
     "body": "Releasing beneficial insects for aphid control avoids residue "
             "entirely on lettuce, an attractive option when the crop is close "
             "to harvest and residue tolerance is tight."},
]


def note_text(note: dict) -> str:
    """Canonical text embedded for a note — identical on ingest and query."""
    parts = [note.get("title", ""), note.get("body", ""),
             note.get("crop", ""), note.get("category", "")]
    return " \n".join(p for p in parts if p)
