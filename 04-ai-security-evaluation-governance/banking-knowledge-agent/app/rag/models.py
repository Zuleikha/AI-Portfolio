"""Data contracts for the RAG pipeline.

Four types, one per stage of the pipeline::

    KnowledgeDocument  --chunker-->  Chunk
    Chunk              --embedder--> EmbeddedChunk
    EmbeddedChunk      --store----->  (indexed)
    query              --retriever-> ScoredChunk / RetrievalResult

Every type carries the full :class:`~app.knowledge.models.DocumentMetadata` of
the document it came from. Metadata is not decoration: it is what lets an answer
say *"per ATM Transaction Lifecycle (TransactionSwitch v4.2)"* instead of
*"somewhere in the docs"*, and it is what makes filtered retrieval possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.models import DocumentMetadata

CONTEXT_SEPARATOR = " — "
"""Joins the title and heading in a chunk's contextual prefix."""


class Chunk(BaseModel):
    """A retrievable passage of a single knowledge document.

    ``content`` is the passage exactly as it appears in the source document.
    ``embedding_text`` is what actually gets embedded: the same content with a
    short contextual prefix naming the document and the section it came from.

    The two are separate on purpose. Read in isolation, a passage such as
    *"Reversals are retried up to ``switch.reversal_retry_count`` times"* never
    names ATMs or TransactionSwitch, so a question phrased in those terms would
    not match it. Prepending ``"ATM Transaction Lifecycle - Reversals"`` puts
    the entity names back into the vector without polluting the text a human
    (or, from Stage 5, the LLM) is shown.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(
        min_length=1,
        description="Stable id: '<document_id>#<ordinal>'. Reproducible across builds.",
    )
    document_id: str = Field(min_length=1, description="Owning document's id.")
    ordinal: int = Field(
        ge=0,
        description="Zero-based position of this chunk within its document.",
    )
    heading: str | None = Field(
        default=None,
        description="The '## ' section heading this chunk came from, if any.",
    )
    content: str = Field(
        min_length=1, description="Passage text as written in the source."
    )
    metadata: DocumentMetadata = Field(
        description="Full metadata of the source document."
    )
    source_path: str = Field(
        min_length=1,
        description="POSIX path of the source document, from the knowledge root.",
    )
    token_count: int = Field(
        ge=1,
        description="Tokens in 'embedding_text', per the embedder's tokenizer.",
    )

    @property
    def embedding_text(self) -> str:
        """The text handed to the embedding model: contextual prefix + content."""
        return f"{self.context_prefix}\n\n{self.content}"

    @property
    def context_prefix(self) -> str:
        """Document title, plus the section heading when the chunk has one."""
        if self.heading is None:
            return self.metadata.title
        return f"{self.metadata.title}{CONTEXT_SEPARATOR}{self.heading}"

    @property
    def citation(self) -> str:
        """Human-readable source reference, e.g. for display next to an answer."""
        location = self.context_prefix
        return f"{location} ({self.source_path})"


class EmbeddedChunk(BaseModel):
    """A chunk paired with its unit-length embedding vector.

    The vector is a plain ``tuple[float, ...]`` rather than a NumPy array so the
    model stays hashable, frozen, JSON-serialisable and free of a NumPy
    dependency in its public contract. The vector store converts to a NumPy
    matrix once, at index time, where the cost is paid a single time.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    embedding: tuple[float, ...] = Field(
        min_length=1,
        description="Unit-length (L2-normalised) embedding of 'chunk.embedding_text'.",
    )


class ScoredChunk(BaseModel):
    """A chunk returned by a similarity search, with its score.

    ``score`` is cosine similarity in ``[-1, 1]``; in practice sentence-embedding
    scores for related text sit in ``[0.2, 0.9]``. It is a *relative* ranking
    signal, not a calibrated probability -- see ``retriever.py`` for how the
    minimum-score threshold was chosen.
    """

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float = Field(ge=-1.0, le=1.0, description="Cosine similarity to the query.")


class RetrievalResult(BaseModel):
    """Everything one retrieval call produced, ready to hand to an agent.

    Carries the outcome *and* the reason for it. ``chunks`` being empty is a
    legitimate, expected result -- it is the signal Stage 5 turns into an
    explicit "I don't have that documented" rather than a fabricated answer --
    so the object records how many candidates were considered and what
    threshold rejected them.
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, description="The question that was searched for.")
    chunks: tuple[ScoredChunk, ...] = Field(
        default=(),
        description="Matches, best first. Empty when nothing cleared the floor.",
    )
    candidates_considered: int = Field(
        ge=0,
        description="Chunks the store scored before the threshold was applied.",
    )
    min_score: float = Field(
        description="Threshold a chunk had to clear to be returned."
    )

    @property
    def is_empty(self) -> bool:
        """Whether retrieval found no sufficiently similar evidence."""
        return not self.chunks

    @property
    def top_score(self) -> float | None:
        """Score of the best match, or ``None`` when there were no matches."""
        return self.chunks[0].score if self.chunks else None

    @property
    def sources(self) -> tuple[str, ...]:
        """Distinct document citations behind this result, best-match order.

        Deduplicated by document: several chunks of one document are one source
        to a reader, and a citation list that repeats the same document five
        times looks like five pieces of evidence when it is one.
        """
        seen: dict[str, None] = {}
        for scored in self.chunks:
            document = scored.chunk
            seen.setdefault(
                f"{document.metadata.title} "
                f"({document.metadata.component} v{document.metadata.version}) "
                f"[{document.source_path}]",
                None,
            )
        return tuple(seen)
