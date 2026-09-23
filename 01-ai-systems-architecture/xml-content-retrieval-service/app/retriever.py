"""
retriever.py
Semantic search over indexed DITA chunks and RAG answer generation.
"""

from app.indexer import (
    embed_texts,
    get_chroma_client,
    get_openai_client,
    get_or_create_collection,
)


def search(query: str, n_results: int = 4, persist_dir: str = "./chroma_store") -> list[dict]:
    """Retrieve top-n chunks relevant to the query."""
    chroma_client = get_chroma_client(persist_dir)
    collection = get_or_create_collection(chroma_client)

    query_embedding = embed_texts([query])[0]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append(
            {
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": round(1 - results["distances"][0][i], 4),
            }
        )
    return chunks


def generate_answer(query: str, chunks: list[dict]) -> str:
    """Generate an answer using retrieved chunks as context."""
    if not chunks:
        return "No relevant documentation found for your query."

    context = "\n\n".join(
        [
            f"[{c['metadata']['topic_title']} > {c['metadata']['section_title']}]\n{c['text']}"
            for c in chunks
        ]
    )

    system_prompt = (
        "You are a helpful documentation assistant for Bentley software products. "
        "Answer questions using only the provided documentation context. "
        "Be concise and accurate. If the answer is not in the context, say so clearly."
    )

    user_prompt = f"Documentation context:\n{context}\n\nQuestion: {query}"

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=500,
    )

    return response.choices[0].message.content
