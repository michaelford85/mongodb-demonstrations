"""A tiny in-memory stand-in for the tickets collection.

Used only by verify_offline.py, so the tool layer and the agent loop can be
exercised end to end with no cluster. It implements exactly the operations the
tools use and nothing more: find/sort/limit, find_one, count_documents, and the
$match/$group/$sort aggregation the summary tool runs.

Not a MongoDB emulator. If a tool starts using an operator this does not
understand, it raises rather than quietly returning the wrong rows.
"""
from datetime import datetime, timedelta, timezone


def _matches(doc: dict, query: dict) -> bool:
    for field, cond in query.items():
        if field == "$or":
            if not any(_matches(doc, c) for c in cond):
                return False
            continue
        value = doc.get(field)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                if op == "$in":
                    if value not in operand:
                        return False
                elif op == "$gte":
                    if value is None or value < operand:
                        return False
                elif op == "$exists":
                    if (value is not None) != operand:
                        return False
                elif op == "$regex":
                    if operand.lower() not in str(value or "").lower():
                        return False
                elif op == "$options":
                    continue
                else:
                    raise NotImplementedError(f"operator {op}")
        elif value != cond:
            return False
    return True


def _project(doc: dict, projection: dict) -> dict:
    if not projection:
        return dict(doc)
    excluded = {f for f, keep in projection.items() if not keep}
    return {k: v for k, v in doc.items() if k not in excluded}


class Cursor:
    def __init__(self, docs: list):
        self._docs = docs

    def sort(self, field, direction=1):
        self._docs.sort(key=lambda d: d.get(field), reverse=direction < 0)
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self, docs: list):
        self.docs = docs

    def find(self, query=None, projection=None):
        return Cursor([_project(d, projection)
                       for d in self.docs if _matches(d, query or {})])

    def find_one(self, query=None, projection=None):
        for doc in self.docs:
            if _matches(doc, query or {}):
                return _project(doc, projection)
        return None

    def count_documents(self, query=None, limit=0):
        n = sum(1 for d in self.docs if _matches(d, query or {}))
        return min(n, limit) if limit else n

    def aggregate(self, pipeline: list):
        docs = list(self.docs)
        rows = None
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if _matches(d, stage["$match"])]
            elif "$group" in stage:
                spec = stage["$group"]
                field = spec["_id"].lstrip("$")
                counts = {}
                for d in docs:
                    counts[d.get(field)] = counts.get(d.get(field), 0) + 1
                rows = [{"_id": k, "n": v} for k, v in counts.items()]
            elif "$sort" in stage:
                if rows is None:
                    raise NotImplementedError("$sort before $group")
                for field, direction in reversed(list(stage["$sort"].items())):
                    key = "n" if field == "n" else field
                    rows.sort(key=lambda r: (r[key] is None, r[key]),
                              reverse=direction < 0)
            else:
                raise NotImplementedError(f"stage {list(stage)}")
        return rows if rows is not None else docs


def load(tickets: list) -> FakeCollection:
    """Turn the JSON corpus into documents with real timestamps, as seed does."""
    now = datetime.now(timezone.utc)
    docs = []
    for t in tickets:
        doc = dict(t)
        age = doc.pop("age_hours")
        doc["created_at"] = now - timedelta(hours=age)
        if doc["status"] in ("resolved", "closed"):
            doc["resolved_at"] = doc["created_at"] + timedelta(
                hours=min(age * 0.5, 48))
        docs.append(doc)
    return FakeCollection(docs)
