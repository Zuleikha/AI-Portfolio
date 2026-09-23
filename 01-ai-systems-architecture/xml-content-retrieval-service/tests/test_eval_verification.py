"""
Unit tests for eval/verify_questions.py and the significance machinery.

These guard the *evaluation* rather than the service. An eval that silently
accepts a broken label set produces numbers that look like findings, which is
worse than producing none, so the guards get the same test treatment as the
production code.

Fully offline: the synthetic corpora here are built in tmp_path, and none of it
touches the fetched PMC corpus, which is gitignored and may be absent.
"""

import pytest

from eval.scoring import paired_bootstrap
from eval.verify_questions import content_words, verify


def chunk(source="doc", section="s1", text="The sky is blue today."):
    return {
        "chunk_id": f"{source}_{section}",
        "source_file": source,
        "section_id": section,
        "text": text,
        "topic_title": "T",
        "section_title": "S",
        "tags": "general",
    }


def question(qid="q1", source="doc", section="s1", span="sky is blue", text="What colour?"):
    return {
        "id": qid,
        "question": text,
        "source_file": source,
        "section_id": section,
        "answer_span": span,
    }


class TestVerify:
    def test_clean_set_passes(self):
        errors, warnings = verify([chunk()], [question()])
        assert errors == [] and warnings == []

    def test_missing_chunk_is_an_error(self):
        errors, _ = verify([chunk()], [question(section="nope")])
        assert len(errors) == 1 and "no chunk" in errors[0]

    def test_span_absent_from_named_section_is_an_error(self):
        errors, _ = verify([chunk()], [question(span="the sea is green")])
        assert len(errors) == 1 and "span not found" in errors[0]

    def test_span_in_two_chunks_is_an_error(self):
        chunks = [chunk(section="s1"), chunk(section="s2")]
        errors, _ = verify(chunks, [question()])
        assert len(errors) == 1 and "occurs in 2 chunks" in errors[0]

    def test_whitespace_differences_are_tolerated(self):
        errors, _ = verify([chunk(text="The sky\n  is   blue today.")], [question()])
        assert errors == []

    def test_case_differences_are_tolerated(self):
        errors, _ = verify([chunk()], [question(span="SKY IS BLUE")])
        assert errors == []

    def test_duplicate_ids_are_an_error(self):
        errors, _ = verify([chunk()], [question(), question()])
        # Both the duplicate-id check and the uniqueness check have opinions
        # here; the duplicate must be among them.
        assert any("duplicate question ids" in e for e in errors)

    def test_echoing_question_warns_but_does_not_fail(self):
        errors, warnings = verify([chunk()], [question(text="Is the sky blue?")])
        assert errors == []
        assert len(warnings) == 1 and "echoes" in warnings[0]

    def test_paraphrase_does_not_warn(self):
        errors, warnings = verify([chunk()], [question(text="What colour is it overhead?")])
        assert errors == [] and warnings == []


class TestContentWords:
    def test_stopwords_removed(self):
        assert content_words("How many of the events were in the arm") == {"events", "arm"}

    def test_digits_ignored(self):
        # A shared number is not a vocabulary leak — the question is allowed to
        # ask "how many" about a figure it does not name.
        assert content_words("349 categories") == {"categories"}


class TestPairedBootstrap:
    def test_identical_scores_give_zero_difference(self):
        result = paired_bootstrap([0.5] * 10, [0.5] * 10)
        assert result["mean_difference"] == 0.0
        assert not result["excludes_zero"]

    def test_consistent_advantage_is_detected(self):
        result = paired_bootstrap([1.0] * 30, [0.2] * 30)
        assert result["mean_difference"] == pytest.approx(0.8)
        assert result["excludes_zero"]

    def test_noisy_small_difference_is_not_detected(self):
        a = [1.0, 0.0] * 10
        b = [0.0, 1.0] * 10
        assert not paired_bootstrap(a, b)["excludes_zero"]

    def test_interval_brackets_the_mean(self):
        result = paired_bootstrap([0.9, 0.1, 0.5, 0.7, 0.3], [0.2, 0.4, 0.1, 0.9, 0.5])
        low, high = result["ci95"]
        assert low <= result["mean_difference"] <= high

    def test_deterministic_for_a_given_seed(self):
        a, b = [0.9, 0.1, 0.5, 0.4], [0.2, 0.4, 0.1, 0.8]
        assert paired_bootstrap(a, b) == paired_bootstrap(a, b)

    def test_mismatched_lengths_rejected(self):
        with pytest.raises(ValueError, match="equal-length"):
            paired_bootstrap([0.1], [0.1, 0.2])

    def test_empty_input_rejected(self):
        with pytest.raises(ValueError, match="no questions"):
            paired_bootstrap([], [])


class TestShippedQuestionSets:
    """The DITA set ships in the repo, so it is verified on every run.

    The PMC set cannot be: its corpus is fetched and gitignored. It is checked
    by `python -m eval.verify_questions --data data/pmc` after fetching.
    """

    def test_dita_question_set_describes_the_shipped_corpus(self):
        from pathlib import Path

        from eval.chunkers import structure_aware_chunks
        from eval.run_comparison import QUESTION_SETS, load_questions

        data_dir = Path(__file__).resolve().parents[1] / "data"
        errors, _ = verify(
            structure_aware_chunks(str(data_dir)), load_questions(QUESTION_SETS["dita"])
        )
        assert errors == []
