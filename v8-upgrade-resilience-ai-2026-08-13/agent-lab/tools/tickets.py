"""The tools the agent can call. Every one is a plain MongoDB query.

Each returns a JSON-serialisable dict with a `summary` line the model can read
directly, plus the structured rows behind it. That split matters: the summary
is what goes back into the prompt (cheap, short), while the rows are what the
CLI prints and what session memory keeps for follow-up questions.

None of these tools write. A read-only tool surface is the right default for a
demo an operator drives with natural language.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import config  # noqa: E402
import embeddings  # noqa: E402

from .registry import Param, tool  # noqa: E402

PRIORITIES = ["critical", "high", "medium", "low"]
STATUSES = ["open", "in_progress", "waiting_on_customer", "resolved", "closed"]
OPEN_STATUSES = ["open", "in_progress", "waiting_on_customer"]
_RANK = {p: i for i, p in enumerate(PRIORITIES)}

_PROJECT = {
    "_id": 0, config.EMBEDDING_FIELD: 0,
}


def _age(doc: dict) -> str:
    created = doc.get("created_at")
    if not isinstance(created, datetime):
        return "unknown"
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
    if hours < 1:
        return f"{int(hours * 60)}m ago"
    if hours < 48:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f}d ago"


def _row(doc: dict) -> dict:
    """Trim a ticket to the fields worth showing and feeding back to the model."""
    return {
        "ticket_id": doc.get("ticket_id"),
        "title": doc.get("title"),
        "priority": doc.get("priority"),
        "status": doc.get("status"),
        "service": doc.get("service"),
        "queue": doc.get("queue"),
        "customer_id": doc.get("customer_id"),
        "assignee": doc.get("assignee"),
        "age": _age(doc),
    }


def _sorted_by_urgency(rows: list) -> list:
    return sorted(rows, key=lambda r: _RANK.get(r["priority"], 99))


@tool("get_recent_tickets",
      "The most recently created tickets, newest first. Use for 'what has come "
      "in lately' with no other qualifier.",
      limit=Param(int, "how many tickets to return", default=5),
      status=Param(str, "restrict to one status, or 'any'", default="any"))
def get_recent_tickets(limit=5, status="any"):
    query = {} if status == "any" else {"status": status}
    if status != "any" and status not in STATUSES:
        raise ValueError(f"status must be 'any' or one of {STATUSES}")
    docs = list(config.get_tickets()
                .find(query, _PROJECT)
                .sort("created_at", -1)
                .limit(max(1, min(limit, 25))))
    rows = [_row(d) for d in docs]
    scope = "" if status == "any" else f" with status {status}"
    return {
        "summary": f"{len(rows)} most recent tickets{scope}.",
        "rows": rows,
        "query": query,
    }


@tool("list_high_priority",
      "Open tickets at or above a priority, most urgent first. Use for "
      "'what needs attention', 'what is urgent', 'high priority'.",
      min_priority=Param(str, "lowest priority to include",
                         default="high", choices=PRIORITIES),
      limit=Param(int, "how many tickets to return", default=10),
      include_resolved=Param(bool, "also include resolved and closed tickets",
                            default=False))
def list_high_priority(min_priority="high", limit=10, include_resolved=False):
    allowed = PRIORITIES[:_RANK[min_priority] + 1]
    query = {"priority": {"$in": allowed}}
    if not include_resolved:
        query["status"] = {"$in": OPEN_STATUSES}
    docs = list(config.get_tickets().find(query, _PROJECT))
    rows = _sorted_by_urgency([_row(d) for d in docs])[:max(1, min(limit, 25))]
    by_priority = {}
    for r in rows:
        by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1
    tally = ", ".join(f"{p}: {by_priority[p]}"
                      for p in PRIORITIES if p in by_priority)
    return {
        "summary": f"{len(rows)} tickets at {min_priority} or above "
                   f"({tally or 'none'}).",
        "rows": rows,
        "query": query,
    }


@tool("summarize_open_incidents",
      "Aggregate view of currently open work: counts by priority, status and "
      "service, plus the worst offenders. Use for 'what is going on', "
      "'give me a summary', 'status of the queue'.",
      hours=Param(int, "only tickets created in the last N hours; 0 for all",
                  default=0),
      top_services=Param(int, "how many services to break out", default=5))
def summarize_open_incidents(hours=0, top_services=5):
    match = {"status": {"$in": OPEN_STATUSES}}
    if hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        match["created_at"] = {"$gte": cutoff}

    coll = config.get_tickets()
    total = coll.count_documents(match)

    def group(field):
        return {r["_id"]: r["n"] for r in coll.aggregate([
            {"$match": match},
            {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
            {"$sort": {"n": -1, "_id": 1}},
        ])}

    by_priority = group("priority")
    by_status = group("status")
    by_service = group("service")
    by_theme = group("theme")

    worst = _sorted_by_urgency(
        [_row(d) for d in coll.find(match, _PROJECT)])[:5]

    window = f" in the last {hours}h" if hours else ""
    urgent = by_priority.get("critical", 0) + by_priority.get("high", 0)
    return {
        "summary": f"{total} open tickets{window}; {urgent} at high or "
                   f"critical priority.",
        "total_open": total,
        "by_priority": {p: by_priority[p] for p in PRIORITIES
                        if p in by_priority},
        "by_status": {s: by_status[s] for s in OPEN_STATUSES if s in by_status},
        "by_service": dict(list(by_service.items())[:top_services]),
        "by_theme": by_theme,
        "most_urgent": worst,
        "query": match,
    }


def _vector_search(query: str, limit: int) -> list:
    """$vectorSearch over the stored ticket embeddings."""
    pipeline = [
        {"$vectorSearch": {
            "index": config.VECTOR_INDEX,
            "path": config.EMBEDDING_FIELD,
            "queryVector": embeddings.embed_query(query),
            "numCandidates": max(limit * 15, 100),
            "limit": limit,
        }},
        {"$project": {**_PROJECT, "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(config.get_tickets().aggregate(pipeline))


def _regex_search(query: str, limit: int) -> list:
    """Fallback: match any meaningful query token against title or description.

    Not semantic, but honest about it — and at this data volume it is instant
    and needs no index, which keeps the lab runnable on any tier.
    """
    terms = embeddings.tokens(query)[:8]
    if not terms:
        return []
    clauses = [{field: {"$regex": t, "$options": "i"}}
               for t in terms for field in ("title", "description")]
    docs = list(config.get_tickets().find({"$or": clauses}, _PROJECT))
    # Rank by how many distinct query terms each ticket matches.
    def hits(doc):
        blob = f"{doc.get('title', '')} {doc.get('description', '')}".lower()
        return sum(1 for t in terms if t in blob)
    docs.sort(key=lambda d: (-hits(d), d.get("ticket_id", "")))
    return docs[:limit]


@tool("search_tickets",
      "Find tickets matching a description of a problem, in words. Use when "
      "the operator asks about a topic, service or symptom rather than a "
      "priority or a date.",
      query=Param(str, "what to look for, in natural language"),
      limit=Param(int, "how many tickets to return", default=5))
def search_tickets(query, limit=5):
    limit = max(1, min(limit, 25))
    if config.USE_VECTOR_SEARCH:
        docs = _vector_search(query, limit)
        method = "vector search"
    else:
        docs = _regex_search(query, limit)
        method = "keyword scan"
    rows = [_row(d) for d in docs]
    for row, doc in zip(rows, docs):
        if "score" in doc:
            row["score"] = round(doc["score"], 4)
    return {
        "summary": f"{len(rows)} tickets matching '{query}' via {method}."
                   + ("" if rows else " Try different wording."),
        "rows": rows,
        "method": method,
    }


@tool("get_ticket",
      "Full detail for one ticket, including its description. Use when the "
      "operator names a specific ticket id such as TCK-1004.",
      ticket_id=Param(str, "the ticket id, e.g. TCK-1004"))
def get_ticket(ticket_id):
    doc = config.get_tickets().find_one(
        {"ticket_id": ticket_id.strip().upper()}, _PROJECT)
    if not doc:
        return {"summary": f"No ticket with id {ticket_id}.", "rows": []}
    row = _row(doc)
    row["description"] = doc.get("description")
    row["theme"] = doc.get("theme")
    row["comment_count"] = doc.get("comment_count")
    return {
        "summary": f"{row['ticket_id']}: {row['title']} "
                   f"({row['priority']}, {row['status']}, {row['age']}).",
        "rows": [row],
    }
