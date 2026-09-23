"""End-to-end indexing and retriever construction.

One place that knows the whole offline path::

    load documents -> chunk -> embed -> index -> persist

and one place that knows how to get a ready-to-query retriever back::

    load index -> verify model and freshness -> Retriever

Indexing is deliberately an **offline build step**, not something that happens
on application startup. Embedding the corpus takes seconds and hundreds of
megabytes of model; doing it per process would make startup slow, make every
container replica repeat the same work, and make a document change invisible
until a restart. Building an artefact once and loading it is how the same index
gets shared by every replica in Stage 12.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.knowledge.loader import load_knowledge_base
from app.knowledge.models import KnowledgeDocument
from app.rag.chunker import chunk_documents
from app.rag.embeddings import Embedder, get_embedder
from app.rag.models import Chunk, EmbeddedChunk
from app.rag.retriever import Retriever
from app.rag.vectorstore import (
    IncompatibleIndexError,
    IndexNotFoundError,
    InMemoryVectorStore,
)

logger = get_logger(__name__)


class StaleIndexError(RuntimeError):
    """The persisted index no longer matches the documents on disk.

    Silently serving a stale index is the worst option available: answers stay
    fluent and citations still resolve, so the staleness is invisible until
    someone notices the agent quoting a procedure that was edited last week.
    """


@traced
def fingerprint_documents(documents: Sequence[KnowledgeDocument]) -> str:
    """Digest the corpus so a stale index can be detected cheaply.

    Covers the document id, its metadata and its body, so an edit to content
    *or* to metadata changes the digest. Documents are sorted first, making the
    digest independent of filesystem ordering.

    Args:
        documents: The loaded corpus.

    Returns:
        A hex SHA-256 digest.
    """
    digest = hashlib.sha256()
    for document in sorted(documents, key=lambda doc: doc.metadata.document_id):
        digest.update(document.metadata.model_dump_json().encode("utf-8"))
        digest.update(document.content.encode("utf-8"))
    return digest.hexdigest()


@traced
def embed_chunks(
    chunks: Sequence[Chunk], embedder: Embedder
) -> tuple[EmbeddedChunk, ...]:
    """Embed chunks in one batch.

    A single batched call rather than one call per chunk: batching is where
    almost all of a transformer's throughput comes from, and the difference on
    this corpus is roughly an order of magnitude.

    Args:
        chunks: Chunks to embed.
        embedder: The embedding model.

    Returns:
        Each chunk paired with its unit-length vector.
    """
    if not chunks:
        return ()

    vectors = embedder.embed_documents([chunk.embedding_text for chunk in chunks])
    return tuple(
        EmbeddedChunk(chunk=chunk, embedding=tuple(float(value) for value in vector))
        for chunk, vector in zip(chunks, vectors, strict=True)
    )


@traced
def build_index(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    persist: bool = True,
) -> Retriever:
    """Build the vector index from the knowledge base on disk.

    Args:
        settings: Application settings. Defaults to the cached singleton.
        embedder: Override the configured embedder, mainly for tests.
        persist: Whether to write the index to ``vectorstore_dir``.

    Returns:
        A retriever over the freshly built index.

    Raises:
        KnowledgeLoadError: If the corpus cannot be loaded.
        ChunkingError: If a document cannot be split to fit the model.
        EmbeddingError: If the model cannot be loaded or cannot encode.
    """
    resolved = settings or get_settings()
    model = embedder if embedder is not None else get_embedder(resolved)

    documents = load_knowledge_base(resolved.knowledge_dir)
    chunks = chunk_documents(documents, model, resolved)
    embedded = embed_chunks(chunks, model)

    store = InMemoryVectorStore(model_id=model.model_id, dimension=model.dimension)
    store.add(embedded)

    if persist:
        store.save(resolved.vectorstore_dir, fingerprint_documents(documents))

    logger.info(
        "rag.index_built",
        document_count=len(documents),
        chunk_count=len(chunks),
        model=model.model_id,
        dimension=model.dimension,
        persisted=persist,
    )
    return Retriever(model, store, resolved)


@traced
def load_retriever(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    check_freshness: bool = True,
) -> Retriever:
    """Load the persisted index and return a retriever over it.

    Args:
        settings: Application settings. Defaults to the cached singleton.
        embedder: Override the configured embedder, mainly for tests.
        check_freshness: Whether to compare the index against the documents on
            disk. Reading the corpus costs milliseconds; serving stale answers
            costs trust, so it is on by default.

    Returns:
        A retriever over the persisted index.

    Raises:
        IndexNotFoundError: If no index has been built.
        IncompatibleIndexError: If the index was built by a different model.
        StaleIndexError: If the documents have changed since the index was built.
    """
    resolved = settings or get_settings()
    model = embedder if embedder is not None else get_embedder(resolved)

    store, fingerprint = InMemoryVectorStore.load(
        resolved.vectorstore_dir,
        model_id=model.model_id,
        dimension=model.dimension,
    )

    if check_freshness:
        current = fingerprint_documents(load_knowledge_base(resolved.knowledge_dir))
        if current != fingerprint:
            raise StaleIndexError(
                f"The vector index at {resolved.vectorstore_dir} was built from a "
                "different version of the knowledge base. Rebuild it with: "
                "python -m app.rag build"
            )

    return Retriever(model, store, resolved)


@traced
def get_retriever(settings: Settings | None = None) -> Retriever:
    """Return a retriever, building the index first if it is missing or stale.

    The convenience entry point for application code. Explicit
    :func:`build_index` / :func:`load_retriever` remain available where the
    caller needs to control which of the two happens.
    """
    resolved = settings or get_settings()
    try:
        return load_retriever(resolved)
    except (IndexNotFoundError, IncompatibleIndexError, StaleIndexError) as exc:
        # Only these three are recoverable by rebuilding. A corrupt index or a
        # broken model must still fail loudly rather than be papered over.
        logger.info("rag.index_rebuilding", reason=type(exc).__name__, detail=str(exc))
        return build_index(resolved)
