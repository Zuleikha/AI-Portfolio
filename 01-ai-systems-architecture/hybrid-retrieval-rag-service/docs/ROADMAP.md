# Roadmap

Known gaps, ordered by what would break first under real use. Each entry names
the files involved so the work is actionable rather than aspirational.

## Blocking public deployment

### Authentication and rate limiting
`/ingest` allows anyone who can reach the service to write to the index;
`/query` allows anyone to spend Anthropic and Cohere credits. Neither is
acceptable on a reachable endpoint.

- **Files:** `src/api/main.py`, `config/settings.py`, `src/app.py`
- **Approach:** `X-API-Key` header checked by a FastAPI dependency, key from
  settings; in-memory token bucket per key.
- **Watch out for:** the Streamlit client must send the key too, so both sides
  change together.

### Generic error responses
`/query` and `/ingest` return `str(exc)` in the 500 body, leaking paths and
provider internals.

- **Files:** `src/api/main.py`
- **Approach:** log the exception server-side with a request ID, return the ID
  and a generic message. Tests asserting on error text need updating.

### Upload size limit
`await file.read()` pulls the whole upload into memory with no cap.

- **Files:** `src/api/main.py`
- **Approach:** max-bytes setting, `413` when exceeded.

## Correctness and cost under load

### BM25 index rebuilt on every query
`HybridRetriever._sparse()` scans the entire store and reconstructs `BM25Okapi`
per query. Latency and read cost are both O(corpus).

- **Files:** `src/rag/retriever.py`, `src/store/pinecone_store.py`
- **Approach:** cache the corpus in memory, invalidate on ingest. Persist a
  sidecar index later if the corpus outgrows one process.
- **Watch out for:** cache staleness across multiple workers — acceptable for a
  single worker, but it must be documented.

### Blocking store calls on the async event loop
The Pinecone client is synchronous but is called from async handlers, stalling
every in-flight request during a call.

- **Files:** `src/store/pinecone_store.py`, `src/rag/retriever.py`, `src/rag/pipeline.py`
- **Approach:** wrap in `asyncio.to_thread()`. Semantics unchanged.

### Index count fetched per query
`pipeline.query()` checks `store.count`, which issues a `describe_index_stats()`
call on every query and on `/health`.

- **Files:** `src/rag/pipeline.py`, `src/api/main.py`
- **Approach:** cache locally, update on ingest.

### Unbounded conversation history
`_history` is keyed by a client-supplied `conversation_id` and never expires.

- **Files:** `src/rag/pipeline.py`
- **Approach:** LRU cap (~500 conversations) via `OrderedDict` eviction.

## Quality

| Item | Files | Approach |
|---|---|---|
| RRF dedup keys on `content[:120]`, so chunks sharing a prefix collapse | `src/rag/retriever.py` | Key on `source::chunk_index`, fall back to a full-content hash |
| CORS origin hardcoded to `localhost:8501` | `src/api/main.py` | Move to settings, env-overridable |
| New `httpx.AsyncClient` per rerank call | `src/rag/reranker.py` | Reuse one client and its connection pool |
| API route calls the private `ingestor._ingest()` | `src/api/main.py` | Promote to a public `ingest_text()` |
| No retry or backoff on Anthropic and Pinecone calls | `src/rag/generator.py`, `src/store/pinecone_store.py` | SDK `max_retries` plus explicit timeouts |
| Prompt injection from ingested documents | `src/rag/generator.py` | Injection-resistance clause in the system prompt; sanitise context delimiters |
| `/documents` scans the whole index | `src/api/main.py` | Maintain a source-count cache |

## Longer term

- **Offline evaluation.** There is no retrieval-quality harness — no RAGAS, no
  needle-in-haystack set. Retrieval correctness is currently pinned only by
  unit tests on the RRF formula, which tests the maths, not the results.
- **Metrics export.** The collector is in-memory and resets on restart.
  Prometheus exposition format would make it scrapeable.
- **Dependency pinning.** Dependencies use `>=` constraints; a lockfile or
  constraints file would make builds reproducible.
- **Multilingual support.** The embedding and rerank models are English-only.
