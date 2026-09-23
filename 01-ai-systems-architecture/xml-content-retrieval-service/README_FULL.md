# XML Content Retrieval Service

Semantic search and grounded Q&A over **structured** documents.

The premise: when a document already carries its own structure in markup, you
can use that structure instead of re-deriving boundaries with a text splitter.
DITA XML declares where a topic starts and where a section ends; JATS does the
same for research articles. **Those declarations become the chunk boundaries**,
and the hierarchy survives into the vector store as filterable metadata.

The project then **measures whether that actually helps**, against fixed-size
windows, on two corpora. The short answer is more interesting than the premise:

> Authored boundaries **beat an untuned splitter** clearly. Against a
> **well-tuned** fixed-size window they are **a tie on retrieval accuracy** — the
> defensible advantages are lower retrieved-context cost and hierarchy metadata
> a splitter cannot produce at all.

Full numbers, confidence intervals and limits: **[`eval/RESULTS.md`](eval/RESULTS.md)**.

## What this is not

This repository is deliberately **not** a second general-purpose RAG service.
Its sibling [`hybrid-retrieval-rag-service`](https://github.com/Zuleikha/hybrid-retrieval-rag-service)
is the retrieval-quality project. This one is the document-parsing project.

| | `hybrid-retrieval-rag-service` | **this repo** |
|---|---|---|
| **The hard problem** | Ranking — getting the right chunk to the top | Chunking — deciding what a chunk *is* |
| Input | PDF, TXT, Markdown — unstructured bytes | DITA and JATS XML — self-describing markup |
| Chunk boundaries | Heuristic splitting at a token budget | `<section>` / `<sec>` elements, exactly as authored |
| Chunk metadata | Source and offset, for citation | Topic id, topic title, section title, section path and depth, short description, source file, derived tags |
| Retrieval | Dense + BM25 in parallel → RRF fusion → cross-encoder rerank | One dense leg, cosine similarity |
| Vector store | Pinecone serverless | ChromaDB, local persistence |
| Embeddings | Cohere `embed-english-v3.0` | OpenAI `text-embedding-3-small` |
| Generation | Anthropic `claude-sonnet-4-6` | OpenAI `gpt-4o-mini` |

**The retrieval stack here is deliberately plain.** Adding RRF and reranking
would demonstrate nothing that the sibling repo does not already demonstrate
better, and it would obscure the point being made: what a chunk boundary is
worth, measured on its own.

## Does structural chunking actually work? — measured

`eval/` compares the production parser against fixed-size character windows
swept across sizes and overlaps, on two corpora, with BM25 held constant so the
*only* thing changing is the chunk boundary. Relevance is containment of a short
answer span lifted verbatim from a labelled section.

| | DITA corpus | JATS / PMC corpus |
|---|---|---|
| Documents | 3 authored topics | 30 research articles |
| Chunks | 12 | 656 |
| Labelled questions | 22 | 38 |
| vs **untuned** window (300c, no overlap) | wins | **+0.208 MRR, CI +0.041 to +0.371** ✅ |
| vs **best-tuned** window | tie | tie (−0.035 MRR, CI −0.145 to +0.073) |
| Retrieved context to reach the answer | **42% less** | 10% less |

**What is claimed, and what is not:**

| ✅ Supported by the numbers | ❌ Not claimed |
|---|---|
| Beats an untuned splitter, significantly | "Better retrieval" in general |
| Matches a well-tuned window on accuracy | Beats a well-tuned window |
| Costs less retrieved context to reach an answer | That the 42% DITA figure generalises — on real articles it is ~10% |
| Preserves `section_path`, `section_title`, `topic_id` as filterable metadata | That metadata's retrieval gain is statistically established at n=38 |

The honest headline is **equivalent accuracy, lower context cost, and hierarchy
metadata a splitter cannot produce** — not "better retrieval". The largest
limitation is sample size: most gaps sit inside their own confidence interval,
and `eval/RESULTS.md` says so in detail rather than quoting the flattering half.

```bash
python -m eval.verify_questions          # check the labels describe the corpus
python -m eval.run_comparison            # DITA
python -m scripts.fetch_pmc --limit 30   # build the JATS corpus (free, no API key)
python -m eval.run_comparison --data data/pmc
```

## Why structural chunking matters

A fixed-window splitter cutting at ~500 tokens will happily slice this in half:

```xml
<section id="system-requirements">
  <title>System Requirements</title>
  <p>Before installing, ensure your system meets the following:</p>
  <ul>
    <li>RAM: 16 GB minimum, 32 GB recommended</li>
    <li>Disk Space: 20 GB free space</li>
  </ul>
</section>
```

Split mid-list and you get one chunk saying "16 GB minimum" with no indication
of what needs 16 GB, and another orphaned from its heading entirely. Both
embed poorly, and neither can be filtered afterwards, because nothing recorded
what they belonged to.

Parsing the markup instead gives one chunk per section, whole, carrying the
answer to *"what is this about?"* in its metadata rather than only in its text:

```json
{
  "chunk_id": "installation_system-requirements",
  "topic_id": "installation",
  "topic_title": "Installing Bentley OpenRoads Designer",
  "section_title": "System Requirements",
  "source_file": "installation",
  "tags": "installation, system-requirements",
  "text": "Before installing, ensure your system meets..."
}
```

Every field lands in ChromaDB alongside the vector, so retrieval can be filtered
by topic or tag, not just ranked by similarity.

### Three details that only structural parsing gets right

| Detail | What the code does |
|---|---|
| **Titles would be counted twice** | Section text is extracted recursively, which pulls the `<title>` in along with the body. It is stripped — but **only when the text starts with it**, so a heading phrase recurring mid-sentence survives |
| **Nested inline markup** | `extract_text()` recurses through children *and* their `tail` text, so `<p>Press <b>OK</b> to continue</p>` yields `"Press OK to continue"`, not `"Press"` |
| **One bad file must not kill the run** | `ET.ParseError` is caught per file, logged as a warning, and parsing continues. A single malformed topic costs you that topic, not the whole index |

## Stack

| Layer | Choice |
|---|---|
| Parsing | `xml.etree.ElementTree` — stdlib, no dependency |
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector store | ChromaDB, persistent, cosine (`hnsw:space`) |
| Generation | OpenAI `gpt-4o-mini`, temperature 0.2 |
| API | FastAPI, Pydantic v2 |
| UI | Streamlit |
| Deployment | Docker Compose — two services, one image |
| Tests | pytest, **149 tests**, fully offline |

## Run it

```bash
cp .env.example .env      # add your OPENAI_API_KEY
docker compose up
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Interactive docs | http://localhost:8000/docs |
| UI | http://localhost:8501 |

Or locally:

```bash
pip install -e ".[dev,ui]"
uvicorn app.api:app --reload           # API
streamlit run app/ui.py                # UI
```

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/index` | Re-parse and re-index every document in the data directory — the explicit rebuild path |
| `POST` | `/search` | Semantic search; returns ranked chunks with their metadata |
| `POST` | `/ask` | Retrieval + generation; returns an answer with its sources |

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I fix a license error?", "n_results": 4}'
```

```json
{
  "query": "How do I fix a license error?",
  "answer": "Verify your network connection and that ports 443 and 80 ...",
  "sources": [
    {
      "topic": "Installing Bentley OpenRoads Designer",
      "section": "Troubleshooting Installation",
      "score": 0.7421,
      "tags": "installation, troubleshooting"
    }
  ]
}
```

**Sources name the topic and the section**, not a page number or a character
offset — because the parser knew what it was cutting.

## Indexing does not re-run on every restart

The startup hook indexes **only when the collection is empty**. A container
restart on an unchanged corpus re-spends nothing on embeddings, and never
briefly empties the collection. `POST /index` remains the explicit,
intentional full rebuild.

Startup indexing is also wrapped: if it fails — a missing `OPENAI_API_KEY`,
say — the API still starts and still serves `/health`, and the failure is
logged with a pointer to `/index`. A service that cannot index is still worth
having up so you can see *why*.

## No API key needed to run the tests

```bash
pytest -q
```

149 tests, fully offline. OpenAI and ChromaDB are both mocked, so the suite
costs nothing and needs no network. The parser tests run against the **real**
sample `.dita` files in `data/` rather than fixtures — the parser's whole job
is handling real markup, so testing it against a simplified stand-in would test
the wrong thing.

The OpenAI client is created lazily on first use, never at import, which is
what makes key-less imports and offline tests possible at all. See
[docs/DECISIONS.md](docs/DECISIONS.md).

## Adding your own documents

Drop `.dita` files into `data/` and call `POST /index`. The parser expects
standard DITA topic structure: a `<topic>` with an `id`, a `<title>`, an
optional `<shortdesc>`, and a `<body>` containing `<section>` elements.

The sample corpus documents Bentley OpenRoads Designer — installation,
configuration and troubleshooting.

## Repository layout

```
app/parser.py       DITA XML → section chunks with metadata
app/jats_parser.py  JATS XML → section chunks; handles nested <sec>
app/dispatch.py     picks a parser from the document's root element
app/indexer.py      OpenAI embeddings → ChromaDB, batched
app/retriever.py    cosine search + grounded answer generation
app/api.py          FastAPI routes and the startup index hook
app/ui.py           Streamlit front end
eval/               chunking comparison, labelled questions, label verifier
scripts/fetch_pmc.py  builds the JATS corpus from PubMed Central
data/               sample DITA corpus (data/pmc/ is fetched and gitignored)
docs/               architecture, decisions, security, roadmap
```

## Known limits

**Parsing.** For DITA, only `<section>` elements under `<body>` become chunks —
`conref`/`keyref` indirection, nested topics, maps and ditamaps are **not**
resolved. For JATS, tables, figures and supplementary material are excluded from
chunk text by design (see `NON_PROSE_TAGS`), so a fact that exists *only* inside
a table is not retrievable. Tags come from a fixed keyword map, not a taxonomy.

**Evidence.** The headline comparison is limited by sample size above all —
22 and 38 labelled questions, where most observed gaps fall inside their own 95%
confidence interval. Retrieval in the comparison is BM25, while production uses
embeddings, so the result is not yet confirmed under dense retrieval. Questions
were authored by the same person who read the corpus; `eval/verify_questions.py`
enforces span uniqueness and flags vocabulary echoes, but that is a guardrail,
not independent authorship. Stated in full in [eval/RESULTS.md](eval/RESULTS.md).

**Corpus.** `data/pmc/` is fetched from PubMed Central and **gitignored, not
redistributed** — PMC Open Access licences vary per article (the sample run
returned CC-BY, CC-BY-NC and CC-BY-NC-ND side by side). `scripts/fetch_pmc.py`
rebuilds it and records each article's id and stated licence in a manifest.

**Service.** Retrieval is a single dense leg with no reranking. There is no auth,
and `/index` spends OpenAI credit on demand.
