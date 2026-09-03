# Agent Lab — a task-focused agent over MongoDB

A support-operations agent that answers questions about a ticket queue by
calling tools. Every tool is a plain MongoDB query. The point of the lab is the
machinery *around* the model — the tool schema, argument validation, the
plan/act/observe loop, and short-term memory — because that is the part you own
and the part that decides whether the agent is trustworthy.

It runs with no API key. The default `LLM_PROVIDER=offline` swaps the language
model for a rule-based planner that reads the same prompt and returns the same
JSON, so the loop is genuine even when the reasoning is not. Point it at a real
model to see planning quality change while nothing around it moves.

Everything is fictitious: the team, its services (`billing-api`,
`checkout-web`, `identity`, …), and its customers (`acct-0001`, …).

## What the agent can do

Five read-only tools. No tool writes; that is the right default for something
an operator drives in natural language.

| Tool | MongoDB operation | Answers |
| --- | --- | --- |
| `get_recent_tickets` | `find` + `sort(created_at)` | "what has come in lately" |
| `list_high_priority` | `find` on priority + status | "what needs attention" |
| `summarize_open_incidents` | `$match` / `$group` aggregation | "what is going on" |
| `search_tickets` | regex scan, or `$vectorSearch` | "anything about *X*" |
| `get_ticket` | `find_one` on `ticket_id` | "show me TCK-1042" |

See exactly what the model sees:

```bash
python app/main.py --tools
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in MONGODB_URI
python data/build_tickets.py
python app/seed.py
python app/main.py
```

`data/build_tickets.py` is deterministic for a given `--count` and `--seed`, so
everyone in a workshop gets byte-identical tickets. Ages are stored as *hours
before seeding*, and `app/seed.py` turns them into real dates, so "recent" stays
meaningful however long after generation the lab is run.

Check what is loaded at any point with `python app/seed.py --status`.

## Configuration

All of it is environment-driven; see `.env.example` for the full annotated set.
Nothing here provisions a cluster — that is `../../atlas-cluster-provisioning`.

| Variable | Default | Notes |
| --- | --- | --- |
| `MONGODB_URI` | — | required; `MONGODB_CERT` for X.509 instead of a password |
| `LLM_PROVIDER` | `offline` | `offline`, `openai`, `anthropic` |
| `LLM_API_KEY` | — | required unless offline |
| `LLM_MODEL` | `gpt-4o-mini` | match it to the provider |
| `MAX_STEPS` | `4` | tool calls allowed per operator turn |
| `MEMORY_TURNS` | `8` | conversation turns kept |
| `SHOW_TRACE` | `true` | print plan / tool call / observation |
| `USE_VECTOR_SEARCH` | `false` | see below |

Leave `SHOW_TRACE` on for a workshop. The trace is the thing being taught.

### Optional: semantic search

`search_tickets` defaults to a regex scan, which is instant at 120 tickets and
needs no particular Atlas tier. To swap in Atlas Vector Search:

```bash
python app/seed.py --embed              # store an embedding per ticket
python app/seed.py --vector-index       # M10+ required
python app/seed.py --status             # wait for queryable=True
# then set USE_VECTOR_SEARCH=true
```

Order matters, and the flags are mutually exclusive. `--embed` reseeds the
collection, which drops the search index with it, so `--vector-index` has to come
afterwards. Passing both at once does not work either: `--vector-index` wins and
`--embed` is ignored. Get it wrong and `search_tickets` reports
`0 tickets ... via vector search` rather than an error, because an absent index
and an empty result look the same to the tool.

`EMBEDDING_PROVIDER=offline` produces deterministic hashed vectors — real
plumbing, meaningless recall, no key. Set `voyage` or `openai` with an
`EMBEDDING_API_KEY` for embeddings that actually retrieve well.

The agent does not change either way. That is the argument for putting search
behind a tool boundary: the retrieval strategy is an implementation detail of
one tool, not a property of the agent.

## Workshop scripts

Three scripted conversations in `scripts/`. Each is a plain list of questions,
one per line, replayed through the same code path as typing them:

```bash
python app/main.py --script scripts/01-triage.txt
python app/main.py --script scripts/02-retrieval.txt
python app/main.py --script scripts/03-memory.txt
```

**`01-triage.txt` — one question, three different tools.**
"Give me a summary of what is going on" becomes an aggregation. "What needs
attention most urgently?" becomes a priority filter — a *different* tool, chosen
from the wording alone. Then "tell me more about the second one" resolves
against what was just listed, with no ticket id spoken.

**`02-retrieval.txt` — retrieval versus lookup.**
A topical question with no structural cue routes to `search_tickets`. Rerun the
same script with `USE_VECTOR_SEARCH=true` and the results change while the trace
above them does not. An explicit ticket id always wins over search.

**`03-memory.txt` — memory, and its limits.**
A recency question, then two follow-ups that name nothing. Then `/reset`, then
the same follow-up again — which now has nothing to resolve against, and the
agent says so instead of guessing. That failure is the exercise: an
unconstrained model invents a plausible ticket id here.

Session commands: `/tools`, `/memory`, `/trace`, `/reset`, `/quit`.

## Verifying without a cluster

```bash
python verify_offline.py
```

Substitutes an in-memory collection (`fake_mongo.py`) for MongoDB and checks
the tool shapes, argument validation, that each scripted question routes to the
intended tool, and that memory resolves "the second one" correctly. Useful
before a workshop, and as a regression net when changing the planner.

It does not exercise `$vectorSearch`, which needs a real cluster.

## Where this stops

Deliberate limits, worth naming out loud rather than hiding:

- **Memory is in-process and forgotten on exit.** Persisting the transcript to
  MongoDB is the obvious next step; keeping it in memory here makes the boundary
  between the agent's state and the database it queries unambiguous.
- **Read-only tools.** No tool mutates a ticket. Adding a write is where
  confirmation prompts and audit trails start to matter.
- **One tool call per turn** under the offline planner. `MAX_STEPS` allows more,
  and a real model will use them.

## Live demo script

Copy-pasteable from a clean shell. Everything is read from the environment, so
exporting works whether or not you have created a `.env`.

```bash
export MONGODB_URI='your-atlas-connection-string'

# The planner. 'offline' is the default and needs no key — start there.
export LLM_PROVIDER='openai'
export LLM_API_KEY='your-llm-provider-key'
export LLM_MODEL='gpt-4o-mini'

cd v8-upgrade-resilience-ai-2026-08-13/agent-lab

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# 1. Generate the tickets — deterministic, identical for every attendee
python data/build_tickets.py

# 2. Load them into MongoDB (drops the collection first unless --keep)
python app/seed.py

# 3. Confirm what landed
python app/seed.py --status

# 4. Show the tool catalogue exactly as the model sees it
python app/main.py --tools

# 5. Interactive session — /tools, /memory, /trace, /reset, /quit
python app/main.py
```

This lab is **CLI only**; there is no web UI and nothing to serve with uvicorn.
The three run modes are all `app/main.py`:

```bash
python app/main.py                                  # interactive
python app/main.py --ask 'what needs attention most urgently?'   # one turn
python app/main.py --script scripts/01-triage.txt   # replay a conversation
```

The scripted form is the one to use on a projector — same code path as typing,
but the pacing is fixed and nothing gets mistyped mid-demo:

```bash
python app/main.py --script scripts/01-triage.txt      # tool selection
python app/main.py --script scripts/02-retrieval.txt   # retrieval vs lookup
python app/main.py --script scripts/03-memory.txt      # memory, and its limits
```

To rehearse without an LLM key, leave the provider on its default and skip the
two `LLM_*` exports above — the loop, the tools, and memory are all unchanged:

```bash
export LLM_PROVIDER='offline' LLM_API_KEY=''
python app/main.py --script scripts/01-triage.txt
```

That still needs `MONGODB_URI`, because the tools are real queries and
`app/main.py` exits early if the collection is empty or unreachable. To check
the lab with no cluster at all, use the offline harness instead:

```bash
python verify_offline.py
```

Add the semantic-search variant only if the cluster is M10 or larger, then rerun
`02-retrieval.txt` to show the results change while the trace does not:

```bash
export EMBEDDING_PROVIDER='voyage'
export EMBEDDING_API_KEY='your-embedding-provider-key'

python app/seed.py --embed          # re-seed, storing a vector per ticket
python app/seed.py --vector-index   # create the Atlas vector index
python app/seed.py --status         # wait for queryable=True

USE_VECTOR_SEARCH=true python app/main.py --script scripts/02-retrieval.txt
```

Run those three in order and do not combine `--embed` with `--vector-index`;
`--embed` reseeds and so drops the index, and passing both together silently
skips the embedding step. Either mistake yields `0 tickets ... via vector search`
instead of an error.

## Optional scenarios

If you want to go beyond the core agent walkthrough, consider:

- Designing a second, slightly different synthetic dataset (for example, tasks instead of tickets) and reusing the same agent tools against it.
- Demonstrating a “read-only” agent mode that only answers questions, then contrasting it with a mode that is allowed to call write-capable tools.
- Swapping in a different agent framework or orchestration pattern and discussing how the responsibilities stay the same even if the implementation changes.

These scenarios are optional and should only be used when there is enough time and appetite to explore variations on the core agent pattern.

