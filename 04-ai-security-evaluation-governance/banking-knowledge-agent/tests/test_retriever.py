"""Tests for the retrieval layer and the end-to-end indexing pipeline.

Retrieval is tested without an LLM anywhere in sight. That is the point of the
layering: when an answer is wrong in Stage 5, the first question is always
"did retrieval find the right passage?", and it must be answerable on its own.

These run on the hashing embedder, so they assert *pipeline* behaviour --
ranking order, filtering, the score floor, staleness, source formatting -- and
never semantic quality, which needs the real model and lives in
``test_rag_integration.py``.
"""

from __future__ import annotations

import pytest

from app.rag.chunker import chunk_documents
from app.rag.embeddings import HashingEmbedder
from app.rag.models import RetrievalResult
from app.rag.pipeline import (
    StaleIndexError,
    build_index,
    embed_chunks,
    fingerprint_documents,
    get_retriever,
    load_retriever,
)
from app.rag.retriever import Retriever
from app.rag.vectorstore import (
    IncompatibleIndexError,
    IndexNotFoundError,
    InMemoryVectorStore,
    UnknownFilterFieldError,
)

# --------------------------------------------------------------------------
# Indexing the real corpus
# --------------------------------------------------------------------------


def test_the_whole_corpus_is_indexed(retriever, corpus):
    assert len(retriever.store) > len(corpus)


def test_every_document_contributes_at_least_one_chunk(retriever, corpus):
    indexed = {
        result.chunk.document_id
        for result in retriever.store.search(
            retriever.embedder.embed_query("banking"), k=len(retriever.store)
        )
    }
    assert indexed == {document.metadata.document_id for document in corpus}


def test_every_indexed_chunk_fits_the_embedding_window(retriever):
    results = retriever.store.search(
        retriever.embedder.embed_query("banking"), k=len(retriever.store)
    )
    for result in results:
        assert result.chunk.token_count <= retriever.embedder.max_tokens


def test_chunk_ids_are_unique_across_the_index(retriever):
    results = retriever.store.search(
        retriever.embedder.embed_query("banking"), k=len(retriever.store)
    )
    ids = [result.chunk.chunk_id for result in results]
    assert len(set(ids)) == len(ids)


def test_index_dimension_matches_the_embedder(retriever):
    assert retriever.store.dimension == retriever.embedder.dimension
    assert retriever.store.model_id == retriever.embedder.model_id


def test_embedding_an_empty_chunk_list_returns_nothing():
    assert embed_chunks([], HashingEmbedder()) == ()


def test_embed_chunks_pairs_each_chunk_with_its_own_vector(corpus, rag_settings):
    embedder = HashingEmbedder()
    chunks = chunk_documents(corpus[:2], embedder, rag_settings)
    embedded = embed_chunks(chunks, embedder)
    assert len(embedded) == len(chunks)
    assert [item.chunk.chunk_id for item in embedded] == [c.chunk_id for c in chunks]
    assert all(len(item.embedding) == embedder.dimension for item in embedded)


# --------------------------------------------------------------------------
# Retrieval behaviour
# --------------------------------------------------------------------------


def test_retrieval_returns_a_result_object(retriever):
    result = retriever.retrieve("ATM transaction reversal")
    assert isinstance(result, RetrievalResult)
    assert result.query == "ATM transaction reversal"


def test_results_are_ordered_best_first(retriever):
    result = retriever.retrieve("ATM cash withdrawal dispense failure", min_score=-1.0)
    scores = [scored.score for scored in result.chunks]
    assert scores == sorted(scores, reverse=True)


def test_top_k_limits_the_number_of_passages(retriever):
    assert len(retriever.retrieve("ATM", k=2, min_score=-1.0).chunks) == 2


def test_default_top_k_comes_from_settings(retriever, rag_settings):
    result = retriever.retrieve("ATM transaction", min_score=-1.0)
    assert len(result.chunks) == rag_settings.retrieval_top_k


def test_every_returned_chunk_carries_its_source_metadata(retriever):
    for scored in retriever.retrieve("ATM cash withdrawal", min_score=-1.0).chunks:
        assert scored.chunk.metadata.document_id
        assert scored.chunk.metadata.component
        assert scored.chunk.metadata.version
        assert scored.chunk.source_path.endswith(".md")


def test_candidates_considered_reports_the_whole_index(retriever):
    result = retriever.retrieve("ATM", min_score=-1.0)
    assert result.candidates_considered == len(retriever.store)


def test_top_score_reflects_the_best_match(retriever):
    result = retriever.retrieve("ATM cash withdrawal", min_score=-1.0)
    assert result.top_score == result.chunks[0].score


def test_retrieval_is_deterministic(retriever):
    first = retriever.retrieve("reversal exception queue")
    second = retriever.retrieve("reversal exception queue")
    assert [c.chunk.chunk_id for c in first.chunks] == [
        c.chunk.chunk_id for c in second.chunks
    ]


def test_an_empty_query_is_rejected(retriever):
    with pytest.raises(ValueError, match="empty query"):
        retriever.retrieve("   ")


def test_a_query_with_no_usable_tokens_returns_no_evidence(retriever):
    # Punctuation only. The hashing embedder has nothing to hash, so the query
    # vector is all zeros, every score is 0.0 and the floor rejects the lot.
    # Returning nothing is the right outcome -- it routes into the agent's
    # "I have no documented answer" path instead of surfacing arbitrary chunks.
    assert retriever.retrieve("!!! ???").is_empty


# --------------------------------------------------------------------------
# The score floor — what makes "I don't know" possible
# --------------------------------------------------------------------------


def test_a_high_floor_rejects_everything(retriever):
    result = retriever.retrieve("ATM cash withdrawal", min_score=0.99)
    assert result.is_empty
    assert result.chunks == ()


def test_an_empty_result_still_reports_why(retriever):
    result = retriever.retrieve("ATM cash withdrawal", min_score=0.99)
    assert result.candidates_considered == len(retriever.store)
    assert result.min_score == 0.99
    assert result.top_score is None


def test_no_returned_chunk_ever_scores_below_the_floor(retriever):
    result = retriever.retrieve("payment authorisation", min_score=0.1)
    assert all(scored.score >= 0.1 for scored in result.chunks)


def test_the_floor_defaults_to_the_configured_value(retriever, rag_settings):
    assert retriever.retrieve("ATM").min_score == rag_settings.retrieval_min_score


def test_disabling_the_floor_returns_the_raw_ranking(retriever):
    assert not retriever.retrieve("sourdough bread baking", min_score=-1.0).is_empty


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------


def test_retrieval_can_be_restricted_to_one_domain(retriever):
    result = retriever.retrieve(
        "transaction failure", filters={"domain": "payments"}, min_score=-1.0
    )
    assert {c.chunk.metadata.domain for c in result.chunks} == {"payments"}


def test_a_filter_narrows_the_candidate_pool(retriever):
    filtered = retriever.retrieve(
        "transaction", filters={"domain": "cards"}, min_score=-1.0
    )
    unfiltered = retriever.retrieve("transaction", min_score=-1.0)
    assert filtered.candidates_considered < unfiltered.candidates_considered


def test_filtering_by_component_works(retriever):
    result = retriever.retrieve(
        "limits", filters={"component": "LimitService"}, min_score=-1.0
    )
    assert {c.chunk.metadata.component for c in result.chunks} == {"LimitService"}


def test_an_unknown_filter_field_fails_loudly(retriever):
    with pytest.raises(UnknownFilterFieldError):
        retriever.retrieve("ATM", filters={"nonsense": "x"})


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


def test_sources_are_deduplicated_by_document(retriever):
    result = retriever.retrieve("ATM transaction lifecycle stages", k=5, min_score=-1.0)
    documents = {c.chunk.document_id for c in result.chunks}
    assert len(result.sources) == len(documents)


def test_a_source_names_the_document_component_version_and_path(retriever):
    source = retriever.retrieve("ATM cash withdrawal", min_score=-1.0).sources[0]
    assert "v" in source
    assert source.endswith(".md]")


def test_an_empty_result_has_no_sources(retriever):
    assert retriever.retrieve("ATM", min_score=0.99).sources == ()


def test_retrieve_many_returns_one_result_per_question(retriever):
    results = retriever.retrieve_many(["ATM failure", "payment authorisation"])
    assert len(results) == 2
    assert results[0].query == "ATM failure"


# --------------------------------------------------------------------------
# Persistence and freshness
# --------------------------------------------------------------------------


def test_building_persists_an_index_that_can_be_reloaded(rag_settings):
    build_index(rag_settings)
    reloaded = load_retriever(rag_settings)
    assert len(reloaded.store) > 0


def test_a_reloaded_index_returns_the_same_results(rag_settings):
    built = build_index(rag_settings)
    reloaded = load_retriever(rag_settings)
    query = "ATM cash withdrawal failure"
    assert [c.chunk.chunk_id for c in built.retrieve(query).chunks] == [
        c.chunk.chunk_id for c in reloaded.retrieve(query).chunks
    ]


def test_loading_without_building_fails_loudly(rag_settings):
    with pytest.raises(IndexNotFoundError):
        load_retriever(rag_settings)


def test_an_index_built_by_a_different_model_is_refused(rag_settings):
    build_index(rag_settings)
    other = HashingEmbedder(dimension=128)
    with pytest.raises(IncompatibleIndexError):
        load_retriever(rag_settings, embedder=other)


def test_a_stale_index_is_refused_rather_than_silently_served(rag_settings, tmp_path):
    # Serving a stale index is the worst failure available: the answer stays
    # fluent and the citation still resolves, so nobody notices.
    build_index(rag_settings)
    store, _ = InMemoryVectorStore.load(
        rag_settings.vectorstore_dir, model_id="hashing-256", dimension=256
    )
    store.save(rag_settings.vectorstore_dir, corpus_fingerprint="a-different-corpus")

    with pytest.raises(StaleIndexError, match="Rebuild"):
        load_retriever(rag_settings)


def test_freshness_checking_can_be_skipped(rag_settings):
    build_index(rag_settings)
    store, _ = InMemoryVectorStore.load(
        rag_settings.vectorstore_dir, model_id="hashing-256", dimension=256
    )
    store.save(rag_settings.vectorstore_dir, corpus_fingerprint="stale")
    assert load_retriever(rag_settings, check_freshness=False) is not None


def test_get_retriever_builds_the_index_when_none_exists(rag_settings):
    assert not rag_settings.vectorstore_dir.exists()
    assert len(get_retriever(rag_settings).store) > 0
    assert rag_settings.vectorstore_dir.exists()


def test_get_retriever_rebuilds_a_stale_index(rag_settings):
    build_index(rag_settings)
    store, _ = InMemoryVectorStore.load(
        rag_settings.vectorstore_dir, model_id="hashing-256", dimension=256
    )
    store.save(rag_settings.vectorstore_dir, corpus_fingerprint="stale")
    assert len(get_retriever(rag_settings).store) > 0


def test_the_fingerprint_changes_when_a_document_changes(corpus):
    edited = list(corpus)
    edited[0] = corpus[0].model_copy(update={"content": corpus[0].content + "\n\nNew."})
    assert fingerprint_documents(corpus) != fingerprint_documents(tuple(edited))


def test_the_fingerprint_changes_when_only_metadata_changes(corpus):
    edited = list(corpus)
    edited[0] = corpus[0].model_copy(
        update={"metadata": corpus[0].metadata.model_copy(update={"version": "9.9"})}
    )
    assert fingerprint_documents(corpus) != fingerprint_documents(tuple(edited))


def test_the_fingerprint_ignores_document_ordering(corpus):
    assert fingerprint_documents(corpus) == fingerprint_documents(
        tuple(reversed(corpus))
    )


def test_the_fingerprint_is_stable_for_unchanged_documents(corpus):
    assert fingerprint_documents(corpus) == fingerprint_documents(corpus)


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------


def test_a_retriever_can_be_built_from_any_embedder_and_store(rag_settings):
    embedder = HashingEmbedder(dimension=32)
    store = InMemoryVectorStore(model_id=embedder.model_id, dimension=32)
    composed = Retriever(embedder, store, rag_settings)
    # Both collaborators are injected protocols; an empty store is a valid one.
    assert composed.retrieve("anything at all").is_empty
