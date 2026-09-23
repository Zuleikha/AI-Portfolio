# ADR-0001 — LLM: Anthropic `claude-sonnet-4-6`

- Status: Accepted
- Date: 2026-06-27 (documenting existing code)

## Context

The generator must follow a strict citation format ("ground every claim, cite
inline with `[1]`, `[2]`, never fabricate"). Reliability of instruction-following
matters more than raw breadth here.

## Decision

Use Anthropic **`claude-sonnet-4-6`** as the generation model
(`config/settings.py: llm_model`). Implemented in `src/rag/generator.py` with the
`anthropic.AsyncAnthropic` client. Generation params: `temperature=0.1`,
`max_tokens=1024`.

The system prompt is passed via Anthropic's separate `system` parameter (not as
the first message), and context blocks are numbered so inline citations map to
specific chunks.

## Consequences

- ✅ Strong, reliable adherence to the citation format.
- ✅ Good speed/cost balance for query traffic.
- ➖ Requires `ANTHROPIC_API_KEY`; the app fails fast at startup if it's missing.
- ➖ External dependency — no offline generation fallback.

## Supersedes

The earlier iteration used OpenAI `gpt-4o-mini` (still referenced in the README
"What changed from v1" table and historical docs). That choice has been replaced
by this ADR.
