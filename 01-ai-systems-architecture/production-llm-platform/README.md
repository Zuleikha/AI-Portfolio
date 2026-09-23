# Production-Grade LLM Platform

> Part of [ai-portfolio](../../README.md) · Personal project · **AI Systems & Architecture**

**In one line:** an LLM chat platform built in ten stages, each adding one real production concern.

## Why it matters

Most LLM demos stop at "it answers". This one adds what a real service needs: grounded answers with citations, monitoring, quality checks in CI, security and reliability.

## Key results

| | |
|---|---|
| Agent | LangGraph agent loop on the Anthropic API |
| Grounding | RAG over Qdrant (Voyage embeddings); answers return typed citations |
| Quality gate | Retrieval quality is scored in CI; a drop fails the build |
| Monitoring | OpenTelemetry traces, Prometheus metrics, Grafana dashboards and alerts |
| Deployment | Docker Compose; Kubernetes via Helm (tested on kind); Terraform for AWS |
| Safety | API keys, rate limiting, prompt-injection guardrails, circuit breaker |
| Tests | 409; the suite can never call a paid API |

## The key decision

Every stage has an architecture decision record (ADR) and a verification log, so each choice can be traced and checked.

## Honest limits

- Not hosted: the demo is real captured output, not a live URL
- Terraform is validated but has never been applied to AWS
- Built and tested locally, not run at production scale

## Run it

```bash
uv sync
docker compose up -d --build
```

Then open http://localhost:8000/docs (needs Python 3.12, uv and Docker).

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (all 10 stages, setup, services, ADRs)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/production-llm-platform) with the full commit history. This folder is the current version.
