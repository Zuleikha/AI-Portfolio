"""Load synthetic banking knowledge documents from disk.

Documents are Markdown files carrying a YAML front-matter block::

    ---
    document_id: atm-transaction-lifecycle
    title: ATM Transaction Lifecycle
    domain: atm
    component: TransactionSwitch
    version: "4.2"
    doc_type: reference
    ---

    # ATM Transaction Lifecycle
    ...

Markdown + front matter is used rather than JSON or a database because the body
is exactly the text that gets chunked and embedded in Stage 3, it stays readable
and reviewable in a diff, and the metadata travels with the content it describes.

The loader is deliberately strict. A document that is malformed, mislabelled or
empty raises rather than being skipped: a silently dropped document becomes an
answer the agent cannot ground, which is far harder to diagnose later than a
failed load.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.knowledge.models import DocumentMetadata, KnowledgeDocument

logger = get_logger(__name__)

FRONT_MATTER_DELIMITER = "---"
DOCUMENT_SUFFIX = ".md"


class KnowledgeLoadError(RuntimeError):
    """Base class for every failure raised while loading knowledge documents."""


class FrontMatterError(KnowledgeLoadError):
    """The document has no well-formed YAML front-matter block."""


class MetadataError(KnowledgeLoadError):
    """The front matter does not satisfy the document metadata schema."""


class EmptyDocumentError(KnowledgeLoadError):
    """The document has a valid header but no body text to index."""


class KnowledgeBaseNotFoundError(KnowledgeLoadError):
    """The configured knowledge directory does not exist or holds no documents."""


class DuplicateDocumentIdError(KnowledgeLoadError):
    """Two documents claim the same ``document_id``, so citations are ambiguous."""


@traced
def split_front_matter(raw: str, source: str) -> tuple[str, str]:
    """Split raw file text into its front-matter block and its body.

    Args:
        raw: Full text of the document file.
        source: Path shown in error messages.

    Returns:
        A ``(front_matter, body)`` pair, both unparsed strings.

    Raises:
        FrontMatterError: If the opening or closing delimiter is missing.
    """
    lines = raw.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise FrontMatterError(
            f"{source}: expected a '{FRONT_MATTER_DELIMITER}' front-matter block "
            "on the first line."
        )

    for index in range(1, len(lines)):
        if lines[index].strip() == FRONT_MATTER_DELIMITER:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])

    raise FrontMatterError(
        f"{source}: front-matter block is never closed with "
        f"'{FRONT_MATTER_DELIMITER}'."
    )


@traced
def parse_metadata(front_matter: str, source: str) -> DocumentMetadata:
    """Parse and validate a front-matter block into typed metadata.

    Args:
        front_matter: The raw YAML text between the delimiters.
        source: Path shown in error messages.

    Returns:
        The validated metadata.

    Raises:
        FrontMatterError: If the block is not valid YAML or is not a mapping.
        MetadataError: If the mapping does not satisfy the metadata schema.
    """
    try:
        # safe_load, never load: front matter must not be able to construct
        # arbitrary Python objects.
        parsed = yaml.safe_load(front_matter)
    except yaml.YAMLError as exc:
        raise FrontMatterError(
            f"{source}: front matter is not valid YAML: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise FrontMatterError(
            f"{source}: front matter must be a mapping of fields, got "
            f"{type(parsed).__name__}."
        )

    try:
        return DocumentMetadata.model_validate(parsed)
    except ValidationError as exc:
        raise MetadataError(f"{source}: invalid document metadata: {exc}") from exc


@traced
def load_document(path: Path, root: Path) -> KnowledgeDocument:
    """Load a single knowledge document from ``path``.

    Args:
        path: The Markdown file to read.
        root: Knowledge base root, used to build the relative citation path.

    Returns:
        The validated document.

    Raises:
        FrontMatterError: If the front matter is missing or malformed.
        MetadataError: If metadata is invalid or contradicts the filename.
        EmptyDocumentError: If the document has no body text.
    """
    source = _relative_posix(path, root)
    raw = path.read_text(encoding="utf-8")

    front_matter, body = split_front_matter(raw, source)
    metadata = parse_metadata(front_matter, source)

    if metadata.document_id != path.stem:
        raise MetadataError(
            f"{source}: document_id '{metadata.document_id}' does not match the "
            f"filename stem '{path.stem}'. Citations are addressed by id, so the "
            "two must agree."
        )

    content = body.strip()
    if not content:
        raise EmptyDocumentError(f"{source}: document has no body content to index.")

    return KnowledgeDocument(
        metadata=metadata,
        content=content,
        source_path=source,
    )


@traced
def load_knowledge_base(root: Path | None = None) -> tuple[KnowledgeDocument, ...]:
    """Load every knowledge document beneath ``root``.

    Args:
        root: Knowledge base directory. Defaults to the configured
            ``knowledge_dir`` setting.

    Returns:
        All documents, ordered deterministically by source path so that indexing
        runs and test assertions are reproducible.

    Raises:
        KnowledgeBaseNotFoundError: If the directory is missing or has no
            documents. An empty knowledge base is treated as a failure because
            it would otherwise surface as an agent that silently answers
            nothing.
        KnowledgeLoadError: If any individual document fails to load.
    """
    root = (root or get_settings().knowledge_dir).resolve()

    if not root.is_dir():
        raise KnowledgeBaseNotFoundError(f"Knowledge directory does not exist: {root}")

    paths = sorted(root.rglob(f"*{DOCUMENT_SUFFIX}"))
    if not paths:
        raise KnowledgeBaseNotFoundError(
            f"No '{DOCUMENT_SUFFIX}' documents found under: {root}"
        )

    documents = tuple(load_document(path, root) for path in paths)
    _reject_duplicate_ids(documents)

    logger.info(
        "knowledge.loaded",
        document_count=len(documents),
        domains=sorted({doc.metadata.domain for doc in documents}),
        root=str(root),
    )
    return documents


@traced
def _reject_duplicate_ids(documents: tuple[KnowledgeDocument, ...]) -> None:
    """Fail if any ``document_id`` appears more than once.

    Raises:
        DuplicateDocumentIdError: If ids collide, which would make a citation
            point at two different documents.
    """
    seen: dict[str, str] = {}
    for document in documents:
        document_id = document.metadata.document_id
        first = seen.get(document_id)
        if first is not None:
            raise DuplicateDocumentIdError(
                f"Duplicate document_id '{document_id}' in '{first}' and "
                f"'{document.source_path}'."
            )
        seen[document_id] = document.source_path


@traced
def _relative_posix(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as a POSIX-style string.

    Citations must read identically on Windows and inside a Linux container, so
    the separator is normalised once here rather than at every display site.
    """
    return path.resolve().relative_to(root.resolve()).as_posix()
