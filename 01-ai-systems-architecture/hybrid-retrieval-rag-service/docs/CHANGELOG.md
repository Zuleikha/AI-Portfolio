# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0]

Initial release.

### Added

- Document ingestion for `.pdf`, `.txt` and `.md`, with per-file error
  isolation and automatic ingestion of `data/raw/` at startup.
- Sentence-aware chunking at 512 tokens with 64-token overlap, carrying source
  metadata through to citations.
- Hybrid retrieval: dense Pinecone ANN search and BM25 sparse search fused with
  Reciprocal Rank Fusion (`k = 60`).
- Cross-encoder reranking via Cohere `rerank-v3.5`, with fallback to
  embedding-score order when unavailable.
- Grounded generation with Anthropic `claude-sonnet-4-6`, numbered context
  blocks and enforced inline citations.
- Per-conversation history, truncated to the last three turns.
- FastAPI service exposing `/query`, `/ingest`, `/documents`, `/metrics`,
  `/health` and conversation deletion.
- Streamlit chat interface with file upload and live metrics.
- `structlog` JSON logging and an in-memory metrics collector with a rolling
  100-request latency window.
- Environment-bound configuration validated at import via `pydantic-settings`.
- Docker image and Compose file running the API and UI together.
- 130 tests covering chunking, retrieval fusion, reranking fallbacks,
  generation, orchestration, metrics and every API route, with all external
  providers mocked.
