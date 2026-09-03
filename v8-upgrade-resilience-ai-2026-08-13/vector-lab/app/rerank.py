"""Reranking: a second, more expensive pass over a small candidate set.

Vector search must be cheap enough to scan an index, so it compares two
independently produced vectors. A reranker instead looks at the query and one
document *together* and scores that pair directly. It cannot be used to search —
far too slow — but over a few dozen candidates it routinely fixes the order.

  voyage   the provider's cross-encoder (RERANK_MODEL).
  offline  a local pair scorer. Not a cross-encoder, but it does the thing a
           cross-encoder does that cosine similarity cannot: it looks at query
           coverage and at how focused the document is, so a page that merely
           repeats the query's words is pushed down.

Both return the candidate list reordered, with a `rerank_score` and the position
each document held before reranking.
"""
import config
import embeddings

_voyage = None


def _offline_pair_score(query: str, text: str) -> float:
    """Coverage of the query's concepts, discounted by how unfocused the text is."""
    q_literal = embeddings._tokens(query)
    q_terms = set(embeddings._expand(q_literal))
    d_tokens = embeddings._tokens(text)
    if not q_terms or not d_tokens:
        return 0.0
    d_terms = set(d_tokens)

    coverage = len(q_terms & d_terms) / len(q_terms)

    # A document that says the same few words over and over has low lexical
    # variety. Keyword-stuffed pages score highly on overlap and badly here.
    variety = len(d_terms) / len(d_tokens)

    # Concept terms the document reaches only through expansion count for less
    # than ones it states outright, which keeps genuinely on-topic pages ahead.
    literal = set(q_literal) & d_terms
    literal_bonus = 0.15 * (len(literal) / max(len(q_literal), 1))

    # Repeating one of the query's own words far more often than the text's
    # length warrants is the signature of a lexical trap rather than an answer.
    repeats = max((d_tokens.count(t) for t in literal), default=0)
    density = repeats / len(d_tokens)
    stuffing_penalty = 1.2 * max(density - 0.04, 0.0)

    return round(0.7 * coverage + 0.3 * variety
                 + literal_bonus - stuffing_penalty, 6)


def _get_voyage():
    global _voyage
    if _voyage is None:
        import voyageai

        key = config.embedding_api_key()
        if not key:
            raise RuntimeError("EMBEDDING_API_KEY is required for reranking")
        _voyage = voyageai.Client(api_key=key)
    return _voyage


def backend() -> str:
    """Which reranker will actually run. Only Voyage exposes a rerank API here."""
    return "voyage" if config.EMBEDDING_PROVIDER == "voyage" else "offline"


def rerank(query: str, candidates: list, limit: int) -> list:
    """Reorder `candidates` (dicts with a body field) and return the top `limit`."""
    if not candidates:
        return []

    for position, doc in enumerate(candidates, start=1):
        doc["vector_rank"] = position

    documents = [f"{d.get(config.TITLE_FIELD, '')}\n{d.get(config.BODY_FIELD, '')}"
                 for d in candidates]

    if backend() == "voyage":
        resp = _get_voyage().rerank(
            query=query,
            documents=documents,
            model=config.RERANK_MODEL,
            top_k=limit,
        )
        ordered = []
        for item in resp.results:
            doc = dict(candidates[item.index])
            doc["rerank_score"] = round(item.relevance_score, 6)
            ordered.append(doc)
        return ordered

    scored = []
    for doc, text in zip(candidates, documents):
        copy = dict(doc)
        copy["rerank_score"] = _offline_pair_score(query, text)
        scored.append(copy)
    scored.sort(key=lambda d: (-d["rerank_score"], d["vector_rank"]))
    return scored[:limit]
