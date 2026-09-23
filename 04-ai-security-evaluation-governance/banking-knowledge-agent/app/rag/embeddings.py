"""Embedding generation, behind a replaceable interface.

The application depends on the :class:`Embedder` protocol, never on a concrete
model. Two implementations ship:

``SentenceTransformerEmbedder``
    The default. Runs ``all-MiniLM-L6-v2`` locally: real semantic embeddings,
    no API key, no per-query cost, no network call after the first download.

``HashingEmbedder``
    A deterministic, dependency-light embedder used by the fast test suite. It
    is *not* semantic -- it hashes token n-grams into a fixed-width vector -- but
    it satisfies the same protocol, which is exactly the point: if the pipeline
    works with it, the pipeline is genuinely decoupled from the model.

Both return **L2-normalised** vectors, so cosine similarity is a plain dot
product and the vector store never needs to know which embedder produced its
index.

Queries and documents are embedded through separate methods even though
MiniLM treats them identically. Asymmetric models (E5, BGE, and most hosted
retrieval models) require distinct ``query:`` / ``passage:`` prefixes, and
retrofitting that distinction later would mean re-indexing.
"""

from __future__ import annotations

import hashlib
import re
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.tracing import traced

if TYPE_CHECKING:  # pragma: no cover - import cost is deliberately deferred
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

Vector = NDArray[np.float32]
Matrix = NDArray[np.float32]

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

HASHING_EMBEDDER_ID = "hashing"
"""Set ``BKA_EMBEDDING_MODEL=hashing`` to run the pipeline with no model download."""


class EmbeddingError(RuntimeError):
    """The embedding model could not be loaded or could not encode the input."""


@runtime_checkable
class Embedder(Protocol):
    """Turns text into unit-length vectors.

    Implementations must guarantee:

    * ``embed_documents`` and ``embed_query`` produce vectors of ``dimension``.
    * Every returned vector is L2-normalised.
    * ``count_tokens`` reports length in the *same* units as ``max_tokens``,
      because the chunker uses the pair to guarantee no chunk is truncated.
    """

    @property
    def model_id(self) -> str:
        """Identifier of the underlying model, recorded in the index."""

    @property
    def dimension(self) -> int:
        """Length of the vectors this embedder produces."""

    @property
    def max_tokens(self) -> int:
        """Longest input the model reads. Anything beyond this is truncated."""

    def count_tokens(self, text: str) -> int:
        """Length of ``text`` in the model's own tokens."""

    def embed_documents(self, texts: list[str]) -> Matrix:
        """Embed passages for indexing. Returns an ``(n, dimension)`` matrix."""

    def embed_query(self, text: str) -> Vector:
        """Embed a single search query. Returns a ``(dimension,)`` vector."""


class SentenceTransformerEmbedder:
    """Local sentence-transformers embedder. The production default.

    The model is loaded lazily and only once. Loading costs several seconds and
    a few hundred megabytes of resident memory, so constructing this class must
    not pay that price -- importing a module or building the FastAPI app should
    stay cheap. The lock makes the lazy load safe when two requests race.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Configure the embedder without loading the model.

        Args:
            settings: Application settings. Defaults to the cached singleton.
        """
        resolved = settings or get_settings()
        self._model_id = resolved.embedding_model
        self._device = resolved.embedding_device
        self._batch_size = resolved.embedding_batch_size
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        """Hugging Face id of the loaded model."""
        return self._model_id

    @property
    def dimension(self) -> int:
        """Embedding width reported by the model itself, never hardcoded.

        Hardcoding 384 would be correct today and silently wrong the moment the
        configured model changes -- and a dimension mismatch surfaces as bad
        search results, not as an exception.

        Raises:
            EmbeddingError: If the model does not report a dimension. The whole
                pipeline is sized from this number, so guessing a default would
                push the failure downstream into the vector store.
        """
        dimension = self._loaded().get_embedding_dimension()
        if dimension is None:
            raise EmbeddingError(
                f"Model '{self._model_id}' does not report an embedding dimension."
            )
        return int(dimension)

    @property
    def max_tokens(self) -> int:
        """The model's input window. Longer input is silently truncated.

        This is the number the chunker is built around: ``all-MiniLM-L6-v2``
        stops at 256 word-piece tokens and gives no error when it truncates.

        Raises:
            EmbeddingError: If the model does not declare a sequence limit.
                Without it the chunker cannot guarantee chunks fit, and a
                truncated chunk fails silently rather than loudly.
        """
        limit = self._loaded().max_seq_length
        if limit is None:
            raise EmbeddingError(
                f"Model '{self._model_id}' does not declare a max sequence length, "
                "so chunks cannot be sized safely."
            )
        return int(limit)

    @traced
    def count_tokens(self, text: str) -> int:
        """Count word-piece tokens in ``text`` using the model's own tokenizer.

        Special tokens are excluded so the count is comparable against
        ``max_seq_length``, which already accounts for them.
        """
        tokenizer = self._loaded().tokenizer
        # verbose=False: the chunker calls this *on purpose* with text longer
        # than the window, to decide where to split it. Without this the
        # tokenizer warns "sequence longer than maximum" on exactly the inputs
        # the chunker exists to fix, which reads like a bug and is not one.
        return len(tokenizer.encode(text, add_special_tokens=False, verbose=False))

    @traced
    def embed_documents(self, texts: list[str]) -> Matrix:
        """Embed passages for indexing.

        Args:
            texts: Passages to embed. May be empty.

        Returns:
            An ``(len(texts), dimension)`` float32 matrix of unit vectors.

        Raises:
            EmbeddingError: If the model fails to encode the batch.
        """
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return self._encode(texts)

    @traced
    def embed_query(self, text: str) -> Vector:
        """Embed one search query.

        Args:
            text: The question to embed.

        Returns:
            A ``(dimension,)`` float32 unit vector.

        Raises:
            EmbeddingError: If the text is blank or the model fails to encode it.
        """
        if not text.strip():
            raise EmbeddingError("Cannot embed an empty query.")
        vector: Vector = self._encode([text])[0]
        return vector

    def _encode(self, texts: list[str]) -> Matrix:
        """Run the model, normalising output and translating failures."""
        model = self._loaded()
        try:
            vectors = model.encode(
                texts,
                batch_size=self._batch_size,
                # Normalise inside the model: cosine similarity then reduces to
                # a dot product everywhere downstream.
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
            raise EmbeddingError(
                f"Model '{self._model_id}' failed to encode {len(texts)} text(s): {exc}"
            ) from exc
        matrix: Matrix = np.asarray(vectors, dtype=np.float32)
        return matrix

    def _loaded(self) -> SentenceTransformer:
        """Return the model, loading it on first use.

        Raises:
            EmbeddingError: If the model cannot be loaded -- typically a first
                run with no network access and nothing in the local cache.
        """
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:  # pragma: no cover - lost race
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - dependency missing
                raise EmbeddingError(
                    "sentence-transformers is not installed. Run: "
                    "pip install -r requirements.txt"
                ) from exc

            logger.info("embedding.model_loading", model=self._model_id)
            try:
                model: SentenceTransformer = SentenceTransformer(
                    self._model_id, device=self._device
                )
            except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
                raise EmbeddingError(
                    f"Could not load embedding model '{self._model_id}'. The first "
                    "run downloads it from Hugging Face and needs network access; "
                    f"later runs use the local cache. Cause: {exc}"
                ) from exc

            self._model = model
            logger.info(
                "embedding.model_loaded",
                model=self._model_id,
                dimension=model.get_embedding_dimension(),
                max_seq_length=model.max_seq_length,
            )
            return model


class HashingEmbedder:
    """Deterministic hashing embedder for fast, offline, reproducible tests.

    Text is lower-cased, split into word tokens, and each unigram and bigram is
    hashed to a column of a fixed-width vector, which is then L2-normalised --
    the classic "hashing trick". Shared vocabulary produces a high score and
    disjoint vocabulary produces a low one, which is enough to exercise
    chunking, indexing, ranking, filtering and thresholding.

    It is deliberately *not* semantic. It exists so the pipeline's tests do not
    depend on a 90 MB model download, a warm cache, or floating-point behaviour
    that varies across machines. Retrieval *quality* is asserted separately,
    against the real model.
    """

    def __init__(self, dimension: int = 256, max_tokens: int = 256) -> None:
        """Create a hashing embedder.

        Args:
            dimension: Width of the produced vectors.
            max_tokens: Reported input limit, mirroring a real model's window.

        Raises:
            ValueError: If either argument is not positive.
        """
        if dimension < 1 or max_tokens < 1:
            raise ValueError("dimension and max_tokens must both be positive.")
        self._dimension = dimension
        self._max_tokens = max_tokens

    @property
    def model_id(self) -> str:
        """Pseudo model id, so an index built with it is identifiable."""
        return f"hashing-{self._dimension}"

    @property
    def dimension(self) -> int:
        """Width of the produced vectors."""
        return self._dimension

    @property
    def max_tokens(self) -> int:
        """Reported input limit."""
        return self._max_tokens

    def count_tokens(self, text: str) -> int:
        """Count word tokens. Whitespace-delimited, matching the hashing split."""
        return len(text.split())

    def embed_documents(self, texts: list[str]) -> Matrix:
        """Embed passages. Returns an ``(len(texts), dimension)`` matrix."""
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)
        return np.vstack([self._hash(text) for text in texts])

    def embed_query(self, text: str) -> Vector:
        """Embed one query.

        Raises:
            EmbeddingError: If the text is blank.
        """
        if not text.strip():
            raise EmbeddingError("Cannot embed an empty query.")
        return self._hash(text)

    def _hash(self, text: str) -> Vector:
        """Hash unigrams and bigrams into a normalised vector."""
        tokens = _TOKEN_PATTERN.findall(text.lower())
        grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]

        vector = np.zeros(self._dimension, dtype=np.float32)
        for gram in grams:
            # blake2b, not Python's hash(): PYTHONHASHSEED randomises str hashing
            # per process, which would make an index unreadable by the next run.
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % self._dimension] += 1.0

        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return vector
        return vector / norm


@traced
def get_embedder(settings: Settings | None = None) -> Embedder:
    """Build the configured embedder.

    The single place the application decides which implementation to use, so
    swapping models is a configuration change rather than a code change.

    Args:
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        An :class:`Embedder`.
    """
    resolved = settings or get_settings()
    if resolved.embedding_model == HASHING_EMBEDDER_ID:
        return HashingEmbedder()
    return SentenceTransformerEmbedder(resolved)
