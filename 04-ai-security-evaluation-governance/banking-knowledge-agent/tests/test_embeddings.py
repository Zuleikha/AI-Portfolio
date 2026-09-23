"""Tests for the embedding layer.

The contract that matters is the :class:`Embedder` protocol, not any one model:
fixed width, unit length, a token count comparable to ``max_tokens``. Everything
downstream — the chunker's budget, the store's dot-product search — is built on
those guarantees, so they are asserted directly.

The real sentence-transformers model is exercised in ``test_rag_integration.py``;
these tests stay fast and offline.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.config import Settings
from app.rag.embeddings import (
    Embedder,
    EmbeddingError,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)


@pytest.fixture
def embedder() -> HashingEmbedder:
    """A deterministic embedder."""
    return HashingEmbedder(dimension=64)


# --------------------------------------------------------------------------
# Protocol conformance
# --------------------------------------------------------------------------


def test_hashing_embedder_satisfies_the_protocol(embedder):
    assert isinstance(embedder, Embedder)


def test_sentence_transformer_embedder_satisfies_the_protocol():
    # Constructed but never used: this asserts conformance without paying the
    # cost of loading the model, which is the point of the lazy load.
    assert isinstance(SentenceTransformerEmbedder(Settings()), Embedder)


def test_constructing_the_real_embedder_does_not_load_the_model():
    instance = SentenceTransformerEmbedder(Settings())
    assert instance._model is None
    assert instance.model_id == "sentence-transformers/all-MiniLM-L6-v2"


# --------------------------------------------------------------------------
# Vector guarantees
# --------------------------------------------------------------------------


def test_document_vectors_have_the_declared_width(embedder):
    matrix = embedder.embed_documents(["alpha beta", "gamma delta", "epsilon"])
    assert matrix.shape == (3, 64)


def test_query_vector_has_the_declared_width(embedder):
    assert embedder.embed_query("alpha beta").shape == (64,)


def test_vectors_are_unit_length_so_cosine_is_a_dot_product(embedder):
    for vector in embedder.embed_documents(["alpha beta gamma", "delta epsilon"]):
        assert math.isclose(float(np.linalg.norm(vector)), 1.0, rel_tol=1e-5)


def test_vectors_are_float32(embedder):
    assert embedder.embed_documents(["alpha"]).dtype == np.float32
    assert embedder.embed_query("alpha").dtype == np.float32


def test_embedding_is_deterministic_across_calls(embedder):
    first = embedder.embed_query("ATM transaction reversal")
    second = embedder.embed_query("ATM transaction reversal")
    assert np.array_equal(first, second)


def test_embedding_is_deterministic_across_processes(embedder):
    # blake2b, not Python's hash(): PYTHONHASHSEED randomises str hashing per
    # process, which would make a persisted index unreadable by the next run.
    assert math.isclose(
        float(embedder.embed_query("reversal") @ embedder.embed_query("reversal")),
        1.0,
        rel_tol=1e-5,
    )


def test_shared_vocabulary_scores_higher_than_disjoint_vocabulary(embedder):
    query = embedder.embed_query("atm cash withdrawal failed")
    related = embedder.embed_query("atm cash withdrawal troubleshooting")
    unrelated = embedder.embed_query("sourdough bread baking recipe")
    assert float(query @ related) > float(query @ unrelated)


def test_embedding_an_empty_batch_returns_an_empty_matrix(embedder):
    assert embedder.embed_documents([]).shape == (0, 64)


def test_text_with_no_usable_tokens_yields_a_zero_vector(embedder):
    assert float(np.linalg.norm(embedder.embed_query("!!! ???"))) == 0.0


# --------------------------------------------------------------------------
# Token counting — what the chunker's budget depends on
# --------------------------------------------------------------------------


def test_token_count_is_reported_in_the_same_units_as_max_tokens(embedder):
    assert embedder.count_tokens("one two three four five") == 5
    assert embedder.max_tokens == 256


def test_empty_text_counts_as_zero_tokens(embedder):
    assert embedder.count_tokens("") == 0


# --------------------------------------------------------------------------
# Failure modes
# --------------------------------------------------------------------------


def test_embedding_a_blank_query_fails_loudly(embedder):
    with pytest.raises(EmbeddingError, match="empty query"):
        embedder.embed_query("   ")


def test_invalid_dimensions_are_rejected():
    with pytest.raises(ValueError, match="positive"):
        HashingEmbedder(dimension=0)
    with pytest.raises(ValueError, match="positive"):
        HashingEmbedder(max_tokens=0)


# --------------------------------------------------------------------------
# Selection by configuration
# --------------------------------------------------------------------------


def test_hashing_embedder_is_selected_by_configuration():
    assert isinstance(
        get_embedder(Settings(embedding_model="hashing")), HashingEmbedder
    )


def test_sentence_transformer_is_the_default():
    assert isinstance(get_embedder(Settings()), SentenceTransformerEmbedder)


def test_the_model_id_identifies_which_embedder_built_an_index(embedder):
    assert embedder.model_id == "hashing-64"
    assert HashingEmbedder(dimension=128).model_id == "hashing-128"
