"""Retrieval-Augmented Generation pipeline.

Stage 3 owns everything between a loaded document and a ranked, cited passage::

    KnowledgeDocument            (Stage 2)
        |
        v  chunker      heading-aware, budgeted in the model's own tokens
      Chunk
        |
        v  embeddings   Embedder protocol -> unit-length vectors
      EmbeddedChunk
        |
        v  vectorstore  VectorStore protocol -> exact cosine search
      (indexed)
        |
    Question
        |
        v  retriever    embed -> search -> threshold
      RetrievalResult   scored chunks + deduplicated sources

Every stage of that path is behind a protocol or a pure function, so the
embedding model and the vector store can each be replaced without touching the
agent (Stage 5) or the API. No LLM is involved: retrieval is measurable on its
own, which is what makes "is the answer wrong, or was the evidence wrong?"
a question with an answer.
"""

from __future__ import annotations

from app.rag.chunker import (
    ChunkingError,
    chunk_document,
    chunk_documents,
    split_sections,
)
from app.rag.embeddings import (
    Embedder,
    EmbeddingError,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)
from app.rag.models import Chunk, EmbeddedChunk, RetrievalResult, ScoredChunk
from app.rag.pipeline import (
    StaleIndexError,
    build_index,
    embed_chunks,
    fingerprint_documents,
    get_retriever,
    load_retriever,
)
from app.rag.retriever import Retriever
from app.rag.vectorstore import (
    IncompatibleIndexError,
    IndexNotFoundError,
    InMemoryVectorStore,
    UnknownFilterFieldError,
    VectorStore,
    VectorStoreError,
)

__all__ = [
    "Chunk",
    "ChunkingError",
    "EmbeddedChunk",
    "Embedder",
    "EmbeddingError",
    "HashingEmbedder",
    "InMemoryVectorStore",
    "IncompatibleIndexError",
    "IndexNotFoundError",
    "RetrievalResult",
    "Retriever",
    "ScoredChunk",
    "SentenceTransformerEmbedder",
    "StaleIndexError",
    "UnknownFilterFieldError",
    "VectorStore",
    "VectorStoreError",
    "build_index",
    "chunk_document",
    "chunk_documents",
    "embed_chunks",
    "fingerprint_documents",
    "get_embedder",
    "get_retriever",
    "load_retriever",
    "split_sections",
]
