"""
Grounded answer generation using Claude (claude-sonnet-4-6).

Why Claude:
- Strong instruction following: the citation-format prompt is obeyed reliably
- Good speed / cost balance for production query traffic

Prompt design:
- System prompt enforces grounding rules upfront, passed via the Anthropic
  `system` parameter (separate from the message list)
- Context is numbered so inline citations ([1], [2]) can reference specific chunks
- Conversation history is truncated to the last 3 turns to bound prompt size
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from config.settings import settings
from src.rag.retriever import RetrievedDocument

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    answer: str
    sources: list[dict]
    tokens_used: int
    latency_ms: float
    model: str


# Assembled with implicit concatenation so the source stays inside the line
# limit without altering a single character of the prompt the model receives.
_SYSTEM_PROMPT = (
    "You are a precise, helpful assistant. Answer the user's question using ONLY"
    " the provided context blocks.\n"
    "\n"
    "Rules:\n"
    "1. Ground every claim in the context. If the context does not contain enough"
    " information to answer, say so clearly — do not guess.\n"
    "2. Cite sources inline using [1], [2], etc., where the number corresponds to"
    " the numbered context block.\n"
    "3. Be concise. Prefer short, clear sentences.\n"
    "4. Never fabricate information that is not present in the context.\n"
)


class RAGGenerator:
    def __init__(self) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.llm_model

    async def generate(
        self,
        query: str,
        context_docs: list[RetrievedDocument],
        conversation_history: list[dict] | None = None,
    ) -> GenerationResult:
        context_text = self._format_context(context_docs)
        messages = self._build_messages(query, context_text, conversation_history)

        # Anthropic takes the system prompt as a separate parameter, not as the
        # first message; everything after it is the user/assistant turn list.
        system_prompt = messages[0]["content"]
        conversation = messages[1:]

        t0 = time.perf_counter()
        answer, tokens_used = await self._call_anthropic(system_prompt, conversation)
        latency_ms = (time.perf_counter() - t0) * 1000

        return GenerationResult(
            answer=answer,
            sources=[
                {
                    "content": d.content[:300],
                    "metadata": d.metadata,
                    "score": round(d.score, 4),
                }
                for d in context_docs
            ],
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            model=self._model,
        )

    # ── Backend ──────────────────────────────────────────────────────────────

    async def _call_anthropic(
        self, system_prompt: str, conversation: list[dict]
    ) -> tuple[str, int]:
        """Generate via the Anthropic Messages API; returns (answer, tokens_used)."""
        response = await self._client.messages.create(
            model=self._model,
            system=system_prompt,
            messages=conversation,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        answer = "".join(block.text for block in response.content if block.type == "text")
        tokens_used = (
            response.usage.input_tokens + response.usage.output_tokens if response.usage else 0
        )
        return answer, tokens_used

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_context(self, docs: list[RetrievedDocument]) -> str:
        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "unknown")
            parts.append(f"[{i}] Source: {source}\n{doc.content}")
        return "\n\n".join(parts)

    def _build_messages(
        self,
        query: str,
        context: str,
        history: list[dict] | None,
    ) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Last 3 turns (6 messages) keeps context focused without ballooning tokens
        if history:
            messages.extend(history[-6:])

        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {query}",
            }
        )
        return messages
