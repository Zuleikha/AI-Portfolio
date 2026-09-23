# Design Notes

Implementation detail behind the components listed in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Chunking

Fixed-width character splitting cuts sentences in half, and a half sentence
embeds badly — the vector lands somewhere between the two ideas it straddles.
`SentenceAwareChunker` therefore splits on sentence boundaries first, then packs
sentences into chunks until a token budget is reached.

- **Budget: 512 tokens.** Large enough to hold a complete argument, small enough
  that a chunk is about one idea. Retrieval precision falls off above this.
- **Overlap: 64 tokens.** A claim that spans a boundary appears in both
  neighbours, so it is retrievable from either side.
- **Token counting** uses a local fast tokenizer, not a character heuristic.
  The hosted embedding model publishes no local tokenizer, so this is a stable
  proxy rather than an exact count — good enough for sizing, and it costs no
  network call and no PyTorch import.

Metadata (source filename, chunk index) is attached at chunk creation and
survives all the way to the citation shown to the user.

## Retrieval

Two legs, run against the same corpus:

| Leg | Strength | Blind spot |
|---|---|---|
| Dense (Pinecone ANN) | Paraphrase, synonymy, conceptual match | Rare literal tokens — codes, IDs, names |
| Sparse (BM25) | Exact terms, unusual vocabulary | Anything phrased differently from the query |

Their scores are not comparable — cosine similarity and BM25 saturation live on
different scales, and normalising between them means inventing a conversion.
Reciprocal Rank Fusion sidesteps that by discarding scores and using rank only:

```
score(d) = Σ over legs of  1 / (k + rank(d, leg)),  k = 60
```

A document ranked first by one leg and absent from the other still scores
`1/61`, which beats a document ranked tenth by both. `k = 60` is the value from
the original RRF paper; it damps the difference between ranks 1 and 2 so a
single leg cannot dominate.

Current limitation: the BM25 index is rebuilt from a full store scan on every
query. That is fine for a demonstration corpus and wrong past a few thousand
chunks. See [ROADMAP.md](ROADMAP.md).

## Reranking

The fused list is ~10 candidates. A cross-encoder scores query and passage
jointly, which a bi-encoder cannot — the bi-encoder had to commit to a single
vector per passage before it ever saw the query. Running it on 10 candidates
rather than the whole corpus keeps the cost bounded.

Two fallbacks, both tested: with no API key configured, and on any API failure,
the reranker returns the input ordered by embedding score. Reranking improves
results; it is not load-bearing.

## Generation

The system prompt is passed through Anthropic's dedicated `system` parameter
rather than as a first message, and enforces four rules: ground every claim,
cite inline by chunk number, be concise, never fabricate. Context blocks are
numbered so `[1]` in the answer maps to a specific retrieved chunk.

Conversation history is truncated to the last three turns. Beyond that, older
turns add prompt cost without improving answers, and risk pulling the model
back to a superseded topic.

## Configuration

All settings are `pydantic-settings` fields bound to environment variables and
validated at import time. A missing or malformed key fails the process at
startup rather than at first request — which is the difference between a failed
deploy and a user-visible incident.

Numeric settings carry range constraints (`chunk_size` 64–2048, `temperature`
0–2, `retrieval_top_k` 1–50) so a typo in an environment variable is caught at
boot rather than producing quietly degraded results.

## Observability

`structlog` emits JSON. Request timing is middleware, not per-handler code, so
no route can forget to record it. `RequestMetrics` is an in-memory singleton
holding counts, error totals, token usage and a rolling 100-request latency
window, exposed at `/metrics`.

It resets on restart and is not in Prometheus exposition format. That is a
deliberate floor, not a finished monitoring story — see [ROADMAP.md](ROADMAP.md).

## Error handling

Ingestion isolates failures per file: one unreadable PDF in a directory does
not abort the other nine. Query failures increment the error counter, log the
full exception server-side, and return an HTTP error to the caller.
