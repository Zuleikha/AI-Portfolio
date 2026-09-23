# Candidate Ranking Service

> Part of [ai-portfolio](../../README.md) · Personal project · **AI/ML & Data**

**In one line:** ranks CVs against a job description and shows exactly why each one got its score.

## Why it matters

Hiring tools can hide unexplained or biased decisions. This one explains every score, and never makes the hire or reject call itself.

## Key results

| | |
|---|---|
| Scoring | Skills 50%, experience 30%, text similarity 20%, shown for every candidate |
| Output | Coarse A to D tiers, not falsely precise numbers |
| Fairness | Four-fifths rule, demographic parity, equal opportunity; only from group labels the user supplies |
| Privacy | Emails, phone numbers and links removed before scoring |
| Tests | 161 |

## The key decision

It **ranks; it does not decide.** No endpoint returns a hire/reject verdict or a pass mark.

## Honest limits

- Data is held in memory and lost on restart
- The API is open unless an API key is set; names are not redacted
- Not evaluated against real hiring outcomes

## Run it

```bash
pip install -e ".[dev]"
uvicorn src.api.main:app --reload
```

Then open http://localhost:8000/docs

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (scoring model, fairness metrics, API)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/candidate-ranking-service) with the full commit history. This folder is the current version.
