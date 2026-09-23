# Hybrid Retrieval RAG Service

> Part of [ai-portfolio](../../README.md) · Personal project · **AI Systems & Architecture**

**In one line:** upload documents, ask questions, and get answers with citations back to the exact source passage.

## Why it matters

Keyword search finds exact terms such as names and codes; vector search finds meaning. This service runs both and combines them, so neither kind of question gets missed.

## Key results

| | |
|---|---|
| Retrieval | Vector search (Cohere + Pinecone) and BM25 keyword search, in parallel |
| Merging | Reciprocal Rank Fusion, then a cross-encoder reranker |
| Answers | Claude, with inline citations and per-stage timings |
| Interfaces | FastAPI and a Streamlit UI |
| Tests | 130, with every external service mocked |

## The key decision

No LangChain. Chunking, fusion and prompt building are plain code, so every step is visible and testable.

## Honest limits

- No login or rate limiting: not safe to expose publicly as-is
- The keyword index is rebuilt per question, which won't scale past a few thousand chunks
- Needs paid API keys (Cohere, Pinecone, Anthropic) to run

## Run it

```bash
cp .env.example .env      # add the three API keys
docker compose up
```

Then open http://localhost:8501 (UI) or http://localhost:8000/docs (API).

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (architecture, API, tests)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/hybrid-retrieval-rag-service) with the full commit history. This folder is the current version.
