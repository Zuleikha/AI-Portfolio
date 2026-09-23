# Decisions

Architectural decisions are recorded individually in [`decisions/`](decisions/).
This page is the index and the summary of *why* the system looks the way it does.

| ADR | Decision | Status |
|---|---|---|
| [0001](decisions/ADR-0001-llm-anthropic-claude-sonnet.md) | Anthropic `claude-sonnet-4-6` for generation | Accepted |
| [0002](decisions/ADR-0002-local-huggingface-embeddings.md) | Local `sentence-transformers` embeddings | Superseded by 0006 |
| [0003](decisions/ADR-0003-pinecone-vector-store.md) | Pinecone serverless as the vector store | Accepted |
| [0004](decisions/ADR-0004-cohere-rerank-api.md) | Hosted Cohere Rerank instead of a local cross-encoder | Accepted |
| [0005](decisions/ADR-0005-hybrid-retrieval-rrf.md) | Hybrid dense + BM25 retrieval fused with RRF | Accepted |
| [0006](decisions/ADR-0006-hosted-cohere-embeddings.md) | Hosted Cohere `embed-english-v3.0` embeddings | Accepted |

## The thread running through them

Three of these decisions (0002 → 0004 → 0006) are the same trade-off resolved
the same way: **hosted API over local model**, because every local
`sentence-transformers` model drags PyTorch into the process and costs roughly
400 MB resident before serving a single request. In a 512 MB budget that is not
a preference, it is the difference between running and not running.

ADR-0002 is kept rather than deleted. It records that local embeddings were
tried deliberately and why they were abandoned — which is more useful to a
future reader than a repository that pretends the first attempt never happened.

## Choices made without a formal ADR

| Choice | Reasoning |
|---|---|
| No LangChain | It was a heavy transitive dependency for what amounts to text splitting and prompt assembly. Both are implemented directly, in less code than the integration would have taken. |
| `pypdf`, not `PyPDF2` | PyPDF2 is unmaintained; `pypdf` is its maintained successor. |
| `pydantic-settings` over `os.getenv` | Type validation and fail-fast startup instead of `None` propagating into a request handler. |
| `ruff` for lint and format | One tool replacing `black` plus `flake8`, one config, one pass. |
| `structlog` over stdlib logging alone | Machine-readable output without hand-formatting every log line. |
| Cohere called over `httpx`, not the SDK | The SDK pulls in `tokenizers` and `huggingface_hub`; the API is two endpoints and a JSON body. |
