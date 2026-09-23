"""Split knowledge documents into retrievable chunks.

The chunk is the unit of retrieval, so its boundaries decide what the agent can
and cannot find. Three rules, each with a measured reason behind it:

**1. Split on Markdown ``##`` headings, not on a fixed window.**
The corpus is written as short titled sections -- *Reversals*, *Timeouts*,
*The keys* -- and an author-chosen heading is a better semantic boundary than
any character count. Measured over the 15 shipped documents, the 108 sections
run 32-411 tokens with a median of 99: naturally chunk-sized, no degenerate
fragments, so no minimum-size merging is needed.

**2. Measure length in the embedding model's own tokens, never in words.**
``all-MiniLM-L6-v2`` reads at most 256 word-piece tokens and **truncates
silently** beyond that -- no exception, no warning from the encoder. The
temptation is to budget in words, but the corpus's tokens-per-word ratio runs
from 1.13 to 2.82, because identifiers like ``SWX-7001`` and
``switch.downstream_timeout_ms`` shatter into many pieces. One 146-word section
tokenises to 411. Any word- or character-based budget would therefore have
truncated the *densest* sections -- precisely the config-key and error-code
tables an engineer searches for. So the chunker asks the embedder to count.

**3. Split an oversized table row-wise, repeating its header.**
Six sections exceed the window and most are tables. A table fragment without
its header row is unreadable: ``| LIM-4001 | Daily limit | Retryable |`` means
nothing once the column names are gone. Each part therefore re-carries the
header and separator rows.

Overlap is applied only *within* a section that had to be split, never across
section boundaries: a heading is a real topic change, so bleeding text across
one adds noise to both chunks rather than recovering a straddling answer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.knowledge.models import KnowledgeDocument
from app.rag.embeddings import Embedder
from app.rag.models import Chunk

logger = get_logger(__name__)

SECTION_PATTERN = re.compile(r"^##[ \t]+(?P<heading>.+?)[ \t]*$")
H1_PATTERN = re.compile(r"^#[ \t]+.+?[ \t]*$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|[\s:|-]+\|$")
FENCE_PATTERN = re.compile(r"^(?P<fence>```|~~~)")

MIN_TABLE_LINES = 3
"""Header, separator, and at least one data row."""


class ChunkingError(RuntimeError):
    """A document could not be split into chunks that fit the embedder."""


@traced
def split_sections(body: str) -> list[tuple[str | None, str]]:
    """Split a document body into ``(heading, text)`` sections.

    The leading ``# Title`` line is dropped: it duplicates ``metadata.title``,
    which the contextual prefix already supplies. Any prose before the first
    ``##`` becomes a section with a ``None`` heading.

    Scanning is line-by-line rather than by regex over the whole body because
    fenced code blocks must be respected: the API documents contain JSON
    samples, and a ``##`` comment inside one is content, not a new section.

    Args:
        body: Markdown body of a document, front matter already removed.

    Returns:
        Sections in document order. Empty sections are omitted.
    """
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    fence: str | None = None
    seen_h1 = False

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append((heading, text))
        buffer.clear()

    for line in body.splitlines():
        opening = FENCE_PATTERN.match(line)
        if opening:
            token = opening.group("fence")
            fence = None if fence == token else (fence or token)
            buffer.append(line)
            continue

        if fence is None:
            if not seen_h1 and heading is None and H1_PATTERN.match(line):
                # The H1 duplicates metadata.title, which the contextual prefix
                # already supplies. Dropping it avoids embedding it twice.
                seen_h1 = True
                continue
            match = SECTION_PATTERN.match(line)
            if match:
                flush()
                heading = match.group("heading").strip()
                continue

        buffer.append(line)

    flush()
    return sections


@traced
def chunk_document(
    document: KnowledgeDocument,
    embedder: Embedder,
    max_tokens: int | None = None,
    overlap_tokens: int = 32,
) -> tuple[Chunk, ...]:
    """Split one document into chunks that fit the embedder's input window.

    Args:
        document: The loaded document to split.
        embedder: Supplies both the token counter and the token limit, so the
            budget can never drift from the model actually used.
        max_tokens: Override the token budget per chunk. Defaults to the
            embedder's own ``max_tokens``.
        overlap_tokens: Tokens repeated between the parts of a section that had
            to be split. Ignored for sections that fit whole.

    Returns:
        The document's chunks, in document order.

    Raises:
        ChunkingError: If the budget leaves no room for content, or if a
            section cannot be reduced to fit.
        ValueError: If ``overlap_tokens`` is negative.
    """
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must not be negative.")

    limit = max_tokens if max_tokens is not None else embedder.max_tokens
    sections = split_sections(document.content)
    if not sections:
        raise ChunkingError(
            f"{document.source_path}: document produced no chunkable sections."
        )

    chunks: list[Chunk] = []
    for heading, text in sections:
        prefix = _context_prefix(document.metadata.title, heading)
        # The contextual prefix is embedded with the content, so it spends part
        # of the same budget. Reserve it before splitting rather than after.
        budget = limit - embedder.count_tokens(f"{prefix}\n\n")
        if budget < 1:
            raise ChunkingError(
                f"{document.source_path}: the contextual prefix for section "
                f"'{heading}' alone fills the {limit}-token window."
            )

        for part in _split_to_budget(text, budget, overlap_tokens, embedder):
            token_count = embedder.count_tokens(f"{prefix}\n\n{part}")
            if token_count > limit:
                raise ChunkingError(
                    f"{document.source_path}: section '{heading}' produced a "
                    f"{token_count}-token chunk, over the {limit}-token limit."
                )
            chunks.append(
                Chunk(
                    chunk_id=f"{document.metadata.document_id}#{len(chunks)}",
                    document_id=document.metadata.document_id,
                    ordinal=len(chunks),
                    heading=heading,
                    content=part,
                    metadata=document.metadata,
                    source_path=document.source_path,
                    token_count=token_count,
                )
            )

    return tuple(chunks)


@traced
def chunk_documents(
    documents: Sequence[KnowledgeDocument],
    embedder: Embedder,
    settings: Settings | None = None,
) -> tuple[Chunk, ...]:
    """Chunk a whole corpus using the configured budget.

    Args:
        documents: Loaded knowledge documents.
        embedder: The embedder the chunks will be indexed with.
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        Every chunk of every document, in corpus order.

    Raises:
        ChunkingError: If the corpus is empty or any document cannot be split.
    """
    if not documents:
        raise ChunkingError("Cannot chunk an empty document set.")

    resolved = settings or get_settings()
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(
            chunk_document(
                document,
                embedder,
                max_tokens=resolved.chunk_max_tokens,
                overlap_tokens=resolved.chunk_overlap_tokens,
            )
        )

    token_counts = [chunk.token_count for chunk in chunks]
    logger.info(
        "rag.chunked",
        document_count=len(documents),
        chunk_count=len(chunks),
        max_chunk_tokens=max(token_counts),
        mean_chunk_tokens=round(sum(token_counts) / len(token_counts), 1),
    )
    return tuple(chunks)


def _context_prefix(title: str, heading: str | None) -> str:
    """Build the prefix that names the document and section for the embedder."""
    return title if heading is None else f"{title} — {heading}"


def _split_to_budget(
    text: str,
    budget: int,
    overlap_tokens: int,
    embedder: Embedder,
) -> list[str]:
    """Reduce ``text`` to parts that each fit within ``budget`` tokens."""
    if embedder.count_tokens(text) <= budget:
        return [text]

    parts: list[str] = []
    for block in _split_blocks(text):
        if embedder.count_tokens(block) <= budget:
            parts.append(block)
        elif _is_table(block):
            parts.extend(_split_table(block, budget, embedder))
        else:
            parts.extend(_split_lines(block, budget, overlap_tokens, embedder))

    return _pack(parts, budget, embedder)


def _split_blocks(text: str) -> list[str]:
    """Split text into blank-line-separated blocks (paragraphs, tables, lists)."""
    return [block.strip() for block in re.split(r"\n[ \t]*\n", text) if block.strip()]


def _is_table(block: str) -> bool:
    """Whether a block is a Markdown table with a header and separator row."""
    lines = block.splitlines()
    return (
        len(lines) >= MIN_TABLE_LINES
        and lines[0].lstrip().startswith("|")
        and bool(TABLE_SEPARATOR_PATTERN.match(lines[1].strip()))
    )


def _split_table(block: str, budget: int, embedder: Embedder) -> list[str]:
    """Split an oversized table row-wise, repeating the header in every part.

    A table fragment stripped of its header row loses the meaning of every
    column, so the two-line header is re-carried rather than treated as
    ordinary content.

    Raises:
        ChunkingError: If the header alone exceeds the budget.
    """
    lines = block.splitlines()
    header, rows = lines[:2], lines[2:]
    header_text = "\n".join(header)
    header_tokens = embedder.count_tokens(header_text)
    if header_tokens >= budget:
        raise ChunkingError(
            f"A table header alone is {header_tokens} tokens, at or over the "
            f"{budget}-token budget; the table cannot be split without loss."
        )

    parts: list[str] = []
    current: list[str] = []
    for row in rows:
        candidate = current + [row]
        if current and embedder.count_tokens("\n".join(header + candidate)) > budget:
            parts.append("\n".join(header + current))
            current = [row]
        else:
            current = candidate

    if current:
        parts.append("\n".join(header + current))
    return parts


def _split_lines(
    block: str,
    budget: int,
    overlap_tokens: int,
    embedder: Embedder,
) -> list[str]:
    """Split a paragraph or list line-wise, repeating a tail as overlap.

    Lines are the finest boundary that keeps a numbered step or a bullet
    intact. A single line longer than the budget is split on words as a last
    resort.
    """
    parts: list[str] = []
    current: list[str] = []

    for line in block.splitlines():
        for piece in _fit_line(line, budget, embedder):
            if current and embedder.count_tokens("\n".join([*current, piece])) > budget:
                parts.append("\n".join(current))
                current = [*_overlap_tail(current, overlap_tokens, embedder), piece]
            else:
                current.append(piece)

    if current:
        parts.append("\n".join(current))
    return parts


def _fit_line(line: str, budget: int, embedder: Embedder) -> list[str]:
    """Break a single over-long line on word boundaries so it fits the budget."""
    if embedder.count_tokens(line) <= budget:
        return [line]

    pieces: list[str] = []
    current: list[str] = []
    for word in line.split():
        if current and embedder.count_tokens(" ".join([*current, word])) > budget:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap_tail(
    lines: list[str],
    overlap_tokens: int,
    embedder: Embedder,
) -> list[str]:
    """Return the trailing lines of a part, up to ``overlap_tokens`` tokens.

    Never returns the whole part: repeating every line would make no forward
    progress and the split would not terminate.
    """
    if overlap_tokens <= 0 or len(lines) < 2:
        return []

    tail: list[str] = []
    for line in reversed(lines[1:]):
        candidate = [line, *tail]
        if embedder.count_tokens("\n".join(candidate)) > overlap_tokens:
            break
        tail = candidate
    return tail


def _pack(parts: list[str], budget: int, embedder: Embedder) -> list[str]:
    """Greedily recombine adjacent parts that fit together within the budget.

    Block-wise splitting can leave a two-line remainder next to a short
    paragraph. Packing them back together keeps chunks close to the window size
    rather than shipping avoidable fragments.
    """
    packed: list[str] = []
    for part in parts:
        if packed and embedder.count_tokens(f"{packed[-1]}\n\n{part}") <= budget:
            packed[-1] = f"{packed[-1]}\n\n{part}"
        else:
            packed.append(part)
    return packed
