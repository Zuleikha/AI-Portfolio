"""
Shared fixtures for the DITA RAG test suite.

All external services (OpenAI, ChromaDB) are mocked — no API keys or vector
store required. If chromadb is not installed (it is heavy), a stub module is
injected so app.indexer can be imported.
"""

import sys
from unittest.mock import MagicMock

import pytest

try:
    import chromadb  # noqa: F401
except ImportError:
    sys.modules["chromadb"] = MagicMock()


SAMPLE_CHUNK = {
    "chunk_id": "installation_sec1",
    "topic_id": "installation",
    "topic_title": "Installing the Product",
    "topic_shortdesc": "How to install",
    "section_id": "sec1",
    "section_title": "System Requirements",
    "text": "You need 8 GB of RAM.",
    "source_file": "installation",
    "tags": "installation, system-requirements",
}


@pytest.fixture
def sample_chunk():
    return dict(SAMPLE_CHUNK)


@pytest.fixture
def retrieved_chunk():
    """A chunk as returned by retriever.search()."""
    return {
        "chunk_id": SAMPLE_CHUNK["chunk_id"],
        "text": SAMPLE_CHUNK["text"],
        "metadata": {
            "topic_id": SAMPLE_CHUNK["topic_id"],
            "topic_title": SAMPLE_CHUNK["topic_title"],
            "section_title": SAMPLE_CHUNK["section_title"],
            "source_file": SAMPLE_CHUNK["source_file"],
            "tags": SAMPLE_CHUNK["tags"],
            "topic_shortdesc": SAMPLE_CHUNK["topic_shortdesc"],
        },
        "score": 0.91,
    }
