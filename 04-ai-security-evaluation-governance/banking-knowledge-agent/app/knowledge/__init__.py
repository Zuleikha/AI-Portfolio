"""Knowledge base: synthetic banking documents and the loader that reads them.

Stage 2 owns document *sourcing* only -- parsing files from disk into validated,
metadata-rich :class:`KnowledgeDocument` objects. Chunking, embedding and vector
search are built on top of this in Stage 3.
"""

from __future__ import annotations

from app.knowledge.loader import (
    EmptyDocumentError,
    FrontMatterError,
    KnowledgeBaseNotFoundError,
    KnowledgeLoadError,
    MetadataError,
    load_document,
    load_knowledge_base,
)
from app.knowledge.models import (
    DocType,
    DocumentMetadata,
    Domain,
    KnowledgeDocument,
)

__all__ = [
    "DocType",
    "DocumentMetadata",
    "Domain",
    "EmptyDocumentError",
    "FrontMatterError",
    "KnowledgeBaseNotFoundError",
    "KnowledgeDocument",
    "KnowledgeLoadError",
    "MetadataError",
    "load_document",
    "load_knowledge_base",
]
