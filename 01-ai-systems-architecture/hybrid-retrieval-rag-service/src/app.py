"""Streamlit frontend for the retrieval service API."""

from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Document Q&A",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Document Q&A")
    st.caption("Hybrid retrieval + reranking over your documents")

    # Connection status
    try:
        health = requests.get(f"{API_BASE}/health", timeout=2).json()
        n_docs = health.get("documents_indexed", 0)
        st.success(f"API connected · **{n_docs}** chunks indexed")
        st.caption(f"Embeddings: `{health.get('embedding_model', '–')}`")
        st.caption(f"LLM: `{health.get('llm_model', '–')}`")
    except Exception:
        st.error("API not reachable.  \nStart with: `python -m uvicorn src.api.main:app --reload`")

    st.divider()

    # Document upload
    st.subheader("Ingest Documents")
    uploaded = st.file_uploader(
        "Drop PDF, TXT, or Markdown files",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
    )
    if uploaded and st.button("Ingest", type="primary"):
        with st.spinner(f"Processing {len(uploaded)} file(s)…"):
            try:
                r = requests.post(
                    f"{API_BASE}/ingest",
                    files=[("files", (f.name, f.getvalue(), f.type)) for f in uploaded],
                    timeout=120,
                )
                r.raise_for_status()
                for d in r.json():
                    st.success(
                        f"**{d['filename']}** — "
                        f"{d['chunks_created']} chunks · "
                        f"{d['characters_processed']:,} chars"
                    )
            except Exception as e:
                st.error(f"Ingestion failed: {e}")

    st.divider()

    # Ingested documents list
    st.subheader("Ingested Documents")
    if st.button("Refresh", key="refresh_docs"):
        st.session_state.pop("documents", None)
    if "documents" not in st.session_state:
        try:
            resp = requests.get(f"{API_BASE}/documents", timeout=5)
            resp.raise_for_status()
            st.session_state.documents = resp.json()
        except Exception:
            st.session_state.documents = []
    docs = st.session_state.get("documents", [])
    if docs:
        for doc in docs:
            st.caption(f"📄 **{doc['name']}** — {doc['chunks']} chunks")
    else:
        st.caption("No documents ingested yet.")

    st.divider()

    # Conversation management
    conv_id = st.text_input("Conversation ID", value="default")
    if st.button("Clear conversation"):
        requests.delete(f"{API_BASE}/conversation/{conv_id}", timeout=5)
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # Live metrics
    try:
        m = requests.get(f"{API_BASE}/metrics", timeout=2).json()
        st.subheader("Session metrics")
        col1, col2 = st.columns(2)
        col1.metric("Queries", m.get("query_count", 0))
        col2.metric("Avg latency", f"{m.get('avg_latency_ms', 0):.0f} ms")
        col1.metric("Errors", m.get("errors", 0))
        col2.metric("Avg tokens", f"{m.get('avg_tokens_per_query', 0):.0f}")
    except Exception:
        pass

# ── Chat ──────────────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

st.header("Chat")

# Render conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "sources" in msg:
            n_src = len(msg["sources"])
            lat = msg.get("latency_ms", 0)
            tok = msg.get("tokens_used", 0)
            reranked = msg.get("chunks_after_rerank", 0)
            with st.expander(
                f"Sources ({n_src}) · {lat:.0f} ms · {tok} tokens · reranked {reranked}"
            ):
                for i, src in enumerate(msg["sources"], 1):
                    meta = src.get("metadata", {})
                    score = src.get("score", 0.0)
                    st.markdown(
                        f"**[{i}] {meta.get('source', 'unknown')}** — rerank score: `{score:.3f}`"
                    )
                    st.text(src.get("content", "")[:400])
                    if i < n_src:
                        st.divider()

# Input box
if prompt := st.chat_input("Ask a question about your documents"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Thinking…")
        try:
            r = requests.post(
                f"{API_BASE}/query",
                json={"question": prompt, "conversation_id": conv_id},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            answer = data["answer"]
            placeholder.markdown(answer)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "sources": data.get("sources", []),
                    "latency_ms": data.get("latency_ms", 0),
                    "tokens_used": data.get("tokens_used", 0),
                    "chunks_after_rerank": data.get("chunks_after_rerank", 0),
                }
            )
        except requests.exceptions.RequestException as exc:
            placeholder.error(f"API error: {exc}")
