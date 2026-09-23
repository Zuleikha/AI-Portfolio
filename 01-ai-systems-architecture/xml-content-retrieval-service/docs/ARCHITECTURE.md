# Architecture

> Module map, interfaces and contracts. Reflects the code as it actually is.

## What this system is for

Retrieval over documentation that **already carries its own structure**. The
design premise throughout: markup that declares topic and section boundaries is
information, and discarding it to re-derive boundaries heuristically is a loss,
not a simplification.

Every choice below follows from that. It is also what separates this repository
from its sibling — see [Differentiation](#differentiation-from-hybrid-retrieval-rag-service).

## Pipeline

```
INDEXING  (app/parser.py → app/indexer.py)

  data/*.dita
    │
    ├─ ET.parse per file, ET.ParseError caught per file and logged
    │
    ▼
  parse_dita_file()
    topic_id, topic_title, topic_shortdesc  ← from <topic>
    │
    └─ for each <section> under <body>:
         section_id, section_title          ← from the element
         text = extract_text(section)       ← recursive, includes child .tail
         strip the leading title, ONLY if the text starts with it
         tags = generate_tags(topic_title, section_title)
         │
         ▼
       chunk { chunk_id: "<file>_<section_id>", + 7 metadata fields }
    │
    ▼
  index_chunks()
    clear the collection            ← a re-index is a full replace, never a merge
    embed_texts() in batches of 100 ← OpenAI text-embedding-3-small
    collection.add(ids, embeddings, documents, metadatas)


RETRIEVAL  (app/retriever.py → app/api.py)

  query
    │
    ▼
  embed_texts([query])[0]           ← same model, same space
    │
    ▼
  collection.query(n_results, include=[documents, metadatas, distances])
    │
    ▼
  score = round(1 - distance, 4)    ← cosine distance → similarity
    │
    ├─ POST /search  → the chunks, with their metadata
    │
    └─ POST /ask     → chunks as numbered context
                       → gpt-4o-mini, temperature 0.2
                       → answer + sources (topic > section, score, tags)
```

## Chunk boundaries are declared, not guessed

**One `<section>` becomes exactly one chunk.** No token budget, no overlap
window, no recursive character splitter.

The consequences are worth stating, because they are the trade-off:

| | Effect |
|---|---|
| **+** | A chunk is semantically whole — a list is never cut in half, a heading is never orphaned from its body |
| **+** | Metadata is free and exact. Topic and section titles are read off the markup, not inferred |
| **+** | Retrieval can filter, not just rank: ChromaDB holds `topic_id`, `topic_title`, `section_title`, `source_file`, `tags`, `topic_shortdesc` per vector |
| **+** | Chunk ids are stable and meaningful — `installation_system-requirements`, not `chunk_0047`. Re-indexing an unchanged document produces the same ids |
| **−** | **Chunk size is uncontrolled.** A long section becomes a long chunk. There is no split for an outsized section and no merge for a one-line one |
| **−** | It only works on documents that carry structure. Point this at a PDF and there is nothing to parse |

That second minus is the real limit of the approach and is tracked in
[ROADMAP.md](ROADMAP.md).

## Three parsing details that matter

### `extract_text` recurses into tails

```python
for child in element:
    parts.append(extract_text(child))
    if child.tail:
        parts.append(child.tail.strip())
```

Without the `.tail` branch, `<p>Press <b>OK</b> to continue</p>` yields
`"Press OK"` and silently drops `" to continue"` — text that lives *after* a
closing tag but still inside the parent. This is the classic ElementTree trap
and it fails quietly, producing chunks that look fine and are missing words.

### The title is stripped conditionally

Recursive extraction pulls `<title>` in along with the body, so the title would
appear twice in the chunk text. It is removed — but only with `startswith`:

```python
if section_text.startswith(section_title):
    section_text = section_text[len(section_title):].strip()
```

A blanket `str.replace` would delete every later occurrence of that phrase from
the body. "Installation Steps" appearing mid-paragraph is content, not a
duplicate heading.

### One malformed file costs one file

`parse_all_dita_files` catches `ET.ParseError` per file, logs a warning with the
filename, and continues. An indexing run over 400 topics is not worth losing to
one unclosed tag.

## Module map

| Module | Responsibility | Hides |
|---|---|---|
| `app/parser.py` | DITA XML → chunks with metadata. Pure functions, no I/O beyond reading files, no external services | ElementTree traversal, the title-strip rule, tag derivation |
| `app/indexer.py` | Embedding and ChromaDB ingestion | The OpenAI client lifecycle, batching, collection setup |
| `app/retriever.py` | Cosine search and grounded generation | Distance → score conversion, prompt assembly |
| `app/api.py` | FastAPI routes, request validation, the startup index hook | Error shaping, environment configuration |
| `app/ui.py` | Streamlit front end | HTTP calls to the API, with timeouts |

`parser.py` depends on nothing but the standard library. It is the part worth
reading and the part that is trivially testable — which is why its tests run
against the real `.dita` files rather than fixtures.

## Interfaces and contracts

**`POST /search`** → `list[SearchResult]`
- In: `{query: str (min_length 1), n_results: int (1–20, default 4)}`
- Out: `[{chunk_id, text, metadata, score}]`
- `422` on empty query or out-of-range `n_results`; `500` generic on failure

**`POST /ask`** → `AskResponse`
- Out: `{query, answer, sources: [{topic, section, score, tags}]}`
- Sources name the **topic and section**, not a page or an offset

**`POST /index`** → `{indexed: int, status: "ok"}`
- `404` if the data directory is missing or contains no `.dita` files
- A **full replace**: the collection is cleared first, so the index always
  reflects the current corpus with no orphans from deleted files

**`parse_dita_file(path) -> list[dict]`** — every chunk carries all 9 keys.
A `<topic>` with no `<body>` returns `[]`, not an error.

**`n_results` is bounded at the schema** (`ge=1, le=20`). Unvalidated, a value
of 0 or 10⁶ reaches ChromaDB and returns as an opaque 500.

## Error handling

- **Startup indexing cannot stop the service.** The lifespan hook wraps
  everything in `try/except`; a missing `OPENAI_API_KEY` is logged with a
  pointer to `/index` and the API starts anyway. A service that cannot index is
  still worth having up so the operator can see why.
- **Internal errors are logged, not returned.** `/search` and `/ask` log the
  full exception and return a generic detail. Raised `from None` so the internal
  chain cannot surface to the caller.
- **The OpenAI client is lazy.** Created on first use, never at import, raising
  a clear `RuntimeError` naming the missing variable. This is what makes
  key-less imports and a fully offline test suite possible.

## Differentiation from `hybrid-retrieval-rag-service`

Both repositories do retrieval-augmented QA. They are demonstrating different
things and the code differs accordingly.

| | `hybrid-retrieval-rag-service` | This service |
|---|---|---|
| **Problem framing** | Given a chunked corpus, get the right chunk to the top | Given a structured document, decide what a chunk *is* |
| Input | PDF, TXT, Markdown | DITA XML |
| Chunking | Heuristic split at a token budget | `<section>` boundaries as authored |
| Retrieval | Dense + BM25 in parallel → RRF (k=60) → cross-encoder rerank → top 3 | Single dense leg, cosine, top *n* |
| Vector store | Pinecone serverless | ChromaDB, local persistence |
| Embeddings | Cohere `embed-english-v3.0` (1024-dim) | OpenAI `text-embedding-3-small` |
| Generation | Anthropic `claude-sonnet-4-6` | OpenAI `gpt-4o-mini` |
| Citations | Chunk-level, with inline numbering | Topic > section, from the markup |

**The plain retrieval stack here is a decision, not an omission.** Adding fusion
and reranking would demonstrate nothing the sibling repo does not demonstrate
more thoroughly, and it would blur the claim being made: that a chunk which
respects the document's own boundaries arrives at retrieval needing less
rescuing.

The interesting comparison is what each system can say about *why* it returned
something. The hybrid service can report which leg surfaced a chunk and how
reranking moved it. This one can report the topic and section a passage was
authored under — because that was never thrown away.

## Dependencies

- **Runtime:** FastAPI, uvicorn, pydantic, chromadb, openai
- **UI only:** streamlit, requests
- **Test only:** pytest, httpx (for `fastapi.testclient`)

XML parsing uses `xml.etree.ElementTree` from the standard library — no lxml, no
DITA toolkit. See [DECISIONS.md](DECISIONS.md) and the
[XML security note](SECURITY.md#xml-parsing).
