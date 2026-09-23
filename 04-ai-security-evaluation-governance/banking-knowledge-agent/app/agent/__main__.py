"""Command-line entry point for the knowledge agent.

::

    python -m app.agent ask "<question>"   # answer one question
    python -m app.agent demo               # the five seed questions, end to end
    python -m app.agent chat               # a conversation; follow-ups keep context
    python -m app.agent conversation-demo  # a scripted conversation of follow-ups

**By default every run is offline and free**: the embedding model is local, and
the default provider is the in-process mock.

If ``BKA_LLM_PROVIDER`` names a paid vendor, both commands say so before doing
anything, and ``demo`` refuses outright unless ``--paid`` is passed. ``demo``
asks every question below, so an accidental paid run is one billed call per
question rather than one -- the command that fans out is the one that needs the
seatbelt. This is a deliberate guard, not a formality: nothing else in the
repository stands between an exported key and a bill.

What the output is designed to show is the *provenance*, not the prose. The mock
provider's answer text is a wiring check, not a generated answer — the parts
worth reading are the route (Stage 7: every choice point and its outcome), how
many searches ran, how many passages reached the prompt, and which documents and
tools they came from.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from app.agent.factory import get_agent
from app.agent.models import AgentAnswer
from app.conversation.factory import get_conversation_service
from app.conversation.models import ConversationAnswer
from app.core.cli import RULE
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.llm.factory import warn_if_paid

SEED_QUESTIONS: tuple[str, ...] = (
    "Why would an ATM transaction fail after card authentication?",
    "What component handles card authentication?",
    "Which API is used for payment authorisation?",
    "How would I troubleshoot a failed cash withdrawal?",
    "What configuration controls transaction limits?",
)
"""The five worked examples from ``prompt.md`` §13."""

TOOL_QUESTIONS: tuple[str, ...] = (
    # Asks what a code MEANS: an explanation of a live identifier, so both.
    "What does error code LIM-4001 mean?",
    # Ask only for a reading: Stage 7's tool-only route, no search at all.
    "What is the status of transaction TXN-20260911-004473?",
    "Is CoreBankingAdapter healthy?",
    "What version is CardSecurityModule running?",
    # A reading that finds nothing. The tool-only plan pulls in documentation,
    # and the answer must report the miss, not refuse.
    "What is the status of transaction TXN-19990101-000001?",
)
"""Five questions that exercise Agent -> MCP -> Tool -> Result (Stages 6 and 7).

Chosen so the demo shows the point rather than merely the plumbing: two of these
return a live value that *disagrees with the documentation* -- the effective ATM
limit and the version CardSecurityModule is actually running -- which is the
whole argument for having tools alongside retrieval.
"""

RETRIEVE_MORE_QUESTIONS: tuple[str, ...] = (
    # Weak first searches (measured 0.490 and 0.442 with the real model). The
    # first is refined from the best passage's component, the second from the
    # component the error-code tool reports (docs/HANDOVER.md 7.D).
    "Why did the withdrawal reverse?",
    "What does SWX-7004 mean?",
)
"""Two questions whose first search is weak enough to be refined (Stage 7)."""

CONTROL_QUESTIONS: tuple[str, ...] = (
    # Answerable-looking, and outside the corpus: it must be refused after a
    # search rather than answered from something adjacent.
    "What is the capital of France?",
    # Nothing to search for at all: refused without a search and without a model
    # call, by the routing policy rather than by the score floor.
    "!!! ???",
)
"""Two questions the agent must decline, for two different reasons."""

CONVERSATION_QUESTIONS: tuple[str, ...] = (
    "What does error code LIM-4001 mean?",
    # carried_identifiers: "it" is LIM-4001, so the error-code tool is called.
    "Which component raises it?",
    "What version is CoreBankingAdapter running?",
    # substituted_identifier: the version question again, for another component.
    "What about CardSecurityModule?",
    # carried_identifiers from the substituted question: health of CSM.
    "Is it healthy?",
    "How would I troubleshoot a failed cash withdrawal?",
    # carried_topic: no identifier to carry, so the previous topic is searched.
    "What should I check first on that?",
)
"""One conversation exercising every Stage 8 resolution rule, in one session."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.agent",
        description="Ask the knowledge agent a technical question.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask = subparsers.add_parser("ask", help="Answer one question.")
    ask.add_argument("question", help="The question to answer.")

    demo = subparsers.add_parser("demo", help="Answer the seed questions end to end.")
    demo.add_argument(
        "--paid",
        action="store_true",
        help="Allow the demo to run against a paid provider (one call per question).",
    )

    subparsers.add_parser(
        "chat",
        help="Hold a conversation; a blank line, 'exit' or end of input stops it.",
    )
    conversation_demo = subparsers.add_parser(
        "conversation-demo", help="Run a scripted conversation of follow-up questions."
    )
    conversation_demo.add_argument(
        "--paid",
        action="store_true",
        help="Allow a paid provider (one call per question).",
    )

    args = parser.parse_args(argv)

    # Citations carry em dashes and middots; a cp1252 console would mangle them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    configure_logging()
    settings = get_settings()

    if args.command == "ask":
        return _ask(args.question, settings)
    if args.command == "chat":
        return _chat(settings)
    if args.command == "conversation-demo":
        return _conversation_demo(settings, allow_paid=args.paid)
    return _demo(settings, allow_paid=args.paid)


def _ask(question: str, settings: Settings) -> int:
    """Answer and print a single question."""
    warn_if_paid(settings)
    agent = get_agent(settings)
    _print_answer(agent.ask(question))
    return 0


def _demo(settings: Settings, allow_paid: bool = False) -> int:
    """Answer the seed questions and the two control questions."""
    questions = (
        SEED_QUESTIONS + TOOL_QUESTIONS + RETRIEVE_MORE_QUESTIONS + CONTROL_QUESTIONS
    )
    if warn_if_paid(settings) and not allow_paid:
        # Refused rather than warned: this command asks every question above, so
        # the cost of getting it wrong is that many calls, and the user cannot
        # take it back once it has run.
        print(
            f"REFUSED: demo would make up to {len(questions)} paid calls. "
            "Re-run with --paid to confirm you accept the cost."
        )
        return 2

    agent = get_agent(settings)
    provider = agent.llm_service.provider

    print(RULE)
    print(f"Provider: {provider.provider_id} / {provider.model_id}")
    print(f"Retriever: {agent.retriever.embedder.model_id}")
    print(RULE)

    for question in questions:
        print()
        _print_answer(agent.ask(question))
    return 0


def _chat(settings: Settings) -> int:
    """Hold one conversation over standard input."""
    warn_if_paid(settings)
    service = get_conversation_service(settings)
    session = service.start()
    print("Conversation started. A blank line, 'exit' or end of input stops it.")
    try:
        while True:
            print("> ", end="", flush=True)
            line = sys.stdin.readline()
            question = line.strip()
            if not line or not question or question.lower() in {"exit", "quit"}:
                break
            print()
            _print_turn(service.ask(session, question))
    finally:
        service.end(session)
    return 0


def _conversation_demo(settings: Settings, allow_paid: bool = False) -> int:
    """Run :data:`CONVERSATION_QUESTIONS` as one session."""
    if warn_if_paid(settings) and not allow_paid:
        print(
            f"REFUSED: conversation-demo would make up to "
            f"{len(CONVERSATION_QUESTIONS)} paid calls. "
            "Re-run with --paid to confirm you accept the cost."
        )
        return 2

    service = get_conversation_service(settings)
    provider = service.agent.llm_service.provider
    print(RULE)
    print(f"Provider: {provider.provider_id} / {provider.model_id}")
    print(RULE)

    session = service.start()
    try:
        for question in CONVERSATION_QUESTIONS:
            print()
            _print_turn(service.ask(session, question))
    finally:
        service.end(session)
    return 0


def _print_turn(result: ConversationAnswer) -> None:
    """Print one conversation turn: how it was resolved, then the answer."""
    context = result.context
    print(f"#  turn {result.turn} · you asked: {context.question}")
    if context.is_follow_up:
        carried = f" · carried {', '.join(context.carried)}" if context.carried else ""
        print(
            f"   [follow-up: {context.resolution}{carried} · "
            f"{len(context.history)} earlier question(s) sent, "
            f"{context.history_dropped} dropped]"
        )
    else:
        print("   [standalone: no conversation history sent]")
    _print_answer(result.answer)


def _print_answer(answer: AgentAnswer) -> None:
    """Print one answer with the execution record that makes it checkable."""
    print(f"Q  {answer.question}")
    print(f"A  {answer.text}")
    print(f"   [decision: {answer.decision.reason} — {answer.decision.explanation}]")
    route = " → ".join(f"{step.step}={step.outcome}" for step in answer.decisions)
    print(f"   [route: {route}]")

    retrieval = answer.retrieval
    if retrieval.performed:
        top = "none" if retrieval.top_score is None else f"{retrieval.top_score:.3f}"
        print(
            f"   [retrieval: {retrieval.passes} search(es) · "
            f"{retrieval.chunks_returned} of "
            f"{retrieval.candidates_considered} passages cleared "
            f"{retrieval.min_score} · top score {top}]"
        )
    else:
        print("   [retrieval: not performed]")

    for call, invocation in zip(answer.tools, answer.decision.tools, strict=True):
        outcome = "ok" if call.ok else f"not found ({call.error_code})"
        print(f"   [tool: {call.tool} -> {outcome} · {invocation.reason}]")

    if answer.refused:
        print("   [refused: no supporting evidence; no model call was made]")
        return

    print(
        f"   [grounded: {answer.chunks_used} passage(s) in the prompt · "
        f"prompt v{answer.prompt_version}]"
    )
    for index, source in enumerate(answer.sources, start=1):
        print(f"   [{index}] {source}")
    for index, result in enumerate(answer.tool_results, start=1):
        print(f"   [T{index}] {result.tool} · {result.summary}")


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
