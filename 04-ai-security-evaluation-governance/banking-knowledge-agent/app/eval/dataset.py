"""The evaluation dataset: what "correct" means, one question at a time.

``data/eval/questions.yaml`` (``docs/HANDOVER.md`` 11.A) pairs each question with
the route the agent should take, the documents that hold the evidence, the tools
that should be called, and short facts the evidence or answer must contain.

**An expectation that cannot be true is refused when the file loads.** A refusal
that also expects documents, or a live reading with no tool, would score as a
failure forever and look like a system fault. The rules below mirror the routes
in :data:`app.agent.models.DecisionReason`, so the dataset cannot drift from them.

**References are checked separately** (:func:`check_references`) because they
need the corpus and the tool registry, which this module must not load itself: a
renamed document would otherwise score zero recall instead of failing loudly.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agent.models import DecisionReason
from app.core.tracing import traced

Category = Literal[
    "knowledge",
    "paraphrase",
    "tool",
    "hybrid",
    "failure",
    "off_topic",
    "injection",
]
"""The evaluation area a question exercises. Every one is covered by the dataset."""

CASE_ID_PATTERN = r"^[a-z]+-\d{3}$"
"""A category-style prefix and a three-digit number, e.g. ``know-001``."""

REFUSAL_PATHS: frozenset[str] = frozenset(
    {"insufficient_evidence", "no_searchable_content"}
)
"""Routes that end in a refusal: nothing retrieved, called or mentioned."""

DOCUMENT_PATHS: frozenset[str] = frozenset(
    {
        "knowledge_required",
        "additional_knowledge_required",
        "knowledge_and_live_status_required",
    }
)
"""Routes whose answer rests on documentation, so evidence must be named."""

TOOL_PATHS: frozenset[str] = frozenset(
    {"live_status_only", "knowledge_and_live_status_required"}
)
"""Routes that call at least one support tool."""


class DatasetError(ValueError):
    """The evaluation dataset is missing, malformed or names something unknown."""


class EvalCase(BaseModel):
    """One question and everything a correct run should show for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=CASE_ID_PATTERN, description="Stable, unique case id.")
    category: Category = Field(description="The evaluation area exercised.")
    question: str = Field(min_length=1, description="The question as asked.")
    expected_path: DecisionReason = Field(
        description="The route the agent should take."
    )
    expected_docs: tuple[str, ...] = Field(
        default=(), description="Document ids holding the evidence; a hit is any one."
    )
    expected_tools: tuple[str, ...] = Field(
        default=(), description="Tool names that must be called."
    )
    must_mention: tuple[str, ...] = Field(
        default=(), description="Facts the evidence (free) or answer (paid) contains."
    )

    @model_validator(mode="after")
    def _expectations_agree_with_the_route(self) -> EvalCase:
        validate_case_expectations(self)
        return self


class Thresholds(BaseModel):
    """Soft floors under the measured scores (``docs/HANDOVER.md`` 11.C)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recall_at_k: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    path_accuracy: float = Field(ge=0.0, le=1.0)


class EvalDataset(BaseModel):
    """The whole question set, with the floors its scores are gated on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=1)
    thresholds: Thresholds
    cases: tuple[EvalCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_are_unique(self) -> EvalDataset:
        validate_unique_ids(self.cases)
        return self


@traced
def validate_case_expectations(case: EvalCase) -> None:
    """Refuse expectations that the case's route can never satisfy.

    Raises:
        ValueError: With the case id and the rule broken. Pydantic wraps it, and
            :func:`load_dataset` reports it against the file.
    """
    path = case.expected_path
    if path in REFUSAL_PATHS:
        if case.expected_docs or case.expected_tools or case.must_mention:
            raise ValueError(
                f"{case.id}: a refusal ({path}) cannot expect documents, tools or "
                "facts, because nothing is retrieved, called or answered."
            )
        return
    if path in DOCUMENT_PATHS and not case.expected_docs:
        raise ValueError(
            f"{case.id}: {path} answers from documents; set expected_docs."
        )
    if path not in DOCUMENT_PATHS and case.expected_docs:
        raise ValueError(
            f"{case.id}: {path} searches no documentation, so expected_docs "
            "must be empty."
        )
    if path in TOOL_PATHS and not case.expected_tools:
        raise ValueError(f"{case.id}: {path} calls a tool; set expected_tools.")
    if path not in TOOL_PATHS and case.expected_tools:
        raise ValueError(
            f"{case.id}: {path} calls no tools, so expected_tools must be empty."
        )


@traced
def validate_unique_ids(cases: Iterable[EvalCase]) -> None:
    """Refuse a dataset in which two cases share an id.

    Raises:
        ValueError: Naming every duplicated id.
    """
    seen: set[str] = set()
    duplicates: dict[str, None] = {}
    for case in cases:
        if case.id in seen:
            duplicates.setdefault(case.id, None)
        seen.add(case.id)
    if duplicates:
        raise ValueError(f"duplicate case id(s): {', '.join(duplicates)}")


@traced
def load_dataset(path: Path) -> EvalDataset:
    """Read and validate an evaluation dataset.

    Args:
        path: The YAML file, normally ``Settings.eval_dataset_path``.

    Returns:
        The validated dataset.

    Raises:
        DatasetError: If the file is missing, is not valid YAML, is not a mapping,
            or breaks any rule on :class:`EvalDataset` or :class:`EvalCase`. The
            message names the file.
    """
    if not path.is_file():
        raise DatasetError(f"Evaluation dataset not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DatasetError(f"{path}: not valid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise DatasetError(
            f"{path}: the top level must be a mapping with version, thresholds "
            "and cases."
        )
    try:
        return EvalDataset.model_validate(raw)
    except ValidationError as exc:
        raise DatasetError(f"{path}: {exc}") from exc


@traced
def check_references(
    dataset: EvalDataset,
    document_ids: Iterable[str],
    tool_names: Iterable[str],
) -> None:
    """Fail if the dataset names a document or tool that does not exist.

    Args:
        dataset: The loaded dataset.
        document_ids: Every document id in the knowledge base.
        tool_names: Every tool name in the registry.

    Raises:
        DatasetError: Listing each unknown reference with its case id.
    """
    known_documents = set(document_ids)
    known_tools = set(tool_names)
    problems: list[str] = []
    for case in dataset.cases:
        problems.extend(
            f"{case.id}: unknown document '{document}'"
            for document in case.expected_docs
            if document not in known_documents
        )
        problems.extend(
            f"{case.id}: unknown tool '{tool}'"
            for tool in case.expected_tools
            if tool not in known_tools
        )
    if problems:
        raise DatasetError(
            "The evaluation dataset names things that do not exist: "
            + "; ".join(problems)
        )
