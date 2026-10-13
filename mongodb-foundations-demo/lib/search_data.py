"""Deterministic, industry-neutral corpus for the Search & RAG sections.

Every source document is an invented internal knowledge article for a fictional
platform, "Example Cloud Platform". No real organisation, product, or person is
named, there is no PII, and nothing is vertical-specific — the topics (access,
backups, incidents, retention, billing, API limits) recur everywhere.

The demo *chunks* these documents at seed time, the same way a real RAG pipeline
would: `chunk_document` walks each article's headed sections and packs
paragraphs into overlapping, bounded chunks. Chunking is deterministic, so a
re-seed always produces byte-identical chunk documents.
"""

from __future__ import annotations

# Chunking budget. Small on purpose so a short article still yields several
# chunks and the retrieval demo has something to rank.
CHUNK_TARGET_CHARS = 480
SENTENCE_OVERLAP = True  # carry the last sentence into the next chunk


def _paragraphs(body: str) -> list:
    return [p.strip() for p in body.split("\n\n") if p.strip()]


def _last_sentence(text: str) -> str:
    parts = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    if not parts:
        return ""
    tail = parts[-1]
    return tail if tail.endswith(".") else tail + "."


def chunk_document(doc: dict, target: int = CHUNK_TARGET_CHARS) -> list:
    """Split one source document into (section, text) chunks.

    Paragraphs are packed up to `target` characters. A `## Heading` line starts
    a new section and flushes the current chunk. When a chunk is flushed mid
    section, its last sentence is carried into the next chunk as overlap, so a
    fact that straddles a boundary is not lost to retrieval.
    """
    chunks: list = []
    section = doc["title"]
    buf = ""
    for para in _paragraphs(doc["body"]):
        if para.startswith("## "):
            # A heading and the first line of its body share one block here
            # (no blank line between them). Peel the heading off its first
            # line and keep the remaining body as the start of the section.
            head, _, rest = para.partition("\n")
            if buf:
                chunks.append((section, buf.strip()))
                buf = ""
            section = head[3:].strip()
            rest = rest.strip()
            if rest:
                buf = rest
            continue
        candidate = (buf + "\n\n" + para).strip() if buf else para
        if buf and len(candidate) > target:
            chunks.append((section, buf.strip()))
            carry = _last_sentence(buf) if SENTENCE_OVERLAP else ""
            buf = (carry + "\n\n" + para).strip() if carry else para
        else:
            buf = candidate
    if buf:
        chunks.append((section, buf.strip()))
    return chunks


def _token_estimate(text: str) -> int:
    """Rough token count (~1.3 tokens/word) so the demo can show chunk sizing."""
    return round(len(text.split()) * 1.3)


def build_chunks() -> list:
    """Chunk every source document into seed-ready chunk documents."""
    docs = []
    for doc in SOURCE_DOCUMENTS:
        pieces = chunk_document(doc)
        total = len(pieces)
        for idx, (section, text) in enumerate(pieces):
            docs.append({
                "_id": "{}-C{:02d}".format(doc["doc_id"], idx),
                "doc_id": doc["doc_id"],
                "doc_title": doc["title"],
                "source_type": doc["source_type"],
                "section": section,
                "chunk_index": idx,
                "chunk_total": total,
                "text": text,
                "token_estimate": _token_estimate(text),
            })
    return docs


def source_summary() -> list:
    """One row per source document, with its chunk count — for the readiness UI."""
    rows = []
    for doc in SOURCE_DOCUMENTS:
        rows.append({
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "source_type": doc["source_type"],
            "chunks": len(chunk_document(doc)),
        })
    return rows


# Questions for the RAG section. Each is answerable only from the corpus, so a
# grounded answer must cite chunks — the whole point of retrieval-augmented
# generation. `expects` names the source document that holds the answer.
RAG_QUESTIONS = [
    {"q": "How long are deleted customer records kept before permanent erasure?",
     "expects": "DOC-0004"},
    {"q": "What should an on-call engineer do first when a Sev-1 is declared?",
     "expects": "DOC-0003"},
    {"q": "How do I raise my API rate limit, and what are the default limits?",
     "expects": "DOC-0005"},
    {"q": "How often are backups taken and how quickly can data be restored?",
     "expects": "DOC-0002"},
    {"q": "What access does a new joiner get on their first day?",
     "expects": "DOC-0001"},
]

# Queries for the ⑧ MongoDB Search section, chosen so keyword (BM25) and
# semantic (autoEmbed) visibly disagree: intent-based phrasings that share few
# literal words with the text semantic search should still find.
CONTRAST_QUERIES = [
    "what happens to my data after I close my account",
    "the site is down and customers are affected",
    "getting throttled when calling the service too fast",
    "recovering information we lost by accident",
    "giving a brand-new teammate the right permissions",
]

# Invented internal articles. Markdown `## Heading` lines mark section
# boundaries the chunker splits on; every name uses the reserved "Example"
# convention so no reader can mistake it for a real organisation.
SOURCE_DOCUMENTS = [
    {
        "doc_id": "DOC-0001",
        "title": "Access & Onboarding Handbook",
        "source_type": "handbook",
        "body": """## New joiner access
On their first day, a new joiner receives a standard account with read-only \
access to the shared knowledge base, the internal directory, and the support \
ticketing system. No elevated permission is granted by default.

A joiner who needs more than the baseline requests it through the access \
portal, where a team lead approves each grant individually. Production access \
is never part of the first-day baseline.

## Requesting elevated roles
Elevated roles follow least privilege. A request names one environment and one \
purpose, and the portal issues a time-boxed role that expires automatically \
unless it is renewed. Standing production access is not offered to anyone.

## Access reviews
Every role is reviewed each quarter. Owners confirm that each person still \
needs each grant; anything unconfirmed is revoked at the end of the review \
window. Departures trigger an immediate, same-day revocation of all access.""",
    },
    {
        "doc_id": "DOC-0002",
        "title": "Backup & Recovery Runbook",
        "source_type": "runbook",
        "body": """## Backup schedule
A full snapshot of every customer dataset is taken once every twenty-four \
hours. On top of that, incremental backups run every hour, on the hour, so the \
most recent hour of change is always captured.

Snapshots are copied to a second region within fifteen minutes of completion, \
so the loss of a single region never means the loss of a backup.

## Recovery objectives
The recovery point objective is one hour: at most one hour of data can be lost \
in a worst-case failure. The recovery time objective is four hours: a full \
restore completes and service resumes within four hours of the decision to \
restore.

## Verifying a restore
A restore is not considered done until an automated check confirms the row \
counts and the latest timestamps match the source. Restores are rehearsed \
monthly against a scratch environment so the runbook itself stays trustworthy.""",
    },
    {
        "doc_id": "DOC-0003",
        "title": "Incident Response Runbook",
        "source_type": "runbook",
        "body": """## Severity levels
A Sev-1 is a customer-facing outage or data-loss event. A Sev-2 degrades \
service without a full outage. A Sev-3 is a minor issue with a workaround. The \
severity sets the response, not the other way around.

## First actions on a Sev-1
When a Sev-1 is declared, the on-call engineer's first action is to \
acknowledge the page within five minutes and open a dedicated incident \
channel. Before attempting any fix, they post an initial status so support can \
tell affected customers what is known. Only after that status is posted does \
diagnosis begin.

## Communication and roles
An incident has one commander who owns decisions and one scribe who records the \
timeline. Status updates go out at a fixed cadence until the incident is \
resolved, even when the update is only that work continues.

## After the incident
Every Sev-1 and Sev-2 gets a blameless review within five working days, and \
each action item has a named owner and a due date.""",
    },
    {
        "doc_id": "DOC-0004",
        "title": "Data Retention & Deletion Policy",
        "source_type": "policy",
        "body": """## Account closure
When a customer closes their account, their records move into a soft-deleted \
state rather than disappearing at once. Soft-deleted records are retained for \
thirty days, during which the customer can ask for a full restore.

After the thirty-day window passes, the records are permanently erased and \
cannot be recovered by anyone, including support and engineering.

## Backups and erasure
Permanent erasure also removes the records from the next backup cycle, so \
within one further backup rotation no copy of the closed account remains. \
Encryption keys scoped to that account are destroyed at the same time.

## Legal hold
A legal hold, when placed, pauses erasure for the named records until the hold \
is lifted. A hold is the only thing that overrides the thirty-day timeline, and \
every hold is logged with who placed it and why.""",
    },
    {
        "doc_id": "DOC-0005",
        "title": "API Rate Limits Reference",
        "source_type": "api-reference",
        "body": """## Default limits
Every API key is limited to sixty requests per minute and ten thousand \
requests per day. The per-minute limit is enforced as a rolling window, not a \
fixed clock minute, so a burst does not reset at the top of the minute.

## Raising a limit
To raise your rate limit, open a request in the developer portal and state the \
sustained requests-per-minute you need and the reason. Approved increases take \
effect within one business day and are applied per key, not per account.

## Handling throttling
When you exceed a limit the API returns HTTP 429 with a Retry-After header \
giving the seconds to wait. Clients should honour that header with exponential \
backoff rather than retrying immediately, which only deepens the throttling.""",
    },
]

