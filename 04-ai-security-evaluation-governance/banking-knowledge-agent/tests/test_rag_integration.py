"""Retrieval *quality* tests, against the real sentence-transformers model.

Every other RAG test runs on the hashing embedder and asserts mechanics. These
assert the thing that actually matters and that mechanics cannot prove: that a
question asked in an engineer's words finds the passage that answers it, and
that a question the corpus cannot answer finds nothing.

They are the guard against the two failure modes that make a RAG system worse
than useless:

* **Silent truncation** -- a chunk longer than the model's window is cut off
  without an error, so a passage quietly stops being findable.
* **Confident irrelevance** -- an off-topic question still returns the five
  least-bad chunks, and an LLM handed five banking passages writes a confident
  banking answer to a question about the weather.

Marked ``integration``. They need the model in the local Hugging Face cache and
take a few seconds; deselect with ``-m "not integration"``.
"""

from __future__ import annotations

import pytest

from app.rag.embeddings import SentenceTransformerEmbedder
from app.rag.pipeline import build_index

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_retriever():
    """A retriever over the real corpus and the real model, built once.

    Module-scoped: loading the transformer costs seconds, and every test here
    reads from the index without mutating it.
    """
    from app.core.config import Settings

    return build_index(Settings(environment="test", log_to_file=False), persist=False)


# --------------------------------------------------------------------------
# The model contract the chunker is built on
# --------------------------------------------------------------------------


def test_the_model_reports_the_window_the_chunker_budgets_against():
    embedder = SentenceTransformerEmbedder()
    assert embedder.max_tokens == 256
    assert embedder.dimension == 384


def test_no_indexed_chunk_is_silently_truncated(real_retriever):
    # The invariant. all-MiniLM-L6-v2 truncates past 256 tokens with no error,
    # so a chunk over the limit is a passage that has quietly stopped being
    # findable. Measured with the model's own tokenizer, not a word estimate.
    embedder = real_retriever.embedder
    results = real_retriever.store.search(
        embedder.embed_query("banking"), k=len(real_retriever.store)
    )
    for result in results:
        actual = embedder.count_tokens(result.chunk.embedding_text)
        assert (
            actual <= embedder.max_tokens
        ), f"{result.chunk.chunk_id} is {actual} tokens and would be truncated"
        assert result.chunk.token_count == actual


def test_real_vectors_are_unit_length(real_retriever):
    import numpy as np

    vector = real_retriever.embedder.embed_query("ATM withdrawal failure")
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)


# --------------------------------------------------------------------------
# The five seed questions from the project brief
# --------------------------------------------------------------------------

SEED_EXPECTATIONS = [
    (
        "Why would an ATM transaction fail after card authentication?",
        "atm-transaction-lifecycle",
    ),
    ("What component handles card authentication?", "card-authentication"),
    ("Which API is used for payment authorisation?", "payment-authorisation-api"),
    (
        "How would I troubleshoot a failed cash withdrawal?",
        "atm-cash-withdrawal-troubleshooting",
    ),
    (
        "What configuration controls transaction limits?",
        "transaction-limits-configuration",
    ),
]


@pytest.mark.parametrize(("question", "expected_document"), SEED_EXPECTATIONS)
def test_seed_question_retrieves_its_document_first(
    real_retriever, question, expected_document
):
    result = real_retriever.retrieve(question)
    assert not result.is_empty, f"no evidence retrieved for: {question}"
    assert result.chunks[0].chunk.document_id == expected_document


@pytest.mark.parametrize(("question", "expected_document"), SEED_EXPECTATIONS)
def test_seed_question_scores_well_clear_of_the_floor(
    real_retriever, question, expected_document
):
    result = real_retriever.retrieve(question)
    assert result.top_score is not None
    assert result.top_score > 0.5


@pytest.mark.parametrize(("question", "expected_document"), SEED_EXPECTATIONS)
def test_seed_question_returns_usable_sources(
    real_retriever, question, expected_document
):
    result = real_retriever.retrieve(question)
    assert result.sources
    assert any(expected_document in source for source in result.sources)


def test_the_lifecycle_question_finds_the_post_authentication_section(real_retriever):
    # The specific question the corpus was written to answer. It should land on
    # the section, not merely the right document.
    result = real_retriever.retrieve(
        "Why would an ATM transaction fail after card authentication?"
    )
    assert result.chunks[0].chunk.heading is not None
    assert "after card authentication" in result.chunks[0].chunk.heading.lower()


# --------------------------------------------------------------------------
# Paraphrase — the reason a neural embedder was chosen over lexical matching
# --------------------------------------------------------------------------

PARAPHRASE_EXPECTATIONS = [
    # No shared vocabulary with the document title or headings.
    ("customer says money left the account but no cash came out", "atm"),
    ("the dispenser is jammed, what now", "atm"),
    ("where do I set the daily cap on withdrawals", "configuration"),
    ("which service checks the PIN", "cards"),
]


@pytest.mark.parametrize(("question", "expected_domain"), PARAPHRASE_EXPECTATIONS)
def test_paraphrased_question_finds_the_right_domain(
    real_retriever, question, expected_domain
):
    result = real_retriever.retrieve(question)
    assert not result.is_empty, f"no evidence retrieved for: {question}"
    domains = {scored.chunk.metadata.domain for scored in result.chunks}
    assert expected_domain in domains


def test_a_paraphrase_matches_the_same_document_as_the_direct_question(real_retriever):
    direct = real_retriever.retrieve(
        "How would I troubleshoot a failed cash withdrawal?"
    )
    paraphrased = real_retriever.retrieve(
        "customer says money left the account but no cash came out"
    )
    assert not paraphrased.is_empty
    assert {c.chunk.document_id for c in paraphrased.chunks} & {
        c.chunk.document_id for c in direct.chunks
    }


# --------------------------------------------------------------------------
# Refusal — the behaviour Stage 5 depends on
# --------------------------------------------------------------------------

OFF_TOPIC = [
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "Who won the 1998 world cup?",
    "What is the weather forecast for tomorrow?",
    "Recommend a good science fiction novel.",
]


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_off_topic_question_retrieves_nothing(real_retriever, question):
    result = real_retriever.retrieve(question)
    assert result.is_empty, (
        f"'{question}' returned {result.top_score:.3f}; the agent would be handed "
        "banking passages for a question the corpus cannot answer"
    )


def test_the_score_distributions_actually_separate(real_retriever):
    # The threshold is only defensible if on-topic and off-topic scores do not
    # overlap. If this ever fails, no single floor works and the fix is a
    # reranker or hybrid search -- not a nudged constant.
    on_topic = [
        real_retriever.retrieve(question, k=1, min_score=-1.0).top_score or -1.0
        for question, _ in SEED_EXPECTATIONS
    ]
    off_topic = [
        real_retriever.retrieve(question, k=1, min_score=-1.0).top_score or -1.0
        for question in OFF_TOPIC
    ]
    assert min(on_topic) > max(off_topic), (
        f"distributions overlap: worst on-topic {min(on_topic):.3f} is not above "
        f"best off-topic {max(off_topic):.3f}"
    )


def test_the_configured_floor_sits_between_the_distributions(
    real_retriever, real_settings
):
    on_topic = min(
        real_retriever.retrieve(question, k=1, min_score=-1.0).top_score or -1.0
        for question, _ in SEED_EXPECTATIONS
    )
    off_topic = max(
        real_retriever.retrieve(question, k=1, min_score=-1.0).top_score or -1.0
        for question in OFF_TOPIC
    )
    assert off_topic < real_settings.retrieval_min_score < on_topic


# --------------------------------------------------------------------------
# Filtering with the real model
# --------------------------------------------------------------------------


def test_a_domain_filter_still_finds_relevant_evidence(real_retriever):
    result = real_retriever.retrieve(
        "how are limits evaluated", filters={"domain": "configuration"}
    )
    assert not result.is_empty
    assert {c.chunk.metadata.domain for c in result.chunks} == {"configuration"}


def test_a_persisted_real_index_round_trips(real_settings):
    from app.rag.pipeline import load_retriever

    built = build_index(real_settings)
    reloaded = load_retriever(real_settings)
    question = "Why would an ATM transaction fail after card authentication?"
    assert [c.chunk.chunk_id for c in built.retrieve(question).chunks] == [
        c.chunk.chunk_id for c in reloaded.retrieve(question).chunks
    ]
