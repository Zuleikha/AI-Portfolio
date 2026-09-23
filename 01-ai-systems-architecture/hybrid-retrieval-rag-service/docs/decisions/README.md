# Architecture Decision Records

One file per decision, numbered in the order they were made. A record states
the context, the decision, and the consequences accepted along with it.

Superseded records stay. They are marked as superseded and link forward to the
record that replaced them — the reasoning behind an abandoned approach is part
of the history worth keeping.

| # | Decision | Status |
|---|---|---|
| [0001](ADR-0001-llm-anthropic-claude-sonnet.md) | LLM: Anthropic `claude-sonnet-4-6` | Accepted |
| [0002](ADR-0002-local-huggingface-embeddings.md) | Embeddings: local HuggingFace model | Superseded by [0006](ADR-0006-hosted-cohere-embeddings.md) |
| [0003](ADR-0003-pinecone-vector-store.md) | Vector store: Pinecone serverless | Accepted |
| [0004](ADR-0004-cohere-rerank-api.md) | Reranking: hosted Cohere Rerank API | Accepted |
| [0005](ADR-0005-hybrid-retrieval-rrf.md) | Retrieval: hybrid dense + BM25, fused with RRF | Accepted |
| [0006](ADR-0006-hosted-cohere-embeddings.md) | Embeddings: hosted Cohere `embed-english-v3.0` | Accepted |

## Adding one

Copy the shape of an existing record: title, status, date, context, decision,
consequences. Number it next in sequence. If it replaces an earlier decision,
mark that one superseded and link both ways.
