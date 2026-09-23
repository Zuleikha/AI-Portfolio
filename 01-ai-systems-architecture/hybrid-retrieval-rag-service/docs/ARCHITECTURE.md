# Architecture

## Request flow

```
┌──────────────┐  HTTP   ┌───────────────────────────────────────────────────────┐
│  Streamlit   │ ──────► │  FastAPI (src/api/main.py)                            │
│  frontend    │         │                                                       │
└──────────────┘         │  POST /ingest ─► DocumentIngestor                     │
                         │                   └─ SentenceAwareChunker             │
                         │                   └─ CohereEmbedder                   │
                         │                   └─ PineconeVectorStore (upsert)     │
                         │                                                       │
                         │  POST /query ──► RAGPipeline                          │
                         │                   └─ HybridRetriever                  │
                         │                       ├─ Dense  (Pinecone ANN)        │
                         │                       ├─ Sparse (BM25, rank-bm25)     │
                         │                       └─ RRF fusion (k=60)            │
                         │                   └─ CohereReranker (rerank-v3.5)     │
                         │                   └─ RAGGenerator                     │
                         │                       └─ Anthropic claude-sonnet-4-6  │
                         └───────────────────────────────────────────────────────┘
```

## Module map

Each module hides one concern behind a small interface. Callers depend on the
interface, not the provider.

| Module | File | Public interface | Hides |
|---|---|---|---|
| Ingestion | `src/ingestion/ingest.py` | `DocumentIngestor.ingest_directory / ingest_pdf_bytes` | PDF/TXT/MD loading, text extraction, per-file error isolation |
| Chunking | `src/rag/chunker.py` | `SentenceAwareChunker.chunk(text, metadata)` | Sentence-boundary regex, tokenizer, 512-token sizing, 64-token overlap |
| Embedding | `src/rag/embedder.py` | `CohereEmbedder.embed_query / embed_batch` | Hosted Cohere `embed-english-v3.0`, 1024-dim, async `httpx`, `input_type` per side |
| Vector store | `src/store/pinecone_store.py` | `PineconeVectorStore.add_documents / query / get_all_documents / count` | Index lifecycle, upsert, pagination |
| Retrieval | `src/rag/retriever.py` | `HybridRetriever.retrieve(query, n_results)` | Dense + BM25 legs, RRF fusion (k=60), dedup |
| Reranking | `src/rag/reranker.py` | `CohereReranker.rerank(query, candidates, top_k)` | Rerank API call, no-key and failure fallbacks |
| Generation | `src/rag/generator.py` | `RAGGenerator.generate(query, context_docs, history)` | Prompt assembly, citation rules, token accounting |
| Orchestration | `src/rag/pipeline.py` | `RAGPipeline.query / ingest_chunks / clear_conversation` | Stage ordering, timing, conversation history |
| API | `src/api/main.py` | FastAPI routes | HTTP shape, validation, status codes, lifespan, CORS |
| Monitoring | `src/monitoring/metrics.py` | `configure_logging`, `get_metrics`, `RequestMetrics` | structlog setup, in-memory counters, rolling window |

## Dependencies between modules

```
api/main ──► pipeline ──► retriever ──► store
                      └─► reranker
                      └─► generator ──► Anthropic
                      └─► embedder
                      └─► chunker
ingestion/ingest ──► pipeline (chunker + embedder + store)
```

`config/settings.py` is imported by every module. It validates all environment
variables at import time and is the single source of tunable values.

## Why hybrid retrieval

Dense retrieval matches meaning but misses exact tokens — a part number, an
error code, a surname that never appeared in the embedding model's training
data. BM25 matches those tokens but misses paraphrase. Running both and fusing
with RRF (`score = Σ 1/(k + rank)`, `k = 60`) needs no score normalisation
between two incomparable scales, and a document ranked well by either leg
survives into the final list.

Reranking then does what neither leg can: a cross-encoder scores the query and
the passage *together*, catching relevance that bi-encoder cosine similarity
approximates away. It only runs on the ~10 fused candidates, so the cost is
bounded.

## Testable contracts

Invariants the suite pins, with all providers mocked:

- **Chunker** — never splits mid-sentence; respects token size and overlap; carries metadata through.
- **Retriever** — RRF score is `Σ 1/(k+rank)` with `k=60`; additive across legs; dedups by id.
- **Reranker** — falls back to embedding-score order with no key *and* on API failure; preserves metadata.
- **Generator** — formats numbered context; truncates history to the last 3 turns.
- **Pipeline** — an empty store short-circuits to the "no documents" answer; per-stage latency is recorded.
- **Metrics** — accumulation, averages, rolling 100-request window cap, `to_dict`, singleton behaviour.
- **API** — status codes (503 not ready, 400 bad input, 500 internal), validation boundaries, response shapes.

## Providers

| Concern | Choice | Set in | ADR |
|---|---|---|---|
| LLM | Anthropic `claude-sonnet-4-6` | `settings.llm_model` | [ADR-0001](decisions/ADR-0001-llm-anthropic-claude-sonnet.md) |
| Embeddings | Hosted Cohere `embed-english-v3.0` (1024-dim) | `settings.embedding_model` | [ADR-0006](decisions/ADR-0006-hosted-cohere-embeddings.md) |
| Vector store | Pinecone serverless | `settings.pinecone_index_name` | [ADR-0003](decisions/ADR-0003-pinecone-vector-store.md) |
| Reranker | Cohere `rerank-v3.5` | `src/rag/reranker.py` | [ADR-0004](decisions/ADR-0004-cohere-rerank-api.md) |
| Retrieval | Hybrid dense + BM25 + RRF | `src/rag/retriever.py` | [ADR-0005](decisions/ADR-0005-hybrid-retrieval-rrf.md) |

## Memory budget

The service is sized to run in 512 MB. That constraint drives two choices:
embeddings and reranking are hosted API calls rather than local
`sentence-transformers` models, which would each pull PyTorch (~400 MB
resident) into the process at startup. The only local model artefact is a fast
tokenizer used purely to count tokens for chunk sizing.
