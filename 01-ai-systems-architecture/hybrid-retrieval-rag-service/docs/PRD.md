# Product Requirements

## Problem

Answering questions from a document set requires either reading everything or
trusting a general-purpose model that has never seen the documents. The first
does not scale; the second produces confident, unverifiable answers.

## Goal

A service that answers natural-language questions using only a supplied corpus,
and shows which passage each claim came from.

## Users

| User | Need |
|---|---|
| Someone querying a document set | Ask in plain language, get an answer they can verify |
| The engineer operating it | Know per-stage latency, token spend and error rate |

## Functional requirements

| # | Requirement |
|---|---|
| F1 | Accept `.pdf`, `.txt` and `.md` uploads; extract text; index them |
| F2 | Split text on sentence boundaries into token-sized chunks with overlap |
| F3 | Retrieve candidates by both semantic similarity and exact-term match |
| F4 | Fuse the two candidate lists into one ranking |
| F5 | Rerank the fused list before generation |
| F6 | Generate an answer grounded only in retrieved context, with inline citations |
| F7 | State plainly when the context does not answer the question |
| F8 | Maintain per-conversation history so follow-up questions have context |
| F9 | Expose liveness, indexed-document count and operational metrics over HTTP |
| F10 | Ingest anything present in `data/raw/` at startup without manual action |

## Non-functional requirements

| # | Requirement | Current state |
|---|---|---|
| N1 | Run inside 512 MB RSS | Met — embeddings and reranking are hosted, so no PyTorch at startup |
| N2 | No API key required to run the test suite | Met — 130 tests, providers mocked |
| N3 | Fail fast on missing configuration | Met — settings validated at import |
| N4 | Structured, machine-readable logs | Met — `structlog` JSON output |
| N5 | Degrade rather than fail when reranking is unavailable | Met — falls back to embedding-score order |
| N6 | Authenticated access | **Not met** — no auth; tracked in ROADMAP |
| N7 | Sparse retrieval cost independent of corpus size | **Not met** — BM25 rebuilds per query; tracked in ROADMAP |

## Out of scope

- Fine-tuning any model. All three model roles are hosted third-party APIs.
- Multi-tenancy. One corpus, one index.
- OCR. Scanned PDFs with no text layer are not handled.
- Non-English corpora. The embedding and rerank models chosen are English-only.

## Success criteria

- An answer cites the chunk it came from, and the citation is correct.
- A question with no supporting context returns a refusal, not a guess.
- Adding a document makes it queryable without a restart.
- Per-stage latency is visible on every response.
