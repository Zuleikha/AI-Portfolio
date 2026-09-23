# Security

## Current posture

This service is built to run locally or behind a trusted boundary. It is **not
hardened for public exposure**, and the gaps below are stated plainly rather
than implied.

| Control | Status |
|---|---|
| Secrets in environment variables only | ✅ Implemented |
| `.env` git-ignored | ✅ Implemented |
| Config validated at import, fails fast | ✅ Implemented |
| Input validation on all request bodies | ✅ Implemented (Pydantic v2, bounded fields) |
| Upload file-type allowlist | ✅ Implemented (`.pdf`, `.txt`, `.md`) |
| Authentication | ❌ Not implemented |
| Rate limiting | ❌ Not implemented |
| Upload size limit | ❌ Not implemented |
| Generic error responses | ❌ Internal exception text is returned to the client |
| Prompt-injection defences | ❌ Not implemented |

## Threats

### Unauthenticated write access
`POST /ingest` has no auth. Anyone who can reach the service can add documents
to the index, which means anyone can influence future answers. If you deploy
this anywhere reachable, put authentication in front of it first.

### Unauthenticated spend
`POST /query` triggers paid calls to Cohere and Anthropic. Without auth or rate
limiting, an open endpoint is an open budget.

### Memory exhaustion
`/ingest` reads each uploaded file fully into memory with no size cap. A large
enough upload will exhaust a small container.

### Information disclosure
Query and ingest handlers currently return `str(exc)` in the HTTP 500 body,
which can leak filesystem paths and provider error detail.

### Prompt injection
Ingested documents are untrusted input that flows directly into the model's
context. A document containing instructions ("ignore previous instructions
and…") is a live injection vector. The system prompt constrains the model
toward grounding but does not defend against this specifically.

## Secrets

Three API keys are required: `ANTHROPIC_API_KEY`, `COHERE_API_KEY`,
`PINECONE_API_KEY`. All are read from the environment by `config/settings.py`.

- Never commit `.env`. Use `.env.example` as the template.
- Keys are never logged. `structlog` output contains request metadata and
  timings, not credentials.
- In a hosted deployment, set them through the platform's secret store rather
  than baking them into an image.

## Data handling

Uploaded document text and its embeddings are sent to Cohere (embedding and
reranking) and Anthropic (generation), and stored in Pinecone. Do not ingest
material you are not permitted to send to third-party providers.

No document content is written to the application's logs. Conversation history
is held in memory only and is lost on restart.

## Reporting

Open a GitHub issue for anything that is not itself sensitive. For a genuine
vulnerability, contact the maintainer directly rather than filing publicly.
