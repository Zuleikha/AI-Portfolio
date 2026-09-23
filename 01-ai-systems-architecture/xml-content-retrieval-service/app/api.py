"""
api.py
FastAPI application for the DITA RAG pipeline.
Endpoints: index, search, ask
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.dispatch import parse_all_files
from app.indexer import collection_count, index_chunks
from app.retriever import generate_answer, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "./data")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_store")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-index on startup only when the store is empty — a restart should not
    # re-spend OpenAI embedding tokens on an unchanged corpus. POST /index forces a rebuild.
    # A failure here (e.g. missing OPENAI_API_KEY) must not prevent the API from starting.
    try:
        if Path(DATA_DIR).exists():
            existing = collection_count(persist_dir=CHROMA_DIR)
            if existing > 0:
                logger.info("Skipping startup indexing — %d documents already indexed", existing)
            else:
                logger.info("Auto-indexing DITA files on startup...")
                chunks = parse_all_files(DATA_DIR)
                if chunks:
                    index_chunks(chunks, persist_dir=CHROMA_DIR)
    except Exception:
        logger.exception("Startup indexing failed — API starting anyway; fix and POST /index")
    yield


app = FastAPI(
    title="DITA RAG Pipeline",
    description="Semantic search and Q&A over DITA XML documentation",
    version="1.0.0",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    n_results: int = Field(default=4, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    metadata: dict
    score: float


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/index")
def reindex():
    """Re-parse and re-index all DITA files."""
    if not Path(DATA_DIR).exists():
        raise HTTPException(status_code=404, detail=f"Data directory not found: {DATA_DIR}")
    chunks = parse_all_files(DATA_DIR)
    if not chunks:
        raise HTTPException(status_code=404, detail="No DITA files found in data directory")
    count = index_chunks(chunks, persist_dir=CHROMA_DIR)
    return {"indexed": count, "status": "ok"}


@app.post("/search", response_model=list[SearchResult])
def semantic_search(request: QueryRequest):
    """Return top matching chunks for a query."""
    try:
        return search(request.query, n_results=request.n_results, persist_dir=CHROMA_DIR)
    except Exception:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail="Search failed — see server logs") from None


@app.post("/ask", response_model=AskResponse)
def ask(request: QueryRequest):
    """Retrieve relevant chunks and generate an answer."""
    try:
        chunks = search(request.query, n_results=request.n_results, persist_dir=CHROMA_DIR)
        answer = generate_answer(request.query, chunks)
        sources = [
            {
                "topic": c["metadata"]["topic_title"],
                "section": c["metadata"]["section_title"],
                "score": c["score"],
                "tags": c["metadata"]["tags"],
            }
            for c in chunks
        ]
        return AskResponse(query=request.query, answer=answer, sources=sources)
    except Exception:
        logger.exception("Ask failed")
        raise HTTPException(
            status_code=500, detail="Answer generation failed — see server logs"
        ) from None
