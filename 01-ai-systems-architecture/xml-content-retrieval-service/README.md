# XML Content Retrieval Service

> Part of [ai-portfolio](../../README.md) · Personal project · **AI Systems & Architecture**

**In one line:** search and question-answering over structured XML documents, using each document's own sections as the building blocks.

## Why it matters

Technical manuals (DITA) and research articles (JATS) already mark where each section starts and ends. This service uses that structure instead of cutting text into fixed-size pieces, and then **measures** whether that actually helps.

## Key results

| | |
|---|---|
| Documents | DITA technical topics and open-access PubMed Central articles (fetched by a script, not redistributed) |
| Stack | ChromaDB, OpenAI embeddings, FastAPI, Streamlit |
| vs an untuned splitter | Clearly better |
| vs a well-tuned splitter | A tie on accuracy, with less text retrieved (42% less on DITA, about 10% on articles) |
| Tests | 149, all run offline |

## The key decision

I expected section-based chunks to win on real articles. **They didn't**, and the results say so, with confidence intervals, instead of overstating it.

## Honest limits

- Small evaluation sets (22 and 38 questions), so most differences are within the margin of error
- Tables and figures are not searchable
- The comparison used keyword search (BM25); the live service uses embeddings

## Run it

```bash
cp .env.example .env      # add your OPENAI_API_KEY
docker compose up
```

Then open http://localhost:8501 (UI) or http://localhost:8000/docs (API).

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (parsing rules, full evaluation, design decisions)

🕘 **Development history:** first published here; there is no separate public repository.
