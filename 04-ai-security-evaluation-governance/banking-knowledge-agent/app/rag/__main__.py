"""Command-line entry point for the RAG pipeline.

::

    python -m app.rag build                 # build and persist the vector index
    python -m app.rag search "<question>"   # one query, with scores and sources
    python -m app.rag demo                  # the representative retrieval examples
    python -m app.rag calibrate             # evidence for the min-score threshold

Indexing is a build step rather than something the application does at startup,
so it needs a way to be run. ``demo`` and ``calibrate`` exist because the two
questions worth asking of a retriever -- *does it find the right passage?* and
*does it stay quiet when there is no right passage?* -- should be answerable
from the command line, not only from the test suite.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.rag.models import RetrievalResult
from app.rag.pipeline import build_index, get_retriever
from app.rag.retriever import Retriever

DEMO_QUESTIONS: tuple[str, ...] = (
    "Why would an ATM transaction fail after card authentication?",
    "What component handles card authentication?",
    "Which API is used for payment authorisation?",
    "How would I troubleshoot a failed cash withdrawal?",
    "What configuration controls transaction limits?",
)
"""The five seed questions from the project brief."""

OFF_TOPIC_QUESTIONS: tuple[str, ...] = (
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "Who won the 1998 world cup?",
    "What is the weather forecast for tomorrow?",
    "Recommend a good science fiction novel.",
)
"""Questions the knowledge base cannot answer. Retrieval must return nothing."""

PARAPHRASED_QUESTIONS: tuple[str, ...] = (
    "customer says money left the account but no cash came out",
    "the dispenser is jammed, what now",
    "where do I set the daily cap on withdrawals",
    "which service checks the PIN",
    "how do I retry a payment safely without double charging",
)
"""Questions sharing little vocabulary with the corpus -- the semantic test."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.rag",
        description="Build and query the banking knowledge vector index.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build", help="Build and persist the vector index.")

    search = subparsers.add_parser("search", help="Retrieve for a single question.")
    search.add_argument("query", help="The question to search for.")
    search.add_argument("-k", type=int, default=None, help="Number of passages.")
    search.add_argument("--domain", default=None, help="Restrict to one domain.")
    search.add_argument(
        "--min-score", type=float, default=None, help="Override the score floor."
    )

    subparsers.add_parser("demo", help="Run the representative retrieval examples.")
    subparsers.add_parser("calibrate", help="Show the score distributions.")

    args = parser.parse_args(argv)

    # The corpus and the citations contain em dashes and middots. A Windows
    # console defaults to cp1252 and would mangle them, so force UTF-8 rather
    # than degrade the output to ASCII everywhere else.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    configure_logging()

    if args.command == "build":
        return _build()
    if args.command == "search":
        return _search(args.query, args.k, args.domain, args.min_score)
    if args.command == "demo":
        return _demo()
    return _calibrate()


def _build() -> int:
    """Build the index and report what it contains."""
    settings = get_settings()
    retriever = build_index(settings)
    print(f"Indexed {len(retriever.store)} chunks")
    print(f"  model      {retriever.embedder.model_id}")
    print(f"  dimension  {retriever.embedder.dimension}")
    print(f"  max tokens {retriever.embedder.max_tokens}")
    print(f"  written to {settings.vectorstore_dir}")
    return 0


def _search(
    query: str,
    k: int | None,
    domain: str | None,
    min_score: float | None,
) -> int:
    """Retrieve for one question and print the result."""
    retriever = get_retriever()
    result = retriever.retrieve(
        query,
        k=k,
        filters={"domain": domain} if domain else None,
        min_score=min_score,
    )
    _print_result(result)
    return 0


def _demo() -> int:
    """Print retrieval for the seed, paraphrased and off-topic questions."""
    retriever = get_retriever()

    _print_group(retriever, "SEED QUESTIONS (from the project brief)", DEMO_QUESTIONS)
    _print_group(
        retriever,
        "PARAPHRASED — little shared vocabulary, tests semantic matching",
        PARAPHRASED_QUESTIONS,
    )
    _print_group(
        retriever,
        "OFF-TOPIC — the knowledge base must return nothing",
        OFF_TOPIC_QUESTIONS,
    )
    return 0


def _calibrate() -> int:
    """Show in-domain vs off-topic score distributions.

    The threshold is only defensible if the two distributions actually separate.
    This prints the gap so the configured floor can be justified, and re-checked
    whenever the corpus or the model changes.
    """
    retriever = get_retriever()
    on_topic = DEMO_QUESTIONS + PARAPHRASED_QUESTIONS

    def top_scores(questions: Sequence[str]) -> list[float]:
        scores = []
        for question in questions:
            # min_score=-1 disables the floor: this measures the raw ranking.
            result = retriever.retrieve(question, k=1, min_score=-1.0)
            scores.append(result.top_score or -1.0)
        return sorted(scores)

    relevant = top_scores(on_topic)
    irrelevant = top_scores(OFF_TOPIC_QUESTIONS)

    print("Top-1 cosine score, best match per question\n")
    print(
        f"  on-topic  ({len(relevant):2d} questions)  "
        f"min {relevant[0]:.3f}  median {relevant[len(relevant) // 2]:.3f}  "
        f"max {relevant[-1]:.3f}"
    )
    print(
        f"  off-topic ({len(irrelevant):2d} questions)  "
        f"min {irrelevant[0]:.3f}  median {irrelevant[len(irrelevant) // 2]:.3f}  "
        f"max {irrelevant[-1]:.3f}"
    )

    gap = relevant[0] - irrelevant[-1]
    print(
        f"\n  separation: {gap:+.3f} "
        f"(worst on-topic {relevant[0]:.3f} - best off-topic {irrelevant[-1]:.3f})"
    )
    midpoint = (relevant[0] + irrelevant[-1]) / 2
    print(f"  midpoint:   {midpoint:.3f}")
    print(f"  configured: {get_settings().retrieval_min_score:.3f}")

    if gap <= 0:
        print(
            "\n  WARNING: the distributions overlap. No single threshold "
            "separates them; a reranker or hybrid search would be needed."
        )
    return 0


def _print_group(retriever: Retriever, title: str, questions: Sequence[str]) -> None:
    """Print retrieval results for a labelled group of questions."""
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    for question in questions:
        _print_result(retriever.retrieve(question))


def _print_result(result: RetrievalResult) -> None:
    """Print one retrieval result: the question, its matches and its sources."""
    print(f"\nQ: {result.query}")
    if result.is_empty:
        print(
            f"   NO MATCH — nothing scored above {result.min_score:.2f} "
            f"of {result.candidates_considered} chunks."
        )
        print("   (The agent must say it has no documented answer.)")
        return

    for rank, scored in enumerate(result.chunks, start=1):
        chunk = scored.chunk
        heading = chunk.heading or "(preamble)"
        print(f"   {rank}. {scored.score:.3f}  {chunk.metadata.title} — {heading}")
        print(
            f"      {chunk.metadata.domain} / {chunk.metadata.component} "
            f"v{chunk.metadata.version} · {chunk.source_path}"
        )
        print(f"      {_preview(chunk.content)}")

    print(f"   sources: {len(result.sources)} document(s)")


def _preview(text: str, width: int = 96) -> str:
    """One-line preview of a chunk's content."""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else f"{flat[: width - 1]}…"


if __name__ == "__main__":
    sys.exit(main())
