"""Unit tests for RAGGenerator — context formatting, message building, and generate()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.generator import GenerationResult, RAGGenerator
from src.rag.retriever import RetrievedDocument


def _doc(content: str, source: str = "doc.txt", score: float = 0.9) -> RetrievedDocument:
    return RetrievedDocument(
        content=content,
        metadata={"source": source},
        score=score,
        retrieval_method="hybrid",
    )


@pytest.fixture
def generator():
    with patch("src.rag.generator.AsyncAnthropic"):
        return RAGGenerator()


def _anthropic_response(text: str, input_tokens: int = 0, output_tokens: int = 0):
    """Build a mock Anthropic Messages response (content blocks + split usage)."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


# ── _format_context ───────────────────────────────────────────────────────────


class TestFormatContext:
    def test_empty_docs_produce_empty_string(self, generator):
        assert generator._format_context([]) == ""

    def test_single_doc_is_numbered_one(self, generator):
        result = generator._format_context([_doc("Paris is the capital.", "geo.txt")])
        assert "[1] Source: geo.txt" in result
        assert "Paris is the capital." in result

    def test_multiple_docs_are_numbered_sequentially(self, generator):
        docs = [_doc("Content A", "a.txt"), _doc("Content B", "b.txt")]
        result = generator._format_context(docs)
        assert "[1] Source: a.txt" in result
        assert "[2] Source: b.txt" in result

    def test_missing_source_falls_back_to_unknown(self, generator):
        doc = RetrievedDocument(content="text", metadata={}, score=0.5, retrieval_method="hybrid")
        result = generator._format_context([doc])
        assert "unknown" in result

    def test_docs_are_separated_by_double_newline(self, generator):
        docs = [_doc("First."), _doc("Second.")]
        result = generator._format_context(docs)
        assert "\n\n" in result


# ── _build_messages ───────────────────────────────────────────────────────────


class TestBuildMessages:
    def test_first_message_is_always_system(self, generator):
        msgs = generator._build_messages("q", "ctx", None)
        assert msgs[0]["role"] == "system"

    def test_last_message_is_always_user(self, generator):
        msgs = generator._build_messages("q", "ctx", None)
        assert msgs[-1]["role"] == "user"

    def test_user_message_contains_context_and_question(self, generator):
        msgs = generator._build_messages("What is X?", "Context about X.", None)
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "What is X?" in user_msg["content"]
        assert "Context about X." in user_msg["content"]

    def test_no_history_produces_exactly_two_messages(self, generator):
        msgs = generator._build_messages("q", "ctx", None)
        assert len(msgs) == 2

    def test_short_history_is_fully_included(self, generator):
        history = [
            {"role": "user", "content": "prev q"},
            {"role": "assistant", "content": "prev a"},
        ]
        msgs = generator._build_messages("follow-up", "ctx", history)
        assert len(msgs) == 4  # system + 2 history + user

    def test_long_history_is_capped_at_six_messages(self, generator):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(20)
        ]
        msgs = generator._build_messages("q", "ctx", history)
        # system (1) + at most 6 history + user (1) = at most 8
        assert len(msgs) <= 8

    def test_empty_history_list_is_treated_as_no_history(self, generator):
        msgs = generator._build_messages("q", "ctx", [])
        assert len(msgs) == 2


# ── generate() ────────────────────────────────────────────────────────────────


class TestGenerateMethod:
    @pytest.mark.asyncio
    async def test_generate_returns_generation_result(self):
        mock_response = _anthropic_response("The answer is 42.", input_tokens=60, output_tokens=40)

        with patch("src.rag.generator.AsyncAnthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            gen = RAGGenerator()

        result = await gen.generate("What is the answer?", [_doc("Relevant context.")])

        assert isinstance(result, GenerationResult)
        assert result.answer == "The answer is 42."
        assert result.tokens_used == 100  # input + output
        assert result.latency_ms >= 0.0

    @pytest.mark.asyncio
    async def test_generate_populates_sources_from_context_docs(self):
        mock_response = _anthropic_response(
            "Answer with citation [1].", input_tokens=30, output_tokens=20
        )

        with patch("src.rag.generator.AsyncAnthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            gen = RAGGenerator()

        docs = [_doc("Source text.", "source.pdf", score=0.85)]
        result = await gen.generate("question", docs)

        assert len(result.sources) == 1
        assert result.sources[0]["score"] == pytest.approx(0.85, abs=0.001)
        assert result.sources[0]["metadata"]["source"] == "source.pdf"

    @pytest.mark.asyncio
    async def test_generate_includes_model_name_in_result(self):
        mock_response = _anthropic_response("Answer.", input_tokens=10, output_tokens=10)

        with patch("src.rag.generator.AsyncAnthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            gen = RAGGenerator()

        result = await gen.generate("q", [_doc("ctx.")])
        assert result.model  # non-empty string

    @pytest.mark.asyncio
    async def test_generate_with_no_usage_returns_zero_tokens(self):
        mock_response = _anthropic_response("Response.")
        mock_response.usage = None

        with patch("src.rag.generator.AsyncAnthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            gen = RAGGenerator()

        result = await gen.generate("q", [_doc("ctx.")])
        assert result.tokens_used == 0
