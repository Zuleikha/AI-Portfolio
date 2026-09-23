"""
indexer.py
Embeds parsed DITA chunks using OpenAI embeddings and stores in ChromaDB.
"""

import logging
import os

import chromadb
from openai import OpenAI

logger = logging.getLogger(__name__)

COLLECTION_NAME = "dita_docs"
EMBED_BATCH_SIZE = 100

_openai_client = None


def get_openai_client() -> OpenAI:
    """Lazily create the OpenAI client so import works without an API key."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set — required for embedding and answer generation"
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def get_chroma_client(persist_dir: str = "./chroma_store"):
    return chromadb.PersistentClient(path=persist_dir)


def get_or_create_collection(chroma_client):
    return chroma_client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using OpenAI text-embedding-3-small, in batches."""
    client = get_openai_client()
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = client.embeddings.create(model="text-embedding-3-small", input=batch)
        embeddings.extend(item.embedding for item in response.data)
    return embeddings


def collection_count(persist_dir: str = "./chroma_store") -> int:
    """Number of documents currently indexed."""
    collection = get_or_create_collection(get_chroma_client(persist_dir))
    return collection.count()


def index_chunks(chunks: list[dict], persist_dir: str = "./chroma_store"):
    """Embed and index all chunks into ChromaDB."""
    chroma_client = get_chroma_client(persist_dir)
    collection = get_or_create_collection(chroma_client)

    # Clear existing data for clean re-index
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        logger.info("Cleared %d existing documents", len(existing["ids"]))

    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts)

    collection.add(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "topic_id": c["topic_id"],
                "topic_title": c["topic_title"],
                "section_title": c["section_title"],
                "source_file": c["source_file"],
                "tags": c["tags"],
                "topic_shortdesc": c["topic_shortdesc"],
            }
            for c in chunks
        ],
    )

    logger.info("Indexed %d chunks into ChromaDB", len(chunks))
    return len(chunks)
