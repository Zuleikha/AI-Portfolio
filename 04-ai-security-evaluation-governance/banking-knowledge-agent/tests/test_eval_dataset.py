"""The Stage 11 evaluation dataset: loading, validation and references (11.A).

Free and offline: no model, no provider. The shipped dataset is checked against
the real corpus and the real tool registry, so a renamed document or tool fails
here rather than silently scoring zero in the evaluation.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from app.agent.models import DecisionReason
from app.core.config import Settings
from app.eval.dataset import (
    Category,
    DatasetError,
    EvalDataset,
    check_references,
    load_dataset,
)
from app.knowledge.loader import load_knowledge_base
from app.mcp.factory import build_tool_registry

VALID_CASE = """
  - id: know-001
    category: knowledge
    question: What component handles card authentication?
    expected_path: knowledge_required
    expected_docs: [card-authentication]
"""


def _write(tmp_path: Path, cases: str, thresholds: str = "") -> Path:
    body = thresholds or "thresholds: {recall_at_k: 0.5, mrr: 0.5, path_accuracy: 0.5}"
    path = tmp_path / "questions.yaml"
    path.write_text(f'version: "1.0"\n{body}\ncases:\n{cases}', encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def shipped() -> EvalDataset:
    return load_dataset(Settings().eval_dataset_path)


class TestShippedDataset:
    def test_it_loads(self, shipped):
        assert shipped.version
        assert len(shipped.cases) >= 40

    def test_it_lives_where_the_settings_say(self):
        assert Settings().eval_dataset_path.parts[-3:] == (
            "data",
            "eval",
            "questions.yaml",
        )

    def test_every_expected_document_and_tool_exists(self, shipped):
        documents = [
            doc.metadata.document_id
            for doc in load_knowledge_base(Settings().knowledge_dir)
        ]
        tools = [spec.name for spec in build_tool_registry().specs()]
        check_references(shipped, documents, tools)

    def test_every_category_is_covered(self, shipped):
        assert {case.category for case in shipped.cases} == set(get_args(Category))

    def test_every_deterministic_route_is_expected_somewhere(self, shipped):
        # additional_knowledge_required depends on a measured score, so no case
        # can demand it; it is accepted as a knowledge answer instead.
        wanted = set(get_args(DecisionReason)) - {"additional_knowledge_required"}
        assert {case.expected_path for case in shipped.cases} == wanted

    def test_each_tool_is_expected_at_least_once(self, shipped):
        expected = {tool for case in shipped.cases for tool in case.expected_tools}
        assert expected == {spec.name for spec in build_tool_registry().specs()}

    def test_thresholds_are_fractions(self, shipped):
        for value in shipped.thresholds.model_dump().values():
            assert 0.0 <= value <= 1.0


class TestLoading:
    def test_a_valid_file_loads(self, tmp_path):
        dataset = load_dataset(_write(tmp_path, VALID_CASE))
        assert dataset.cases[0].expected_docs == ("card-authentication",)
        assert dataset.cases[0].expected_tools == ()

    def test_a_missing_file_is_a_dataset_error(self, tmp_path):
        with pytest.raises(DatasetError, match="not found"):
            load_dataset(tmp_path / "absent.yaml")

    def test_malformed_yaml_is_a_dataset_error(self, tmp_path):
        path = tmp_path / "questions.yaml"
        path.write_text("cases: [unclosed", encoding="utf-8")
        with pytest.raises(DatasetError):
            load_dataset(path)

    def test_a_non_mapping_document_is_a_dataset_error(self, tmp_path):
        path = tmp_path / "questions.yaml"
        path.write_text("- just\n- a list\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="mapping"):
            load_dataset(path)

    def test_duplicate_ids_are_rejected(self, tmp_path):
        with pytest.raises(DatasetError, match="know-001"):
            load_dataset(_write(tmp_path, VALID_CASE + VALID_CASE))

    def test_an_unknown_path_is_rejected(self, tmp_path):
        case = VALID_CASE.replace("knowledge_required", "guess_the_answer")
        with pytest.raises(DatasetError):
            load_dataset(_write(tmp_path, case))

    def test_a_threshold_above_one_is_rejected(self, tmp_path):
        thresholds = "thresholds: {recall_at_k: 1.5, mrr: 0.5, path_accuracy: 0.5}"
        with pytest.raises(DatasetError):
            load_dataset(_write(tmp_path, VALID_CASE, thresholds))

    def test_a_bad_id_is_rejected(self, tmp_path):
        with pytest.raises(DatasetError):
            load_dataset(_write(tmp_path, VALID_CASE.replace("know-001", "Know 1")))

    def test_the_error_names_the_file(self, tmp_path):
        path = _write(tmp_path, VALID_CASE + VALID_CASE)
        with pytest.raises(DatasetError, match="questions.yaml"):
            load_dataset(path)


class TestCaseRules:
    """An expectation that cannot be true is refused when the file loads."""

    def test_a_refusal_cannot_expect_documents(self, tmp_path):
        case = VALID_CASE.replace("knowledge_required", "insufficient_evidence")
        with pytest.raises(DatasetError, match="refusal"):
            load_dataset(_write(tmp_path, case))

    def test_a_knowledge_answer_needs_documents(self, tmp_path):
        case = VALID_CASE.replace("    expected_docs: [card-authentication]\n", "")
        with pytest.raises(DatasetError, match="expected_docs"):
            load_dataset(_write(tmp_path, case))

    def test_a_live_reading_needs_tools(self, tmp_path):
        case = """
  - id: tool-001
    category: tool
    question: What version is PaymentEngine running?
    expected_path: live_status_only
"""
        with pytest.raises(DatasetError, match="expected_tools"):
            load_dataset(_write(tmp_path, case))

    def test_a_live_reading_cannot_expect_documents(self, tmp_path):
        case = """
  - id: tool-001
    category: tool
    question: What version is PaymentEngine running?
    expected_path: live_status_only
    expected_tools: [retrieve_system_version]
    expected_docs: [platform-component-overview]
"""
        with pytest.raises(DatasetError, match="expected_docs"):
            load_dataset(_write(tmp_path, case))

    def test_a_hybrid_answer_needs_both(self, tmp_path):
        case = """
  - id: hyb-001
    category: hybrid
    question: What does error code CSM-3010 mean?
    expected_path: knowledge_and_live_status_required
    expected_docs: [card-pin-verification]
"""
        with pytest.raises(DatasetError, match="expected_tools"):
            load_dataset(_write(tmp_path, case))


class TestReferences:
    def test_an_unknown_document_is_named(self, tmp_path):
        dataset = load_dataset(_write(tmp_path, VALID_CASE))
        with pytest.raises(DatasetError, match="card-authentication"):
            check_references(dataset, ["some-other-doc"], [])

    def test_an_unknown_tool_is_named(self, tmp_path):
        case = """
  - id: tool-001
    category: tool
    question: What version is PaymentEngine running?
    expected_path: live_status_only
    expected_tools: [retrieve_system_version]
"""
        dataset = load_dataset(_write(tmp_path, case))
        with pytest.raises(DatasetError, match="retrieve_system_version"):
            check_references(dataset, [], ["look_up_error_code"])
