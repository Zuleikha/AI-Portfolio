"""Vector storage and similarity search, behind a replaceable interface.

The application depends on the :class:`VectorStore` protocol. The shipped
implementation, :class:`InMemoryVectorStore`, holds one NumPy matrix in memory
and persists it next to a JSON sidecar.

**Why not FAISS, Chroma, pgvector or Qdrant?**
This corpus produces on the order of a hundred 384-dimension chunks. Exact
search over a ``(120, 384)`` matrix is a single BLAS matrix-vector product --
tens of microseconds, far below the cost of embedding the query, never mind an
LLM call. An approximate index (HNSW, IVF) buys sub-linear scaling by
*sacrificing recall*, and at this size there is no scaling problem to spend
recall on. A server-backed store would add a container, a network hop and an
operational dependency to a portfolio project that must run offline. Choosing
brute force here is the measured decision; the protocol is the insurance that
it can be replaced with any of the above without the retriever, agent or API
layer noticing.

**Why cosine similarity?** ``all-MiniLM-L6-v2`` is trained with a cosine
objective, so cosine is the metric the vector space was actually built for --
not merely a convenient one. Because every vector is L2-normalised at encode
time, cosine reduces to a dot product, and the whole search is one ``@``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from app.core.logging import get_logger
from app.core.tracing import traced
from app.rag.models import Chunk, EmbeddedChunk, ScoredChunk

logger = get_logger(__name__)

Vector = NDArray[np.float32]

MANIFEST_FILENAME = "manifest.json"
VECTORS_FILENAME = "vectors.npy"
CHUNKS_FILENAME = "chunks.json"

INDEX_FORMAT_VERSION = 1

FilterValue = str | Sequence[str]
Filters = Mapping[str, FilterValue]

FILTERABLE_FIELDS = frozenset(
    {"document_id", "domain", "component", "doc_type", "version"}
)


class VectorStoreError(RuntimeError):
    """Base class for vector store failures."""


class IndexNotFoundError(VectorStoreError):
    """No persisted index exists at the requested location."""


class IncompatibleIndexError(VectorStoreError):
    """The persisted index cannot be used with the current configuration.

    Raised when a stored index was built by a different embedding model or with
    a different vector width. Searching such an index would not fail -- it would
    quietly return nonsense, because the query vector and the stored vectors
    live in unrelated spaces. That failure mode is invisible in the output, so
    it is checked explicitly at load time.
    """


class UnknownFilterFieldError(VectorStoreError):
    """A filter named a metadata field that does not exist.

    Filtering on a typo would silently match nothing and look like "the
    knowledge base has no answer", so an unknown field is an error.
    """


@runtime_checkable
class VectorStore(Protocol):
    """Stores embedded chunks and ranks them against a query vector."""

    def add(self, chunks: Sequence[EmbeddedChunk]) -> None:
        """Add embedded chunks to the index."""

    def search(
        self,
        query_vector: Vector,
        k: int = 5,
        filters: Filters | None = None,
    ) -> tuple[ScoredChunk, ...]:
        """Return the ``k`` most similar chunks, best first."""

    def count(self, filters: Filters | None = None) -> int:
        """Number of indexed chunks, optionally restricted by ``filters``."""

    def clear(self) -> None:
        """Remove every chunk from the index."""

    def __len__(self) -> int:
        """Number of indexed chunks."""


class InMemoryVectorStore:
    """Exact cosine search over an in-memory NumPy matrix, persistable to disk.

    Vectors are kept as one contiguous ``(n, dimension)`` float32 matrix rather
    than a list of per-chunk arrays: scoring the whole corpus is then a single
    vectorised operation instead of ``n`` Python-level dot products.
    """

    def __init__(self, model_id: str, dimension: int) -> None:
        """Create an empty store bound to one embedding model.

        Args:
            model_id: Identifier of the embedder whose vectors this store holds.
            dimension: Expected width of every vector added.

        Raises:
            ValueError: If ``dimension`` is not positive.
        """
        if dimension < 1:
            raise ValueError("dimension must be positive.")
        self._model_id = model_id
        self._dimension = dimension
        self._chunks: list[Chunk] = []
        self._matrix: NDArray[np.float32] = np.zeros((0, dimension), dtype=np.float32)

    @property
    def model_id(self) -> str:
        """Embedding model this index was built with."""
        return self._model_id

    @property
    def dimension(self) -> int:
        """Width of the stored vectors."""
        return self._dimension

    def __len__(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunks)

    @traced
    def add(self, chunks: Sequence[EmbeddedChunk]) -> None:
        """Add embedded chunks to the index.

        Args:
            chunks: Chunks with their vectors. May be empty.

        Raises:
            VectorStoreError: If any vector has the wrong width, or a
                ``chunk_id`` already present in the index is added again --
                duplicates would let one passage outvote the rest of the corpus.
        """
        if not chunks:
            return

        existing = {chunk.chunk_id for chunk in self._chunks}
        for embedded in chunks:
            if len(embedded.embedding) != self._dimension:
                raise VectorStoreError(
                    f"Chunk '{embedded.chunk.chunk_id}' has a "
                    f"{len(embedded.embedding)}-dimension vector; this index "
                    f"expects {self._dimension}."
                )
            if embedded.chunk.chunk_id in existing:
                raise VectorStoreError(
                    f"Chunk '{embedded.chunk.chunk_id}' is already indexed."
                )
            existing.add(embedded.chunk.chunk_id)

        additions = np.asarray(
            [embedded.embedding for embedded in chunks], dtype=np.float32
        )
        self._matrix = np.vstack([self._matrix, additions])
        self._chunks.extend(embedded.chunk for embedded in chunks)

    @traced
    def search(
        self,
        query_vector: Vector,
        k: int = 5,
        filters: Filters | None = None,
    ) -> tuple[ScoredChunk, ...]:
        """Return the ``k`` chunks most similar to ``query_vector``.

        Filters are applied **before** scoring, not after. Post-filtering a
        top-k list is the classic retrieval bug: ask for the best 5 chunks and
        then keep only the ``payments`` ones and you can easily be left with
        zero, even though the corpus holds plenty of relevant payments
        material. Pre-filtering always returns the best ``k`` *of the
        permitted set*.

        Args:
            query_vector: Unit-length query embedding.
            k: Maximum number of results.
            filters: Optional metadata equality filters, e.g.
                ``{"domain": ["payments", "cards"]}``.

        Returns:
            Scored chunks, highest cosine similarity first. Fewer than ``k``
            if the filtered index holds fewer.

        Raises:
            ValueError: If ``k`` is not positive or the vector has the wrong width.
            UnknownFilterFieldError: If a filter names an unknown field.
        """
        if k < 1:
            raise ValueError("k must be positive.")
        if query_vector.shape != (self._dimension,):
            raise ValueError(
                f"Query vector has shape {query_vector.shape}; this index "
                f"expects ({self._dimension},)."
            )
        if not self._chunks:
            return ()

        indices = self._matching_indices(filters)
        if indices.size == 0:
            return ()

        # Every vector is L2-normalised, so the dot product is the cosine.
        scores = self._matrix[indices] @ query_vector.astype(np.float32)

        top = min(k, scores.size)
        # argpartition is O(n) and avoids sorting the whole corpus to take 5.
        partitioned = np.argpartition(-scores, top - 1)[:top]
        ordered = partitioned[np.argsort(-scores[partitioned], kind="stable")]

        return tuple(
            ScoredChunk(
                chunk=self._chunks[int(indices[position])],
                # Clamp: normalised dot products can land a hair outside
                # [-1, 1] through float32 rounding, which the model rejects.
                score=float(np.clip(scores[position], -1.0, 1.0)),
            )
            for position in ordered
        )

    @traced
    def count(self, filters: Filters | None = None) -> int:
        """Number of indexed chunks matching ``filters`` (all of them if none)."""
        if filters is None:
            return len(self._chunks)
        return int(self._matching_indices(filters).size)

    def clear(self) -> None:
        """Remove every chunk from the index."""
        self._chunks.clear()
        self._matrix = np.zeros((0, self._dimension), dtype=np.float32)

    @traced
    def save(self, directory: Path, corpus_fingerprint: str) -> None:
        """Persist the index to ``directory``.

        Three files: the vectors as ``.npy`` (compact and fast to memory-map),
        the chunks as JSON (diffable and inspectable by a human), and a manifest
        recording which model built the index.

        Args:
            directory: Destination directory; created if absent.
            corpus_fingerprint: Digest of the source documents, so a stale index
                can be detected without re-reading the whole corpus.
        """
        directory.mkdir(parents=True, exist_ok=True)

        np.save(directory / VECTORS_FILENAME, self._matrix)
        (directory / CHUNKS_FILENAME).write_text(
            json.dumps(
                [chunk.model_dump(mode="json") for chunk in self._chunks],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (directory / MANIFEST_FILENAME).write_text(
            json.dumps(
                {
                    "format_version": INDEX_FORMAT_VERSION,
                    "model_id": self._model_id,
                    "dimension": self._dimension,
                    "chunk_count": len(self._chunks),
                    "corpus_fingerprint": corpus_fingerprint,
                    "built_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(
            "rag.index_saved",
            directory=directory.as_posix(),
            chunk_count=len(self._chunks),
            model=self._model_id,
        )

    @classmethod
    @traced
    def load(
        cls,
        directory: Path,
        model_id: str,
        dimension: int,
    ) -> tuple[InMemoryVectorStore, str]:
        """Load a persisted index, refusing one built by a different model.

        Args:
            directory: Directory previously passed to :meth:`save`.
            model_id: Embedding model the caller intends to query with.
            dimension: Vector width the caller expects.

        Returns:
            The loaded store and the corpus fingerprint recorded at build time.

        Raises:
            IndexNotFoundError: If the directory or any expected file is absent.
            IncompatibleIndexError: If the index was built by a different model,
                with a different vector width, or in an older on-disk format.
            VectorStoreError: If the stored files disagree with each other.
        """
        manifest_path = directory / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise IndexNotFoundError(
                f"No vector index at {directory}. Build one with: "
                "python -m app.rag build"
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if manifest.get("format_version") != INDEX_FORMAT_VERSION:
            raise IncompatibleIndexError(
                f"Index at {directory} uses format version "
                f"{manifest.get('format_version')}; this build expects "
                f"{INDEX_FORMAT_VERSION}. Rebuild it."
            )
        if manifest.get("model_id") != model_id:
            raise IncompatibleIndexError(
                f"Index at {directory} was built with '{manifest.get('model_id')}' "
                f"but the application is configured for '{model_id}'. Vectors from "
                "different models are not comparable -- searching would return "
                "plausible-looking nonsense. Rebuild the index."
            )
        if manifest.get("dimension") != dimension:
            raise IncompatibleIndexError(
                f"Index at {directory} holds {manifest.get('dimension')}-dimension "
                f"vectors but the embedder produces {dimension}. Rebuild the index."
            )

        vectors_path = directory / VECTORS_FILENAME
        chunks_path = directory / CHUNKS_FILENAME
        for path in (vectors_path, chunks_path):
            if not path.is_file():
                raise IndexNotFoundError(
                    f"Index at {directory} is missing {path.name}."
                )

        matrix = np.load(vectors_path).astype(np.float32)
        chunks = [
            Chunk.model_validate(item)
            for item in json.loads(chunks_path.read_text(encoding="utf-8"))
        ]

        if matrix.shape[0] != len(chunks):
            raise VectorStoreError(
                f"Index at {directory} is inconsistent: {matrix.shape[0]} vectors "
                f"but {len(chunks)} chunks."
            )

        store = cls(model_id=model_id, dimension=dimension)
        store._chunks = chunks
        store._matrix = matrix

        logger.info(
            "rag.index_loaded",
            directory=directory.as_posix(),
            chunk_count=len(chunks),
            model=model_id,
        )
        return store, str(manifest.get("corpus_fingerprint", ""))

    def _matching_indices(self, filters: Filters | None) -> NDArray[np.intp]:
        """Row indices of the chunks satisfying every filter."""
        if not filters:
            return np.arange(len(self._chunks), dtype=np.intp)

        unknown = set(filters) - FILTERABLE_FIELDS
        if unknown:
            raise UnknownFilterFieldError(
                f"Unknown filter field(s): {sorted(unknown)}. "
                f"Filterable fields are {sorted(FILTERABLE_FIELDS)}."
            )

        allowed = {
            field: {value} if isinstance(value, str) else set(value)
            for field, value in filters.items()
        }

        return np.array(
            [
                index
                for index, chunk in enumerate(self._chunks)
                if all(
                    _field_value(chunk, field) in values
                    for field, values in allowed.items()
                )
            ],
            dtype=np.intp,
        )


def _field_value(chunk: Chunk, field: str) -> str:
    """Read a filterable metadata field off a chunk."""
    if field == "document_id":
        return chunk.document_id
    return str(getattr(chunk.metadata, field))
