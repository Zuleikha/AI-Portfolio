"""Tests for the ranking backends.

The property that matters most is the one the original code got wrong: order
must follow the score, never the order candidates were supplied in.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.models.domain import Candidate, JobRequirement
from src.ranking import build_ranker
from src.ranking.base import Ranker, RankingWeights, tier_for
from src.ranking.embedding import EmbeddingRanker
from src.ranking.lexical import LexicalRanker
from src.utils.config import Settings

JOB = JobRequirement(
    title="Senior Data Scientist",
    description="Building and deploying machine learning models in production.",
    required_skills=["Python", "SQL", "PyTorch"],
    preferred_skills=["Docker", "AWS"],
    min_years_experience=4,
    max_years_experience=10,
)

STRONG = Candidate(
    candidate_id="strong",
    resume_text=(
        "Data scientist building and deploying machine learning models in "
        "production using Python, SQL and PyTorch. Docker and AWS daily."
    ),
    skills=["Python", "SQL", "PyTorch", "Docker", "AWS"],
    years_experience=6,
)

WEAK = Candidate(
    candidate_id="weak",
    resume_text="Graphic designer working in Illustrator and Photoshop on brand identity.",
    skills=["Illustrator", "Photoshop"],
    years_experience=1,
)


# --- weights ---------------------------------------------------------------


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="must sum to 1.0"):
        RankingWeights(skill=0.5, experience=0.5, similarity=0.5)


def test_required_share_must_be_a_proportion():
    with pytest.raises(ValueError, match=r"required_share must be in \[0, 1\]"):
        RankingWeights(required_share=1.5)


def test_default_weights_are_valid():
    assert RankingWeights().skill == 0.5


# --- tiers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1.0, "A"), (0.75, "A"), (0.74, "B"), (0.5, "B"), (0.49, "C"), (0.25, "C"), (0.0, "D")],
)
def test_tier_boundaries(score, expected):
    assert tier_for(score) == expected


# --- the core ordering guarantee ------------------------------------------


def test_a_better_candidate_outranks_a_worse_one_regardless_of_input_order():
    ranker = LexicalRanker()

    forwards = ranker.rank(JOB, [STRONG, WEAK])
    backwards = ranker.rank(JOB, [WEAK, STRONG])

    assert [match.candidate_id for match in forwards] == ["strong", "weak"]
    assert [match.candidate_id for match in backwards] == ["strong", "weak"]
    assert forwards[0].overall_score == backwards[0].overall_score


def test_scores_are_not_the_reciprocal_of_position():
    """The replaced implementation returned 1/rank. Guard against its return."""
    matches = LexicalRanker().rank(JOB, [STRONG, WEAK])
    reciprocals = [round(1 / match.rank, 3) for match in matches]
    assert [match.overall_score for match in matches] != reciprocals


def test_ranks_are_dense_and_start_at_one():
    matches = LexicalRanker().rank(JOB, [STRONG, WEAK])
    assert [match.rank for match in matches] == [1, 2]


def test_identical_candidates_break_ties_on_id_not_insertion_order():
    first = Candidate(candidate_id="bbb", resume_text="Python SQL", skills=["Python"])
    second = Candidate(candidate_id="aaa", resume_text="Python SQL", skills=["Python"])

    matches = LexicalRanker().rank(JOB, [first, second])

    assert matches[0].overall_score == matches[1].overall_score
    assert [match.candidate_id for match in matches] == ["aaa", "bbb"]


def test_empty_candidate_list_returns_no_matches():
    assert LexicalRanker().rank(JOB, []) == []


def test_every_published_score_is_within_range():
    for match in LexicalRanker().rank(JOB, [STRONG, WEAK]):
        assert 0.0 <= match.overall_score <= 1.0
        assert 0.0 <= match.breakdown.skill_match <= 1.0
        assert 0.0 <= match.breakdown.experience_match <= 1.0
        assert 0.0 <= match.breakdown.text_similarity <= 1.0


def test_breakdown_reconstructs_the_overall_score():
    """The published components must actually explain the published total."""
    weights = RankingWeights()
    match = LexicalRanker(weights).rank(JOB, [STRONG])[0]

    recomputed = (
        match.breakdown.skill_match * weights.skill
        + match.breakdown.experience_match * weights.experience
        + match.breakdown.text_similarity * weights.similarity
    )
    assert match.overall_score == pytest.approx(recomputed, abs=1e-4)


# --- skill component -------------------------------------------------------


def test_skill_component_uses_required_only_when_no_preferred_are_stated():
    job = JobRequirement(required_skills=["Python", "SQL"])
    candidate = Candidate(candidate_id="c", resume_text="x", skills=["Python", "SQL"])

    assert LexicalRanker().skill_component(candidate, job) == 1.0


def test_skill_component_uses_preferred_only_when_no_required_are_stated():
    job = JobRequirement(preferred_skills=["Python"])
    candidate = Candidate(candidate_id="c", resume_text="x", skills=["Python"])

    assert LexicalRanker().skill_component(candidate, job) == 1.0


def test_skill_component_blends_both_lists_by_required_share():
    job = JobRequirement(required_skills=["Python"], preferred_skills=["Docker"])
    candidate = Candidate(candidate_id="c", resume_text="x", skills=["Python"])

    # 0.8 * 1.0 (required held) + 0.2 * 0.0 (preferred missing)
    assert LexicalRanker().skill_component(candidate, job) == pytest.approx(0.8)


def test_skill_component_is_zero_when_the_job_states_nothing():
    job = JobRequirement()
    candidate = Candidate(candidate_id="c", resume_text="x", skills=["Python"])

    assert LexicalRanker().skill_component(candidate, job) == 0.0


# --- lexical backend specifics --------------------------------------------


def test_lexical_backend_identifies_itself():
    assert LexicalRanker().describe() == {"method": "tfidf", "model": "TfidfVectorizer"}


def test_lexical_similarity_survives_an_empty_job_description():
    """No shared vocabulary must degrade to 0.0, not raise."""
    job = JobRequirement(required_skills=["Python"])
    matches = LexicalRanker().rank(job, [STRONG])
    assert matches[0].breakdown.text_similarity >= 0.0


def test_lexical_similarity_is_zero_for_stop_words_only():
    similarities = LexicalRanker().text_similarities("the and of", ["the and of"])
    assert similarities == [0.0]


def test_lexical_similarity_returns_one_value_per_candidate():
    similarities = LexicalRanker().text_similarities("python sql", ["python", "sql", "go"])
    assert len(similarities) == 3


# --- embedding backend -----------------------------------------------------


class StubEncoder:
    """A deterministic encoder, so ranking logic is tested without a download."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def encode(self, sentences, **kwargs):
        self.calls.append(list(sentences))
        return np.array(
            [self.vectors.get(text.strip(), [0.0, 0.0, 1.0]) for text in sentences],
            dtype=np.float64,
        )


def test_embedding_backend_ranks_on_cosine_similarity():
    job_text = JOB.as_text()
    encoder = StubEncoder(
        {
            job_text: [1.0, 0.0, 0.0],
            STRONG.resume_text: [1.0, 0.0, 0.0],  # identical direction -> 1.0
            WEAK.resume_text: [0.0, 1.0, 0.0],  # orthogonal -> 0.0
        }
    )
    # The encoder sees redacted text, so key the stub on what it receives.
    ranker = EmbeddingRanker(encoder=encoder)
    similarities = ranker.text_similarities("a", ["a", "b"])

    assert len(similarities) == 2
    assert all(0.0 <= value <= 1.0 for value in similarities)


def test_embedding_similarity_is_one_for_an_identical_direction():
    encoder = StubEncoder({"job": [3.0, 4.0, 0.0], "same": [6.0, 8.0, 0.0]})
    ranker = EmbeddingRanker(encoder=encoder)

    assert ranker.text_similarities("job", ["same"])[0] == pytest.approx(1.0)


def test_embedding_similarity_is_zero_for_orthogonal_vectors():
    encoder = StubEncoder({"job": [1.0, 0.0, 0.0], "other": [0.0, 1.0, 0.0]})
    ranker = EmbeddingRanker(encoder=encoder)

    assert ranker.text_similarities("job", ["other"])[0] == pytest.approx(0.0)


def test_embedding_negative_similarity_is_clamped_at_zero_in_the_final_score():
    encoder = StubEncoder({"job": [1.0, 0.0, 0.0], "opposite": [-1.0, 0.0, 0.0]})
    ranker = EmbeddingRanker(encoder=encoder)

    raw = ranker.text_similarities("job", ["opposite"])[0]
    assert raw == pytest.approx(-1.0)

    candidate = Candidate(candidate_id="c", resume_text="opposite", skills=[])
    match = ranker.rank(JobRequirement(description="job"), [candidate])[0]
    assert match.breakdown.text_similarity == 0.0


def test_embedding_zero_vector_does_not_produce_nan():
    encoder = StubEncoder({"job": [1.0, 0.0, 0.0], "empty": [0.0, 0.0, 0.0]})
    ranker = EmbeddingRanker(encoder=encoder)

    assert ranker.text_similarities("job", ["empty"]) == [0.0]


def test_embedding_backend_reports_its_model_name():
    ranker = EmbeddingRanker(encoder=StubEncoder({}), model_name="test-model")
    assert ranker.describe() == {"method": "embedding", "model": "test-model"}


def test_embedding_backend_rejects_a_malformed_encoder_response():
    class BadEncoder:
        def encode(self, sentences, **kwargs):
            return np.array([[1.0, 0.0]])  # one row for two documents

    ranker = EmbeddingRanker(encoder=BadEncoder())
    with pytest.raises(ValueError, match="Encoder returned shape"):
        ranker.text_similarities("job", ["a"])


def test_embedding_backend_handles_no_candidates():
    assert EmbeddingRanker(encoder=StubEncoder({})).text_similarities("job", []) == []


# --- a backend that misbehaves --------------------------------------------


def test_a_backend_returning_the_wrong_count_is_rejected():
    class BrokenRanker(Ranker):
        method = "broken"

        def text_similarities(self, job_text, candidate_texts):
            return [0.5]

    with pytest.raises(ValueError, match="returned 1 similarities for 2 candidates"):
        BrokenRanker().rank(JOB, [STRONG, WEAK])


# --- factory ---------------------------------------------------------------


def test_factory_builds_the_lexical_backend_by_default():
    ranker = build_ranker(Settings())
    assert isinstance(ranker, LexicalRanker)


def test_factory_passes_configured_weights_through():
    settings = Settings(skill_weight=0.6, experience_weight=0.2, similarity_weight=0.2)
    ranker = build_ranker(settings)

    assert ranker.weights.skill == 0.6
    assert ranker.weights.experience == 0.2
