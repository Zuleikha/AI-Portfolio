"""The agent reaching MCP: routing, wiring, and keeping the two evidence kinds apart.

``prompt.md`` §14 asks for two things beyond the tools themselves: the flow
*Agent → MCP → Tool → Result*, and a clear separation between knowledge retrieval
and live information. These tests are where both are asserted.

Everything here runs offline against the hashing embedder and the mock provider,
so nothing asserts retrieval *quality* — that stays in
``test_agent_integration.py``. What is asserted is behaviour: which route a
question takes, what reaches the prompt, what comes back on the record, and what
is allowed into a log line.
"""

from __future__ import annotations

import pytest

from app.agent.agent import KnowledgeAgent
from app.agent.models import AgentDecision, RetrievalDecision, ToolCallSummary
from app.agent.policy import decide
from app.agent.tool_policy import COMPONENT_NAMES, MAX_TOOL_CALLS, RuleToolSelector
from app.core.config import Settings
from app.llm.mock import MockLLMProvider
from app.llm.prompts import CONTEXT_OPEN, TOOL_CONTEXT_OPEN
from app.llm.service import LLMService
from app.mcp.base import ToolError
from app.mcp.models import ToolInvocation, ToolResult
from app.mcp.registry import ToolRegistry
from app.rag.retriever import Retriever

# --- Routing ---------------------------------------------------------------
#
# Stage 6 routed with a module function, select_tools(). Stage 7 replaced it with
# RuleToolSelector, built from the registry's specs (docs/HANDOVER.md 7.C). These
# tests kept their Stage 6 assertions and now reach them through the selector.


@pytest.fixture
def selector(tool_registry: ToolRegistry) -> RuleToolSelector:
    """The Stage 7 selector over all six tools."""
    return RuleToolSelector(tool_registry.specs())


class TestTheRoutingDecision:
    @pytest.mark.parametrize(
        ("question", "tool"),
        [
            ("What does LIM-4001 mean?", "look_up_error_code"),
            (
                "Status of TXN-20260911-004182?",
                "check_transaction_status",
            ),
            ("Is CoreBankingAdapter healthy?", "check_service_health"),
            ("What version is DeviceManager running?", "retrieve_system_version"),
            (
                "What is LimitService limits.atm.per_transaction_amount set to?",
                "get_system_configuration",
            ),
        ],
    )
    def test_an_identifier_selects_the_tool_that_can_act_on_it(
        self, selector: RuleToolSelector, question: str, tool: str
    ):
        assert tool in {invocation.tool for invocation in selector.select(question)}

    def test_a_plain_documentation_question_selects_no_tool(
        self, selector: RuleToolSelector
    ):
        assert selector.select("What component handles card authentication?") == ()

    def test_a_question_with_no_identifier_selects_no_tool(
        self, selector: RuleToolSelector
    ):
        assert selector.select("Why would an ATM transaction fail?") == ()

    def test_the_decision_records_that_tools_were_chosen(
        self, selector: RuleToolSelector
    ):
        decision = decide("What does LIM-4001 mean?", selector)
        assert decision.reason == "knowledge_and_live_status_required"
        assert decision.uses_tools

    def test_explaining_a_tool_reading_still_retrieves(
        self, selector: RuleToolSelector
    ):
        """An explanation needs documentation to interpret the reading."""
        assert decide("What does LIM-4001 mean?", selector).retrieve is True

    def test_a_documentation_question_keeps_the_stage_5_reason(
        self, selector: RuleToolSelector
    ):
        decision = decide("What component handles card authentication?", selector)
        assert decision.reason == "knowledge_required"
        assert decision.tools == ()

    def test_an_unsearchable_question_calls_nothing(self, selector: RuleToolSelector):
        decision = decide("!!! ???", selector)
        assert decision.reason == "no_searchable_content"
        assert decision.retrieve is False
        assert decision.tools == ()

    def test_a_blank_question_raises(self, selector: RuleToolSelector):
        with pytest.raises(ValueError):
            decide("   ", selector)

    def test_arguments_are_extracted_from_the_question(
        self, selector: RuleToolSelector
    ):
        invocation = selector.select("Why did TXN-20260911-004473 fail?")[0]
        assert invocation.arguments == {"transaction_reference": "TXN-20260911-004473"}

    def test_a_lowercase_reference_is_normalised(self, selector: RuleToolSelector):
        invocation = selector.select("check txn-20260911-004473 please")[0]
        assert invocation.arguments["transaction_reference"] == ("TXN-20260911-004473")

    def test_every_invocation_carries_a_displayable_reason(
        self, selector: RuleToolSelector
    ):
        for invocation in selector.select("Is CoreBankingAdapter healthy?"):
            assert invocation.reason.strip()

    def test_the_same_call_is_not_queued_twice(self, selector: RuleToolSelector):
        invocations = selector.select("LIM-4001 and LIM-4001 again")
        assert len(invocations) == 1

    def test_the_number_of_calls_is_capped(self, selector: RuleToolSelector):
        question = " ".join(f"LIM-400{n}" for n in range(1, 9))
        assert len(selector.select(question)) <= MAX_TOOL_CALLS

    def test_selection_is_deterministic(self, selector: RuleToolSelector):
        question = "Is CoreBankingAdapter healthy, and what does COR-5015 mean?"
        assert selector.select(question) == selector.select(question)

    def test_a_config_key_without_a_component_is_left_to_documentation(
        self, selector: RuleToolSelector
    ):
        """The tool needs both arguments; one alone is a documentation question."""
        assert selector.select("What does limits.atm.velocity_window_minutes do?") == ()

    def test_ordinary_prose_does_not_look_like_an_error_code(
        self, selector: RuleToolSelector
    ):
        assert selector.select("The ATM ate my card and I am cross") == ()

    def test_the_policy_component_list_matches_what_the_tools_accept(
        self, tool_registry: ToolRegistry
    ):
        """The policy must not offer a component no tool can resolve."""
        for component in COMPONENT_NAMES:
            assert tool_registry.call(
                "get_component_status", {"component": component}
            ).ok, component


# --- Agent -> MCP -> Tool -> Result ----------------------------------------


class TestTheAgentReachesTheTools:
    def test_a_tool_question_produces_a_tool_result(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert answer.tool_results
        assert answer.tool_results[0].tool == "look_up_error_code"

    def test_the_answer_reports_that_live_information_was_used(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert answer.used_live_information is True

    def test_a_documentation_question_uses_no_live_information(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("What component handles card authentication?")
        assert answer.used_live_information is False
        assert answer.tool_results == ()

    def test_the_tool_result_reaches_the_prompt(
        self, tool_agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        tool_agent.ask("What does error code LIM-4001 mean?")
        sent = mock_provider.calls[-1].user_text
        assert TOOL_CONTEXT_OPEN in sent
        assert "look_up_error_code" in sent

    def test_documentation_and_tool_results_occupy_separate_fences(
        self, tool_agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        """§14's separation requirement, asserted on the actual prompt."""
        tool_agent.ask("What does error code LIM-4001 mean?")
        sent = mock_provider.calls[-1].user_text
        assert CONTEXT_OPEN in sent
        assert TOOL_CONTEXT_OPEN in sent
        assert sent.index(CONTEXT_OPEN) < sent.index(TOOL_CONTEXT_OPEN)

    def test_one_question_is_one_tool_call(
        self, tool_agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert len(answer.tool_results) == 1
        assert mock_provider.call_count == 1

    def test_several_tools_can_answer_one_question(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("Is CoreBankingAdapter healthy?")
        assert {result.tool for result in answer.tool_results} == {
            "check_service_health",
            "get_component_status",
        }

    def test_the_agent_without_a_registry_is_unchanged(self, agent: KnowledgeAgent):
        """Stage 5's composition still answers documentation questions."""
        answer = agent.ask("What component handles card authentication?")
        assert answer.tool_results == ()
        assert answer.text


class TestTheExecutionRecord:
    def test_each_call_is_summarised(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert len(answer.tools) == len(answer.tool_results)
        assert isinstance(answer.tools[0], ToolCallSummary)

    def test_the_summary_records_argument_names_but_not_values(
        self, tool_agent: KnowledgeAgent
    ):
        """The security line: shape is loggable, identifiers are not."""
        answer = tool_agent.ask("Why did TXN-20260911-004473 fail?")
        summary = answer.tools[0]
        assert summary.arguments == ("transaction_reference",)
        assert "TXN-20260911-004473" not in summary.model_dump_json()

    def test_the_summary_carries_no_payload(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        body = answer.tools[0].model_dump_json()
        assert "daily_withdrawal_amount" not in body

    def test_the_full_result_is_returned_for_display(self, tool_agent: KnowledgeAgent):
        """Stage 9 must be able to render the tool result without re-calling."""
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert answer.tool_results[0].data["breached_configuration_key"]

    def test_a_not_found_is_recorded_as_a_call_that_happened(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("Status of TXN-19990101-000001?")
        assert answer.tools[0].ok is False
        assert answer.tools[0].error_code == "NOT_FOUND"

    def test_the_decision_is_recorded_with_its_invocations(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert isinstance(answer.decision, AgentDecision)
        assert answer.decision.tools[0].arguments["error_code"] == "LIM-4001"

    def test_tools_used_counts_what_reached_the_prompt(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("Is CoreBankingAdapter healthy?")
        assert answer.tools_used == len(answer.tool_results)

    def test_documentation_sources_do_not_include_tool_names(
        self, tool_agent: KnowledgeAgent
    ):
        """Sources are things a reader can open. A tool is not one."""
        answer = tool_agent.ask("What does error code LIM-4001 mean?")
        assert not any("look_up_error_code" in source for source in answer.sources)


class TestEvidenceAndRefusal:
    def test_a_tool_result_alone_is_enough_to_answer(
        self,
        rag_settings: Settings,
        llm_settings: Settings,
        tool_registry: ToolRegistry,
    ):
        """A successful tool call must prevent a refusal even with no passages.

        The index is built with a score floor nothing can clear, so retrieval is
        genuinely empty while the tool still answers. Before Stage 6 this
        question would have been refused.
        """
        from app.rag.pipeline import build_index

        starved = build_index(
            rag_settings.model_copy(update={"retrieval_min_score": 0.999}),
            persist=False,
        )
        provider = MockLLMProvider()
        agent = KnowledgeAgent(
            starved,
            LLMService(provider, llm_settings),
            llm_settings,
            tools=tool_registry,
        )
        answer = agent.ask("What does error code LIM-4001 mean?")
        assert answer.retrieval.chunks_returned == 0
        assert answer.tool_results
        assert not answer.refused
        assert provider.call_count == 1

    def test_no_evidence_of_either_kind_still_refuses(
        self, tool_agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        answer = tool_agent.ask("!!! ???")
        assert answer.refused
        assert answer.tool_results == ()
        assert mock_provider.call_count == 0

    def test_the_refusal_sentence_is_still_stage_4s(self, tool_agent: KnowledgeAgent):
        from app.llm.prompts import INSUFFICIENT_EVIDENCE

        assert tool_agent.ask("!!! ???").text == INSUFFICIENT_EVIDENCE


class TestFailuresPropagate:
    def test_a_broken_tool_raises_rather_than_answering_without_it(
        self,
        retriever: Retriever,
        llm_service: LLMService,
        llm_settings: Settings,
        tool_registry: ToolRegistry,
    ):
        """Silently dropping the live half would produce a confident half-answer."""

        class BrokenTool:
            def __init__(self, spec):  # type: ignore[no-untyped-def]
                self._spec = spec

            @property
            def spec(self):  # type: ignore[no-untyped-def]
                return self._spec

            def invoke(self, arguments):  # type: ignore[no-untyped-def]
                raise RuntimeError("the backing system fell over")

        broken = ToolRegistry()
        broken.register(BrokenTool(tool_registry.get("look_up_error_code").spec))
        agent = KnowledgeAgent(retriever, llm_service, llm_settings, tools=broken)
        with pytest.raises(ToolError):
            agent.ask("What does error code LIM-4001 mean?")

    def test_an_agent_without_a_registry_has_no_tools_to_select(
        self, agent: KnowledgeAgent
    ):
        """Stage 7 contract (docs/HANDOVER.md 7.C).

        Stage 6 raised here, because a registry-blind policy could select a tool
        the agent could not call. The Stage 7 selector is built *from* the
        registry, so an agent without one has nothing to select and answers from
        documentation, exactly as the Stage 5 composition always did.
        """
        answer = agent.ask("What does error code LIM-4001 mean?")
        assert answer.tool_results == ()

    def test_a_selector_without_a_registry_is_a_loud_composition_error(
        self,
        retriever: Retriever,
        llm_service: LLMService,
        llm_settings: Settings,
        tool_registry: ToolRegistry,
    ):
        """Selecting tools the agent cannot call is still never silent."""
        with pytest.raises(ValueError, match="registry"):
            KnowledgeAgent(
                retriever,
                llm_service,
                llm_settings,
                selector=RuleToolSelector(tool_registry.specs()),
            )


class TestBackwardsCompatibility:
    def test_the_stage_5_decision_name_still_resolves(self):
        assert RetrievalDecision is AgentDecision

    def test_the_stage_5_policy_name_still_works(self):
        from app.agent.policy import decide_retrieval

        assert decide_retrieval("What handles card authentication?").retrieve

    def test_a_decision_can_still_be_built_without_tools(self):
        decision = AgentDecision(
            retrieve=True, reason="knowledge_required", explanation="because"
        )
        assert decision.tools == ()
        assert not decision.uses_tools


class TestTheStage6Boundary:
    def test_the_agent_does_not_let_a_model_choose_tools(self):
        """Stage 7 decided: rules only, no model selector (docs/HANDOVER.md 7.B)."""
        import ast
        from pathlib import Path

        tree = ast.parse(Path("app/agent/tool_policy.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("app.llm")

    def test_the_mcp_package_imports_no_vendor_sdk_and_no_network(self):
        import ast
        from pathlib import Path

        forbidden = {"anthropic", "openai", "requests", "socket", "urllib"}
        package = Path("app/mcp")
        for path in sorted(package.rglob("*.py")):
            if path.name == "server.py":
                continue  # the protocol server legitimately uses the mcp SDK
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert not roots & forbidden, f"{path} imports {roots & forbidden}"

    def test_no_tool_module_reads_a_clock_or_the_filesystem(self):
        """Purity, asserted structurally rather than hoped for."""
        import ast
        from pathlib import Path

        forbidden = {"datetime", "time", "random", "pathlib", "os", "io"}
        for path in sorted(Path("app/mcp/tools").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert not roots & forbidden, f"{path.name} imports {roots & forbidden}"


class TestInvocationModel:
    def test_an_invocation_requires_a_reason(self):
        with pytest.raises(ValueError):
            ToolInvocation(tool="look_up_error_code", arguments={}, reason="")

    def test_an_unknown_tool_name_is_rejected_by_the_type(self):
        with pytest.raises(ValueError):
            ToolInvocation(
                tool="no_such_tool",  # type: ignore[arg-type]
                arguments={},
                reason="r",
            )

    def test_a_result_records_which_tool_produced_it(self, tool_registry: ToolRegistry):
        result = tool_registry.call("look_up_error_code", {"error_code": "LIM-4001"})
        assert isinstance(result, ToolResult)
        assert result.tool == "look_up_error_code"
