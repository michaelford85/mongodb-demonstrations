"""A rule-based stand-in for the LLM, so the lab runs with no key.

It reads the *same* prompt the real model gets and returns the *same* JSON, so
the agent loop cannot tell the difference. What it is not is a language model:
intent comes from keyword rules, and the final answer is assembled from the
observations by template rather than written.

Worth saying out loud in a workshop: this is a deliberately dumb planner. Its
value is that everything *around* the model — tool schemas, validation, the
plan/act/observe loop, session memory — is exactly the real thing, so those are
what the demo is actually teaching. Point LLM_PROVIDER at a real model to see
the planning quality change while the surrounding machinery stays put.
"""
import json
import re

import config

# ── Intent rules, first match wins ────────────────────────────────────────────
# (tool name, argument builder, phrases)
_URGENT = ("urgent", "high priority", "high-priority", "critical", "needs "
           "attention", "worst", "escalat", "on fire", "priorit", "pressing",
           "important")
_SUMMARY = ("summar", "summarise", "summarize", "overview", "what is going on",
            "whats going on", "what's going on", "how are we", "state of",
            "status of", "breakdown", "brief me", "digest", "roll up",
            "rollup", "queue look")
_RECENT = ("recent", "latest", "newest", "just came in", "came in", "last few",
           "new tickets", "today", "past hour", "last hour")

_TICKET_RE = re.compile(r"\b(tck-?\s?\d{3,5})\b", re.IGNORECASE)
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2,
             "3rd": 2, "fourth": 3, "4th": 3, "fifth": 4, "5th": 4,
             "last": -1, "top": 0}
_HOURS_RE = re.compile(r"last\s+(\d{1,3})\s*(hour|hr|h)\b", re.IGNORECASE)
_LIMIT_RE = re.compile(r"\b(?:top|first|show me|give me|list)\s+(\d{1,2})\b",
                       re.IGNORECASE)
# Matched on word boundaries, not as substrings: "it" must not fire on "with".
_FOLLOWUP_RE = re.compile(
    r"\b(that one|that ticket|this one|it|them|those|more details?|"
    r"tell me more|expand|full detail|the description|what does it say|"
    r"open it)\b", re.IGNORECASE)


def _sections(system: str, messages: list) -> tuple:
    """Pull the machine-readable parts the agent puts in the prompt."""
    mode = "answer" if "MODE: answer" in system else "plan"
    last = messages[-1]["content"] if messages else ""
    operator = ""
    observations = []
    context_ids = []

    m = re.search(r"^OPERATOR: (.*)$", last, re.MULTILINE)
    if m:
        operator = m.group(1).strip()

    m = re.search(r"^OBSERVATIONS:\s*(\[.*?\])\s*$", last,
                  re.MULTILINE | re.DOTALL)
    if m:
        try:
            observations = json.loads(m.group(1))
        except json.JSONDecodeError:
            observations = []

    m = re.search(r"^CONTEXT_TICKET_IDS: (.*)$", last, re.MULTILINE)
    if m:
        context_ids = [t.strip() for t in m.group(1).split(",") if t.strip()]

    return mode, operator, observations, context_ids


def _int_in(pattern, text, default=None):
    m = pattern.search(text)
    return int(m.group(1)) if m else default


def _plan(operator: str, observations: list, context_ids: list) -> dict:
    """Choose one tool, or decide there is enough to answer."""
    text = operator.lower()

    # Already acted this turn: the loop only needs one tool call per turn here.
    if observations:
        return {"tool": None,
                "thought": "Observations are in hand; answering."}

    # An explicit ticket id always wins.
    m = _TICKET_RE.search(operator)
    if m:
        ticket_id = re.sub(r"[\s-]+", "-", m.group(1).upper())
        if not ticket_id.startswith("TCK-"):
            ticket_id = "TCK-" + ticket_id.replace("TCK", "").strip("-")
        return {"tool": "get_ticket", "arguments": {"ticket_id": ticket_id},
                "thought": f"The operator named {ticket_id} directly."}

    # A follow-up that leans on what was just shown — resolve from memory.
    if _FOLLOWUP_RE.search(text):
        if not context_ids:
            # The honest answer. Guessing a ticket id here would be the worst
            # possible behaviour, and it is what an unconstrained model does.
            return {"tool": None,
                    "thought": "That refers to something previously shown, "
                               "but there is nothing in context to resolve it "
                               "against."}
        index = 0
        for word, pos in _ORDINALS.items():
            if re.search(rf"\b{word}\b", text):
                index = pos
                break
        try:
            ticket_id = context_ids[index]
        except IndexError:
            ticket_id = context_ids[0]
        return {"tool": "get_ticket", "arguments": {"ticket_id": ticket_id},
                "thought": f"Follow-up referring to {ticket_id} from the "
                           f"previous result."}

    if any(p in text for p in _SUMMARY):
        args = {}
        hours = _int_in(_HOURS_RE, text)
        if hours:
            args["hours"] = hours
        return {"tool": "summarize_open_incidents", "arguments": args,
                "thought": "Asked for an overview, so aggregate rather than "
                           "list."}

    if any(p in text for p in _URGENT):
        args = {}
        if "critical" in text:
            args["min_priority"] = "critical"
        limit = _int_in(_LIMIT_RE, text)
        if limit:
            args["limit"] = limit
        return {"tool": "list_high_priority", "arguments": args,
                "thought": "Asked about urgency, so filter by priority."}

    if any(p in text for p in _RECENT):
        args = {}
        limit = _int_in(_LIMIT_RE, text)
        if limit:
            args["limit"] = limit
        for status in ("open", "in_progress", "resolved", "closed"):
            if status.replace("_", " ") in text or status in text:
                args["status"] = status
                break
        return {"tool": "get_recent_tickets", "arguments": args,
                "thought": "Asked what has come in lately, so sort by date."}

    if not text:
        return {"tool": None, "thought": "Nothing asked."}

    # Anything else is treated as a topical lookup.
    args = {"query": operator}
    limit = _int_in(_LIMIT_RE, text)
    if limit:
        args["limit"] = limit
    return {"tool": "search_tickets", "arguments": args,
            "thought": "No structural cue, so search on the wording."}


def _describe_rows(rows: list, cap: int = 5) -> list:
    lines = []
    for r in rows[:cap]:
        bits = [f"{r.get('ticket_id')} — {r.get('title')}"]
        detail = [str(r[k]) for k in ("priority", "status", "service", "age")
                  if r.get(k)]
        if detail:
            bits.append("(" + ", ".join(detail) + ")")
        if r.get("assignee"):
            bits.append(f"assigned to {r['assignee']}")
        elif "assignee" in r:
            bits.append("unassigned")
        lines.append("  - " + " ".join(bits))
    if len(rows) > cap:
        lines.append(f"  ... and {len(rows) - cap} more")
    return lines


def _answer(operator: str, observations: list) -> str:
    """Assemble prose from the observations. Template-driven, not generated."""
    if not observations:
        if _FOLLOWUP_RE.search(operator):
            return ("I do not have anything in context to resolve that "
                    "against — nothing has been listed in this session yet. "
                    "Ask for a summary, for recent tickets, or name a ticket "
                    "id, and then the follow-up will work.")
        return ("I did not gather anything for that. Try asking for a summary, "
                "for high-priority tickets, for recent tickets, or for a "
                "ticket id such as TCK-1004.")

    out = []
    for obs in observations:
        result = obs.get("result") or {}
        if obs.get("error"):
            out.append(f"The {obs.get('tool')} tool failed: {obs['error']}")
            continue

        name = obs.get("tool")
        out.append(result.get("summary", ""))

        if name == "summarize_open_incidents":
            by_p = result.get("by_priority") or {}
            by_s = result.get("by_service") or {}
            if by_p:
                out.append("By priority: " + ", ".join(
                    f"{k} {v}" for k, v in by_p.items()) + ".")
            if by_s:
                worst_service = next(iter(by_s))
                out.append(f"Most affected service is {worst_service} "
                           f"({by_s[worst_service]} open).")
            urgent = result.get("most_urgent") or []
            if urgent:
                out.append("The ones I would look at first:")
                out.extend(_describe_rows(urgent))
        elif name == "get_ticket":
            rows = result.get("rows") or []
            if rows and rows[0].get("description"):
                out.append(rows[0]["description"])
        else:
            rows = result.get("rows") or []
            if rows:
                out.extend(_describe_rows(rows, cap=10))

    return "\n".join(line for line in out if line)


def complete(system: str, messages: list) -> str:
    """Same contract as a real model: read the prompt, return JSON as text."""
    mode, operator, observations, context_ids = _sections(system, messages)

    if mode == "answer":
        return json.dumps({"answer": _answer(operator, observations)})

    decision = _plan(operator, observations, context_ids)
    if decision.get("tool") is None:
        return json.dumps({"thought": decision.get("thought", ""),
                           "done": True})
    return json.dumps({
        "thought": decision.get("thought", ""),
        "tool": decision["tool"],
        "arguments": decision.get("arguments", {}),
    })
