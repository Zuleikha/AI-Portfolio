"""Command-line scorecard for the Stage 11 evaluation.

::

    python -m app.eval                      # FREE: mock provider, rule checks
    python -m app.eval --dataset other.yaml # a different question set
    python -m app.eval -k 3                 # recall@3 instead of recall@top_k
    python -m app.eval --paid               # PAID: the configured real model

**Free by default, whatever the environment says** (``docs/HANDOVER.md`` 11.B).
Without ``--paid`` the agent is built on the mock provider even if
``BKA_LLM_PROVIDER`` names a vendor, so an exported key cannot turn a routine
evaluation into a bill. ``--paid`` refuses unless the provider is a paid one
*and* ``BKA_LLM_API_KEY`` is set, and prints how many questions it will send
before any provider is built.

Exit code: 0 when every gate passes, 1 when a floor or invariant fails, 2 when a
paid run is refused.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.agent.agent import KnowledgeAgent
from app.core.cli import RULE
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.tracing import traced
from app.eval.dataset import check_references, load_dataset
from app.eval.report import render_report
from app.eval.runner import Mode, run_evaluation
from app.knowledge.loader import load_knowledge_base
from app.llm.factory import PAID_PROVIDERS, get_llm_service, is_paid_provider
from app.llm.mock import MockLLMProvider
from app.llm.service import LLMService
from app.mcp.factory import get_tool_registry
from app.rag.pipeline import get_retriever


@traced
def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    """Run the evaluation and print the scorecard.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.
        settings: Application settings. Defaults to the cached singleton.

    Returns:
        A process exit code (see the module docstring).

    Raises:
        DatasetError: If the dataset is missing, invalid or names an unknown
            document or tool.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.eval",
        description="Score the knowledge agent against the evaluation dataset.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset file (BKA_EVAL_DATASET_PATH).",
    )
    parser.add_argument(
        "-k", type=int, default=None, help="Rank cut-off (BKA_RETRIEVAL_TOP_K)."
    )
    parser.add_argument(
        "--paid",
        action="store_true",
        help="Evaluate the configured PAID model: one billed call per question.",
    )
    args = parser.parse_args(argv)
    if args.k is not None and args.k < 1:
        parser.error("-k must be at least 1")

    # Case ids and details are ASCII, but a Windows console defaults to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    resolved = settings or get_settings()
    configure_logging(resolved)

    if args.paid:
        refusal = paid_refusal(resolved)
        if refusal is not None:
            print(refusal)
            return 2

    dataset = load_dataset(args.dataset or resolved.eval_dataset_path)

    mode: Mode
    if args.paid:
        print(RULE)
        print(
            f"!! PAID run: BKA_LLM_PROVIDER={resolved.llm_provider}. "
            f"{len(dataset.cases)} question(s), up to one billed call each."
        )
        print(RULE)
        llm_service = get_llm_service(resolved)
        mode = "paid"
    else:
        if is_paid_provider(resolved):
            print(
                f"Note: BKA_LLM_PROVIDER={resolved.llm_provider} is ignored. This run "
                "is free and uses the mock provider; pass --paid to evaluate the "
                "real model."
            )
        llm_service = LLMService(MockLLMProvider(), resolved)
        mode = "mock"

    registry = get_tool_registry()
    documents = load_knowledge_base(resolved.knowledge_dir)
    check_references(
        dataset,
        (document.metadata.document_id for document in documents),
        (spec.name for spec in registry.specs()),
    )
    agent = KnowledgeAgent(
        get_retriever(resolved), llm_service, resolved, tools=registry
    )
    report = run_evaluation(
        dataset, agent, k=args.k or resolved.retrieval_top_k, mode=mode
    )
    print(render_report(report))
    return 1 if report.failed_floors() else 0


@traced
def paid_refusal(settings: Settings) -> str | None:
    """Why a ``--paid`` run cannot start, or None when it may."""
    if not is_paid_provider(settings):
        return (
            f"REFUSED: --paid needs BKA_LLM_PROVIDER set to a paid provider "
            f"({', '.join(PAID_PROVIDERS)}); it is '{settings.llm_provider}'."
        )
    if settings.llm_api_key is None:
        return "REFUSED: --paid needs BKA_LLM_API_KEY set in the environment."
    return None


if __name__ == "__main__":
    sys.exit(main())
