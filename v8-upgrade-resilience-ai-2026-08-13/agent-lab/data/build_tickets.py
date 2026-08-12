"""Generate the synthetic support ticket dataset.

    python data/build_tickets.py              # writes data/tickets.json
    python data/build_tickets.py --count 200

Deterministic for a given --count and --seed, so everyone in a workshop gets
byte-identical data. Timestamps are stored as an *offset in hours from seeding
time* rather than an absolute date, so "recent" and "the last 24 hours" stay
meaningful however long after generation the lab is actually run.

Everything is fictitious: the team, its services, and its customers.
"""
import argparse
import json
import random
from pathlib import Path

OUT_FILE = Path(__file__).parent / "tickets.json"

PRIORITIES = ["critical", "high", "medium", "low"]
STATUSES = ["open", "in_progress", "waiting_on_customer", "resolved", "closed"]
SERVICES = ["billing-api", "checkout-web", "notifications", "search-index",
            "reporting", "identity", "file-storage"]
QUEUES = ["frontline", "platform", "billing", "security"]
ASSIGNEES = ["operator-01", "operator-02", "operator-03", "operator-04", None]
CUSTOMERS = [f"acct-{n:04d}" for n in range(1, 41)]

# Templates keyed by the theme they belong to. `incident` themes are the ones
# that should dominate a "what is on fire right now" summary.
THEMES = [
    ("incident", "Elevated error rate on {service}",
     "Customers on {customer} report intermittent failures when calling "
     "{service}. Error rate has been above the alerting threshold for "
     "{n} minutes. No recent deploy to {service}, so a dependency is the "
     "likely cause."),
    ("incident", "{service} latency spike during peak hours",
     "Requests to {service} are taking several seconds to complete for "
     "{customer}. The slowdown tracks the daily traffic peak and clears on "
     "its own afterwards, which points at capacity rather than a defect."),
    ("incident", "Queued messages not draining in {service}",
     "The backlog in {service} has been growing for {n} minutes and is not "
     "draining. Nothing is being lost, but {customer} is seeing stale data "
     "downstream until the queue clears."),
    ("access", "{customer} cannot sign in after provider change",
     "Nobody at {customer} can start a new session since their identity "
     "provider was reconfigured. Existing sessions still work, so the "
     "problem is only visible to people signing in fresh."),
    ("access", "Permission denied on {service} for a whole team",
     "A team at {customer} lost access to {service} without any role change "
     "being recorded on our side. Needs an audit trail check before anything "
     "is granted back."),
    ("billing", "Unexpected charge on the {customer} statement",
     "{customer} is querying a line item they did not expect this cycle. "
     "Their plan changed mid-period, so proration is the likely explanation, "
     "but it needs confirming before we reply."),
    ("billing", "Invoice not delivered to {customer}",
     "The statement for {customer} was generated but never arrived. Their "
     "billing contact changed recently and the old address may still be on "
     "file."),
    ("data", "Report totals disagree with export for {customer}",
     "{customer} sees one figure in the dashboard for {service} and a "
     "different one in the file they export. Both are probably correct at "
     "different moments; needs explaining rather than fixing."),
    ("data", "Missing records in {service} extract",
     "The nightly extract from {service} came through short for {customer}. "
     "Row counts are off by a small margin, consistently, across several "
     "days."),
    ("request", "Raise the rate limit for {customer} on {service}",
     "{customer} is hitting the default rate limit on {service} during their "
     "own batch window and is asking for headroom. No incident, just a "
     "capacity request that needs a decision."),
    ("request", "Add a second admin for {customer}",
     "{customer} wants a second person able to administer their workspace so "
     "they are not dependent on one individual. Routine, needs the existing "
     "owner to confirm."),
    ("howto", "How does {service} handle a retry?",
     "{customer} is asking what happens to a request to {service} that fails "
     "on the first attempt, and whether they need to retry it themselves. "
     "Documentation question, no fault reported."),
]


def _ticket(rng: random.Random, seq: int, max_age_hours: int) -> dict:
    theme, title_t, body_t = THEMES[seq % len(THEMES)]
    service = rng.choice(SERVICES)
    customer = rng.choice(CUSTOMERS)
    minutes = rng.choice([15, 25, 40, 55, 90, 120])

    # Incidents skew urgent and recent; requests and how-tos skew calm and old.
    if theme == "incident":
        priority = rng.choices(PRIORITIES, weights=[35, 40, 20, 5])[0]
        status = rng.choices(STATUSES, weights=[40, 35, 5, 15, 5])[0]
        age = round(rng.triangular(0, max_age_hours * 0.4, 2), 2)
    elif theme in ("access", "billing", "data"):
        priority = rng.choices(PRIORITIES, weights=[5, 30, 45, 20])[0]
        status = rng.choices(STATUSES, weights=[25, 25, 20, 20, 10])[0]
        age = round(rng.uniform(0, max_age_hours * 0.7), 2)
    else:
        priority = rng.choices(PRIORITIES, weights=[0, 10, 40, 50])[0]
        status = rng.choices(STATUSES, weights=[20, 15, 15, 25, 25])[0]
        age = round(rng.uniform(max_age_hours * 0.2, max_age_hours), 2)

    return {
        "ticket_id": f"TCK-{1000 + seq}",
        "title": title_t.format(service=service, customer=customer),
        "description": body_t.format(service=service, customer=customer,
                                     n=minutes),
        "theme": theme,
        "priority": priority,
        "status": status,
        "service": service,
        "queue": rng.choice(QUEUES),
        "customer_id": customer,
        "assignee": rng.choice(ASSIGNEES),
        # Hours before seeding time; app/seed.py turns this into a real date.
        "age_hours": age,
        "comment_count": rng.randint(0, 7),
    }


def generate(count: int, seed: int, max_age_hours: int) -> list:
    rng = random.Random(seed)
    tickets = [_ticket(rng, i, max_age_hours) for i in range(count)]
    tickets.sort(key=lambda t: t["age_hours"])
    return tickets


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic ticket set.")
    parser.add_argument("--count", type=int, default=120,
                        help="tickets to generate (default: 120)")
    parser.add_argument("--seed", type=int, default=8,
                        help="RNG seed for reproducible output (default: 8)")
    parser.add_argument("--max-age-hours", type=int, default=336,
                        help="oldest ticket, in hours before seeding (default: 336)")
    args = parser.parse_args()

    tickets = generate(args.count, args.seed, args.max_age_hours)
    OUT_FILE.write_text(json.dumps(tickets, indent=2) + "\n")

    def tally(field):
        counts = {}
        for t in tickets:
            counts[t[field]] = counts.get(t[field], 0) + 1
        return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))

    print(f"Wrote {len(tickets)} tickets to {OUT_FILE}")
    print(f"  priority  {tally('priority')}")
    print(f"  status    {tally('status')}")
    print(f"  theme     {tally('theme')}")
    print("\nNext: python app/seed.py")


if __name__ == "__main__":
    main()
