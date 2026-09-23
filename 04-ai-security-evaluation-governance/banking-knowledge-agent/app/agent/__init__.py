"""The knowledge agent: the component that owns a complete request.

Stage 5 joined the two halves built in isolation before it; Stage 6 gave it
tools; Stage 7 made it choose::

    question
       │
       ▼  policy       plan: knowledge? tools? both? nothing to search?
       │
       ├──▶ MCP tools   Stage 6 — selected by tool_policy.RuleToolSelector
       ├──▶ retriever   Stage 3 — and ONE refined second search when weak
       │
       ▼  LLMService   Stage 4 — budget, fence, generate, validate
       │
    AgentAnswer        answer + route + every choice point + retrieval + tools

Two properties are the point of this package:

**It adds a seam, not a layer of logic.** The retriever still has no LLM
dependency and the LLM service still does not retrieve. Every decision the agent
makes is a deterministic rule in :mod:`app.agent.policy` or
:mod:`app.agent.tool_policy`; :mod:`app.agent.agent` only carries them out.

**There is exactly one way to refuse.** A question the agent declines to search,
or searches and finds nothing for, is routed through Stage 4's existing
empty-evidence guard rather than getting a refusal of its own, so the
insufficient-evidence sentence has a single definition — the one the API, the
web interface and the evaluation harness all match against.
"""

from __future__ import annotations

from app.agent.agent import KnowledgeAgent
from app.agent.factory import get_agent
from app.agent.models import (
    AgentAnswer,
    AgentDecision,
    DecisionReason,
    DecisionStep,
    RetrievalDecision,
    RetrievalSummary,
)
from app.agent.policy import decide, decide_retrieval
from app.agent.tool_policy import RuleToolSelector, ToolSelector

__all__ = [
    "AgentAnswer",
    "AgentDecision",
    "DecisionReason",
    "DecisionStep",
    "KnowledgeAgent",
    "RetrievalDecision",
    "RetrievalSummary",
    "RuleToolSelector",
    "ToolSelector",
    "decide",
    "decide_retrieval",
    "get_agent",
]
