# Banking Support Knowledge Agent

> Part of [ai-portfolio](../../README.md) · Personal project · **AI Security, Evaluation & Governance**

**In one line:** a support assistant for a made-up banking platform that cites every answer and says "I don't know" when it has no evidence.

## Why it matters

In a regulated setting, a confident wrong answer is worse than no answer. This agent answers only from its documents and live tools, and refuses otherwise.

## Key results

| | |
|---|---|
| Routing | Fixed rules pick one of five paths: documents, tools, both, refined search, or refuse |
| Retrieval | Local embeddings and a NumPy index; no vector database |
| Tools | Six support tools behind an MCP tool registry |
| Evaluation | 49 reviewed questions, including prompt-injection: recall@5 1.000 · MRR 0.927 · routing 0.959 |
| Safety | Injection defences; logs keep a hash of each question, never the text |
| Tests | 1,412 |

## The key decision

No evidence means no model call at all. The agent refuses before spending anything.

## Honest limits

- All banking data is synthetic (invented for this project)
- Not deployed
- Evaluation scores used real embeddings but a mock language model

## Run it

```bash
pip install -r requirements-dev.txt
python -m app.rag build      # build the search index
python -m app --reload       # web app on http://127.0.0.1:8000
```

`python -m app.eval` prints the evaluation scorecard (free, no API key).

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (all 15 stages, architecture, evaluation, security)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/banking-knowledge-agent) with the full commit history. This folder is the current version.
