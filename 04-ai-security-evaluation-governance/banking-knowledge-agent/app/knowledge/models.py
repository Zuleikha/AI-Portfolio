"""Knowledge document model and its metadata schema.

Every document in the knowledge base carries the same five pieces of metadata:
document, domain, component, version and document type. Retrieval (Stage 3) and
the agent's source citations (Stage 5) both depend on these fields being present
and well typed, so they are validated at load time rather than trusted.

``Domain`` and ``DocType`` are closed sets on purpose: a typo in a document's
front matter should fail the load, not quietly create a new domain that nothing
ever filters on.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Domain = Literal[
    "atm",
    "cards",
    "payments",
    "digital-banking",
    "api",
    "configuration",
    "operations",
    "platform",
]

DocType = Literal[
    "reference",
    "api",
    "configuration",
    "runbook",
    "troubleshooting",
]

DOCUMENT_ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class DocumentMetadata(BaseModel):
    """Validated front matter of a single knowledge document.

    ``extra="forbid"`` means an unrecognised front-matter key is an error. A
    misspelled ``compnent:`` would otherwise be silently dropped and the
    document would lose the field retrieval filters on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(
        pattern=DOCUMENT_ID_PATTERN,
        description="Stable slug identifying the document; matches the filename.",
    )
    title: str = Field(min_length=1, description="Human readable document title.")
    domain: Domain = Field(description="Banking domain the document belongs to.")
    component: str = Field(
        min_length=1,
        description="Platform component the document describes.",
    )
    version: str = Field(
        min_length=1,
        description="Version of the component the document documents.",
    )
    doc_type: DocType = Field(description="Kind of document, used to weight results.")
    tags: tuple[str, ...] = Field(
        default=(),
        description="Free-form keywords; supplementary retrieval signal.",
    )


class KnowledgeDocument(BaseModel):
    """A loaded knowledge document: validated metadata plus its body text.

    ``content`` is the Markdown body with the front matter removed -- it is the
    text that gets chunked and embedded in Stage 3.
    """

    model_config = ConfigDict(frozen=True)

    metadata: DocumentMetadata
    content: str = Field(
        min_length=1,
        description="Markdown body with the front matter removed.",
    )
    source_path: str = Field(
        min_length=1,
        description=(
            "Path relative to the knowledge root, always POSIX-style so that "
            "citations are identical on Windows and in Docker."
        ),
    )

    @property
    def citation(self) -> str:
        """Short human-readable source reference for an answer."""
        return f"{self.metadata.title} ({self.source_path})"
