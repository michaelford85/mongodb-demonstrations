"""Prove the lab works with no cluster and no API key.

    python verify_offline.py

Substitutes an in-memory collection for MongoDB (fake_mongo.py) and leaves the
offline planner in place, then checks the parts a workshop depends on:

  * every tool runs and returns the documented shape
  * argument validation rejects what it should
  * the agent routes each scripted question to the intended tool
  * short-term memory resolves "the second one" to the right ticket
  * /reset genuinely drops that context

Not a substitute for a live run: $vectorSearch is never exercised here.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import config  # noqa: E402
import fake_mongo  # noqa: E402

_COLL = fake_mongo.load(json.loads((ROOT / "data" / "tickets.json").read_text()))
config.get_tickets = lambda: _COLL
config.namespace = lambda: "offline.tickets"

import agent as agent_mod  # noqa: E402
import memory  # noqa: E402
import tools  # noqa: E402

FAILURES = []


def check(label: str, condition, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


def _silent(kind, payload):
    pass


def run_tools() -> None:
    section("Tools")
    recent = tools.get("get_recent_tickets").call({"limit": 5})
    check("get_recent_tickets returns 5 rows", len(recent["rows"]) == 5)
    check("get_recent_tickets rows have the documented shape",
          set(recent["rows"][0]) == {"ticket_id", "title", "priority", "status",
                                     "service", "queue", "customer_id",
                                     "assignee", "age"},
          str(sorted(recent["rows"][0])))
    newest = recent["rows"][0]["ticket_id"]
    all_recent = tools.get("get_recent_tickets").call({"limit": 25})
    check("get_recent_tickets is newest first",
          all_recent["rows"][0]["ticket_id"] == newest, newest)
    check("get_recent_tickets honours a status filter",
          all(r["status"] == "open" for r in tools.get("get_recent_tickets")
              .call({"status": "open", "limit": 10})["rows"]))

    high = tools.get("list_high_priority").call({})
    check("list_high_priority is open work only",
          all(r["status"] in ("open", "in_progress", "waiting_on_customer")
              for r in high["rows"]))
    check("list_high_priority is critical-first",
          high["rows"][0]["priority"] in ("critical", "high"),
          high["summary"])

    summary = tools.get("summarize_open_incidents").call({})
    check("summarize_open_incidents counts match rows",
          summary["total_open"] == sum(summary["by_priority"].values()),
          summary["summary"])
    check("summarize_open_incidents breaks out services",
          len(summary["by_service"]) > 1)

    found = tools.get("search_tickets").call({"query": "billing statement"})
    check("search_tickets finds billing tickets", bool(found["rows"]),
          found["summary"])
    top = tools.get("get_ticket").call(
        {"ticket_id": found["rows"][0]["ticket_id"]})["rows"][0]
    blob = f"{top['title']} {top['description']}".lower()
    check("search_tickets ranks a two-term match first",
          "billing" in blob and "statement" in blob, top["title"])
    empty = tools.get("search_tickets").call({"query": "zzzznothinghere"})
    check("search_tickets says so when nothing matches",
          empty["rows"] == [] and "Try different wording" in empty["summary"])

    one = tools.get("get_ticket").call({"ticket_id": "tck-1020"})
    check("get_ticket normalises a lowercase id",
          one["rows"] and one["rows"][0]["ticket_id"] == "TCK-1020")
    check("get_ticket includes the description",
          bool(one["rows"][0].get("description")))
    missing = tools.get("get_ticket").call({"ticket_id": "TCK-9999"})
    check("get_ticket reports an unknown id", missing["rows"] == [])


def run_validation() -> None:
    section("Argument validation")
    for label, name, args in [
        ("unknown parameter rejected", "get_recent_tickets", {"limt": 5}),
        ("bad choice rejected", "list_high_priority",
         {"min_priority": "urgent"}),
        ("missing required argument rejected", "search_tickets", {}),
        ("non-numeric limit rejected", "get_recent_tickets",
         {"limit": "loads"}),
    ]:
        try:
            tools.get(name).call(args)
            check(label, False, "no error raised")
        except ValueError as exc:
            check(label, True, str(exc)[:70])

    try:
        tools.get("delete_everything")
        check("unknown tool rejected", False, "no error raised")
    except KeyError:
        check("unknown tool rejected", True)


def run_routing() -> None:
    section("Routing")
    ag = agent_mod.Agent(memory.Session(), trace=_silent)
    for question, expected in [
        ("Give me a summary of what is going on right now",
         "summarize_open_incidents"),
        ("What needs attention most urgently?", "list_high_priority"),
        ("What has come in over the last few hours?", "get_recent_tickets"),
        ("Anything going on with the billing-api service?", "search_tickets"),
        ("Show me TCK-1020", "get_ticket"),
    ]:
        ag.session.clear()
        answer = ag.ask(question)
        called = [s["tool"] for s in ag.session.turns[-1].steps if "tool" in s]
        check(f"{question!r} -> {expected}", called == [expected], str(called))
        check("  answer is non-empty prose", len(answer) > 20)


def run_memory() -> None:
    section("Short-term memory")
    ag = agent_mod.Agent(memory.Session(), trace=_silent)
    ag.ask("What needs attention most urgently?")
    ids = ag.session.context_ticket_ids()
    check("context holds the listed ticket ids", len(ids) > 2, str(ids[:3]))

    second = ids[1]
    ag.ask("Tell me more about the second one")
    step = ag.session.turns[-1].steps[0]
    check("'the second one' resolves from memory",
          step["tool"] == "get_ticket"
          and step["arguments"]["ticket_id"] == second,
          f"expected {second}, got {step.get('arguments')}")

    ag.session.clear()
    check("reset drops the context", ag.session.context_ticket_ids() == [])
    answer = ag.ask("Tell me more about the first one")
    called = [s["tool"] for s in ag.session.turns[-1].steps if "tool" in s]
    check("with no context it calls nothing rather than inventing an id",
          called == [], str(called))
    check("  and says why", "context" in answer.lower(), answer[:60])


def main() -> None:
    print(f"Offline verification — {len(_COLL.docs)} tickets, "
          f"planner={config.LLM_PROVIDER}")
    run_tools()
    run_validation()
    run_routing()
    run_memory()
    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nAll checks passed")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
