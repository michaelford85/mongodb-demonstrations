"""Seed definitions for the fictitious DocsCo knowledge base.

Three groups of documents, each doing a different job in the demo:

  SHOWCASE  hand-written articles that answer one of the example queries
            *without reusing the query's words*. Keyword search cannot find
            them; vector search can.

  DECOY     articles that are stuffed with the query's words but answer a
            different question. Keyword search ranks them first; the reranker
            is what pushes them back down.

  FILLER    combinatorially generated support articles that give the corpus
            enough volume for numCandidates and BM25 scoring to behave
            realistically.

Everything is synthetic. DocsCo, its products, and its people do not exist.
"""

PRODUCTS = ["Ledger", "Dispatch", "Atlas Reports", "Signal", "Vault"]
AUDIENCES = ["administrators", "developers", "support agents", "analysts"]
CATEGORIES = ["billing", "onboarding", "security", "integrations",
              "troubleshooting", "reporting", "performance", "account"]

# ── Showcase: the semantic-gap articles ───────────────────────────────────────
# Query "why is my invoice more than last month" has no lexical overlap with
# "proration", "seat count", or "usage tier" — which is the whole point.
SHOWCASE = [
    {
        "title": "Understanding proration on mid-cycle plan changes",
        "category": "billing",
        "product": "Ledger",
        "audience": "administrators",
        "body": (
            "When a workspace changes plan part-way through a cycle, DocsCo "
            "splits the period in two and charges each half at its own rate. "
            "The resulting line items rarely match the flat figure quoted on "
            "the pricing page, and the difference persists for exactly one "
            "cycle before settling. Seat additions behave the same way: each "
            "new seat is charged from the day it was assigned, not from the "
            "start of the period."
        ),
    },
    {
        "title": "What happens when a teammate leaves the workspace",
        "category": "account",
        "product": "Ledger",
        "audience": "administrators",
        "body": (
            "Removing somebody from a workspace releases their seat "
            "immediately, but the credit appears on the following statement "
            "rather than the current one. Their documents stay where they are "
            "and ownership transfers to the workspace owner. Anything they "
            "had shared by link keeps working until the link is revoked."
        ),
    },
    {
        "title": "Requests are accepted but nothing appears downstream",
        "category": "integrations",
        "product": "Dispatch",
        "audience": "developers",
        "body": (
            "A 202 response means DocsCo has taken custody of the payload, "
            "not that the receiving system has processed it. If the "
            "destination endpoint returns a non-2xx status, Dispatch holds "
            "the message and tries again with widening gaps for up to six "
            "hours before parking it in the dead letter queue, where it can "
            "be replayed by hand."
        ),
    },
    {
        "title": "Signing in stopped working after the company switched providers",
        "category": "security",
        "product": "Vault",
        "audience": "support agents",
        "body": (
            "When an organisation moves to a new identity provider, existing "
            "sessions survive until they expire, so the problem often shows "
            "up hours later and only for some people. The fix is to re-issue "
            "the metadata document and ask affected users to start a fresh "
            "session in a private window. Local passwords are not consulted "
            "once federated access is enforced."
        ),
    },
    {
        "title": "Numbers in the dashboard disagree with the exported file",
        "category": "reporting",
        "product": "Atlas Reports",
        "audience": "analysts",
        "body": (
            "The dashboard reads from a rolling summary refreshed every "
            "fifteen minutes, while an export is assembled from the raw event "
            "stream at the moment you request it. Late-arriving events are "
            "therefore visible in one and not yet the other. Comparing the "
            "two is only meaningful once the summary window has closed."
        ),
    },
    {
        "title": "Large workspaces feel sluggish in the afternoon",
        "category": "performance",
        "product": "Signal",
        "audience": "administrators",
        "body": (
            "Scheduled digests are generated on the hour, and a workspace "
            "with many saved views can queue enough of them to delay "
            "interactive requests. Spreading digest schedules across the hour, "
            "or trimming views nobody opens, restores responsiveness without "
            "changing plan."
        ),
    },
]

# ── Decoys: lexically attractive, semantically wrong ──────────────────────────
# Each one repeats the *literal wording* of an example query while answering a
# different question, so BM25 ranks it first and the reranker has to demote it.
DECOY = [
    {
        "title": "Where to find a bill and how the bill list is sorted",
        "category": "billing",
        "product": "Ledger",
        "audience": "administrators",
        "body": (
            "The bill list shows one row per month, with the newest month "
            "first. You can re-sort the list so an older month sits higher, "
            "pin a month you refer to often, or hide any month with no "
            "activity. None of this alters a bill in any way — it only "
            "changes which month you see and where in the list it appears."
        ),
    },
    {
        "title": "Glossary: request, accepted, and system",
        "category": "integrations",
        "product": "Dispatch",
        "audience": "developers",
        "body": (
            "Definitions only. A request is a single call. A request is "
            "accepted once the system has taken custody of it. The other "
            "system is whichever party receives the request. This page never "
            "describes what the system does with a request — it only defines "
            "the words that other articles use."
        ),
    },
    {
        "title": "Password rules for people who log in with a password",
        "category": "security",
        "product": "Vault",
        "audience": "administrators",
        "body": (
            "Local policy for people who log in with a password: minimum "
            "length, character classes, how often the password must be "
            "changed, and how many past passwords are remembered. People who "
            "log in this way are covered here; nothing in this article "
            "changes for anybody else."
        ),
    },
]


# ── Filler: combinatorial support content ─────────────────────────────────────
# One template per category. `{product}` and `{audience}` are substituted, and
# a variant clause is appended so no two bodies are identical.
FILLER_TEMPLATES = {
    "billing": (
        "This article explains how {product} usage is measured for {audience} "
        "and where the totals appear in the statement. {variant}"
    ),
    "onboarding": (
        "A first-week checklist for {audience} setting up {product}: invite "
        "the team, pick a workspace name, and confirm notification defaults. "
        "{variant}"
    ),
    "security": (
        "Access controls available to {audience} in {product}, including role "
        "assignment, session length, and audit visibility. {variant}"
    ),
    "integrations": (
        "How {product} exchanges data with other systems, and what {audience} "
        "should check when a connection is first established. {variant}"
    ),
    "troubleshooting": (
        "Diagnostic steps for {audience} when {product} behaves unexpectedly, "
        "starting with the activity log and working outwards. {variant}"
    ),
    "reporting": (
        "Building and sharing views in {product} for {audience}, including "
        "scheduling and export formats. {variant}"
    ),
    "performance": (
        "What governs responsiveness in {product} for {audience}, and which "
        "settings are worth changing before contacting support. {variant}"
    ),
    "account": (
        "Workspace and membership administration in {product} as it affects "
        "{audience}, from invitation through to removal. {variant}"
    ),
}

FILLER_VARIANTS = [
    "Changes take effect on the next request; no restart is needed.",
    "Only workspace owners can complete the final step.",
    "The setting is per workspace, not per user.",
    "Historical records are never rewritten by this change.",
    "An entry is added to the audit trail either way.",
    "The default is deliberately conservative and suits most teams.",
    "Limits are advisory and can be raised on request.",
    "The same procedure applies in every region.",
]

FILLER_TITLES = {
    "billing": "How {product} usage is counted for {audience}",
    "onboarding": "Getting {audience} started with {product}",
    "security": "{product} access controls for {audience}",
    "integrations": "Connecting {product} to other systems",
    "troubleshooting": "Diagnosing unexpected {product} behaviour",
    "reporting": "Views, schedules and exports in {product}",
    "performance": "Keeping {product} responsive at scale",
    "account": "Managing {product} workspaces and membership",
}

# ── Example queries surfaced in the UI ────────────────────────────────────────
# Each is worded the way a person would ask it, deliberately avoiding the
# vocabulary of the article that actually answers it.
EXAMPLE_QUERIES = [
    "why is my bill higher than last month",
    "we accepted the request but the other system never got it",
    "people cannot log in since IT changed something",
    "the dashboard total does not match the file I downloaded",
    "everything slows down after lunch",
    "what happens to files when someone quits",
]
