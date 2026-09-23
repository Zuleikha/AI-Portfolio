"""Stage 8: resolving a follow-up question, and the history limits.

Pure rules: no agent, no retriever, no model. The design these tests pin is
recorded in ``docs/HANDOVER.md`` §8.C and guide §20.24-§20.25.
"""

from __future__ import annotations

import pytest

from app.conversation.context import (
    MAX_CARRIED_IDENTIFIERS,
    find_identifiers,
    resolve_follow_up,
)
from app.conversation.models import ConversationTurn
from app.core.config import Settings


def turn(
    question: str,
    resolved: str | None = None,
    topic: str | None = None,
    number: int = 1,
) -> ConversationTurn:
    return ConversationTurn(
        number=number,
        question=question,
        resolved_question=resolved or question,
        topic=topic or resolved or question,
        answer_text="An earlier answer that must never be carried.",
        decision="knowledge_required",
        refused=False,
    )


@pytest.fixture
def settings(llm_settings: Settings) -> Settings:
    return llm_settings.model_copy(
        update={
            "conversation_max_history_turns": 3,
            "conversation_max_history_chars": 1000,
        }
    )


LIM_QUESTION = "Which component raises LIM-4001?"
WITHDRAWAL = "How would I troubleshoot a failed cash withdrawal?"


class TestIdentifiers:
    def test_every_identifier_kind_is_found_in_question_order(self):
        found = find_identifiers(
            "Is corebankingadapter why TXN-20260911-004473 hit LIM-4001 "
            "under limits.atm.daily_withdrawal_amount?"
        )
        assert [(i.kind, i.value) for i in found] == [
            ("component", "CoreBankingAdapter"),
            ("transaction_reference", "TXN-20260911-004473"),
            ("error_code", "LIM-4001"),
            ("key", "limits.atm.daily_withdrawal_amount"),
        ]

    def test_a_plain_question_has_none(self):
        assert find_identifiers(WITHDRAWAL) == ()


class TestStandalone:
    def test_the_first_turn_is_standalone(self, settings: Settings):
        context = resolve_follow_up("What does it mean?", (), settings)
        assert context.resolution == "standalone"
        assert context.resolved_question == "What does it mean?"
        assert context.history == ()
        assert context.is_follow_up is False

    def test_a_question_naming_its_own_identifier_stands_alone(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "Is it true that CoreBankingAdapter is healthy?",
            (turn(LIM_QUESTION),),
            settings,
        )
        assert context.resolution == "standalone"
        assert "LIM-4001" not in context.resolved_question

    def test_a_new_question_without_a_reference_word_stands_alone(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "How do ATM withdrawals work?", (turn(LIM_QUESTION),), settings
        )
        assert context.resolution == "standalone"

    def test_reference_words_match_whole_words_only(self, settings: Settings):
        context = resolve_follow_up(
            "Which item thereafter logs withdrawals?", (turn(LIM_QUESTION),), settings
        )
        assert context.resolution == "standalone"

    def test_a_zero_turn_window_disables_conversation_context(self, settings: Settings):
        disabled = settings.model_copy(update={"conversation_max_history_turns": 0})
        context = resolve_follow_up(
            "What does it mean?", (turn(LIM_QUESTION),), disabled
        )
        assert context.resolution == "standalone"
        assert context.history == ()


class TestCarriedIdentifiers:
    def test_a_pronoun_carries_the_previous_identifier(self, settings: Settings):
        context = resolve_follow_up(
            "What does it mean?", (turn(LIM_QUESTION),), settings
        )
        assert context.resolution == "carried_identifiers"
        assert context.carried == ("LIM-4001",)
        assert context.resolved_question.startswith("What does it mean?")
        assert "LIM-4001" in context.resolved_question

    def test_identifiers_are_carried_from_the_resolved_question(
        self, settings: Settings
    ):
        previous = turn(
            "Is it healthy?", resolved="Is it healthy? (regarding CardSecurityModule)"
        )
        context = resolve_follow_up("Why is that?", (previous,), settings)
        assert context.carried == ("CardSecurityModule",)

    def test_only_the_previous_turn_is_consulted(self, settings: Settings):
        earlier = (turn(LIM_QUESTION, number=1), turn(WITHDRAWAL, number=2))
        context = resolve_follow_up(
            "What should I check first on that?", earlier, settings
        )
        assert context.resolution == "carried_topic"
        assert "LIM-4001" not in context.resolved_question

    def test_carried_identifiers_are_capped(self, settings: Settings):
        previous = turn("Compare LIM-4001, LIM-4002, SWX-7001 and COR-5015.")
        context = resolve_follow_up("What do they mean?", (previous,), settings)
        assert context.carried == ("LIM-4001", "LIM-4002", "SWX-7001")
        assert len(context.carried) == MAX_CARRIED_IDENTIFIERS

    def test_the_earlier_answer_is_never_read(self, settings: Settings):
        context = resolve_follow_up(
            "What does it mean?", (turn(LIM_QUESTION),), settings
        )
        assert "earlier answer" not in context.resolved_question
        assert all("earlier answer" not in q for q in context.history)


class TestSubstitution:
    def test_what_about_swaps_a_component(self, settings: Settings):
        context = resolve_follow_up(
            "What about CardSecurityModule?",
            (turn("What version is CoreBankingAdapter running?"),),
            settings,
        )
        assert context.resolution == "substituted_identifier"
        expected = "What version is CardSecurityModule running?"
        assert context.resolved_question == expected

    def test_and_for_swaps_an_error_code(self, settings: Settings):
        context = resolve_follow_up(
            "And for LIM-4002?", (turn("What does LIM-4001 mean?"),), settings
        )
        assert context.resolved_question == "What does LIM-4002 mean?"

    def test_the_previous_question_is_matched_case_insensitively(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "How about CardSecurityModule?",
            (turn("what version is corebankingadapter running?"),),
            settings,
        )
        expected = "what version is CardSecurityModule running?"
        assert context.resolved_question == expected

    def test_a_different_kind_of_identifier_is_not_substituted(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "What about LIM-4001?",
            (turn("What version is CoreBankingAdapter running?"),),
            settings,
        )
        assert context.resolution == "standalone"

    def test_an_ambiguous_previous_question_is_not_substituted(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "What about PaymentEngine?",
            (turn("Is CoreBankingAdapter or CardSecurityModule healthy?"),),
            settings,
        )
        assert context.resolution == "standalone"


class TestCarriedTopic:
    def test_a_reference_with_no_identifiers_carries_the_topic(
        self, settings: Settings
    ):
        context = resolve_follow_up(
            "What should I check first on that?", (turn(WITHDRAWAL),), settings
        )
        assert context.resolution == "carried_topic"
        assert context.carried == ()
        assert WITHDRAWAL in context.resolved_question
        assert context.topic == WITHDRAWAL

    def test_a_chain_of_topic_follow_ups_does_not_grow(self, settings: Settings):
        first = resolve_follow_up(
            "What should I check first on that?", (turn(WITHDRAWAL),), settings
        )
        previous = turn(
            "What should I check first on that?",
            resolved=first.resolved_question,
            topic=first.topic,
            number=2,
        )
        second = resolve_follow_up("And why does that happen?", (previous,), settings)
        assert second.resolved_question.count(WITHDRAWAL) == 1
        assert second.topic == WITHDRAWAL


class TestHistoryLimits:
    def test_a_follow_up_gets_earlier_questions_as_asked_oldest_first(
        self, settings: Settings
    ):
        earlier = (
            turn(WITHDRAWAL, number=1),
            turn("Is it bad?", resolved="Is it bad? (following: x)", number=2),
            turn(LIM_QUESTION, number=3),
        )
        context = resolve_follow_up("What does it mean?", earlier, settings)
        assert context.history == (WITHDRAWAL, "Is it bad?", LIM_QUESTION)
        assert context.history_dropped == 0

    def test_the_window_bounds_how_many_turns_are_sent(self, settings: Settings):
        earlier = tuple(
            turn(f"Earlier question number {n}?", number=n) for n in range(1, 5)
        ) + (turn(LIM_QUESTION, number=5),)
        context = resolve_follow_up("What does it mean?", earlier, settings)
        assert len(context.history) == 3
        assert context.history[-1] == LIM_QUESTION

    def test_the_character_budget_drops_the_oldest_questions_whole(
        self, settings: Settings
    ):
        older = "An older question that is fairly long to push the budget over?"
        middle = "A middle question?"
        earlier = (
            turn(older, number=1),
            turn(middle, number=2),
            turn(LIM_QUESTION, number=3),
        )
        budget = len(middle) + len(LIM_QUESTION)
        tight = settings.model_copy(update={"conversation_max_history_chars": budget})
        context = resolve_follow_up("What does it mean?", earlier, tight)
        assert context.history == (middle, LIM_QUESTION)
        assert context.history_dropped == 1

    def test_a_budget_smaller_than_the_newest_question_sends_nothing(
        self, settings: Settings
    ):
        tight = settings.model_copy(update={"conversation_max_history_chars": 5})
        context = resolve_follow_up("What does it mean?", (turn(LIM_QUESTION),), tight)
        assert context.resolution == "carried_identifiers"
        assert context.history == ()
        assert context.history_dropped == 1

    def test_a_standalone_question_sends_no_history(self, settings: Settings):
        earlier = (turn(WITHDRAWAL, number=1), turn(LIM_QUESTION, number=2))
        context = resolve_follow_up(
            "What configuration controls transaction limits?", earlier, settings
        )
        assert context.history == ()
        assert context.history_dropped == 0
