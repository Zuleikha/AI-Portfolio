# Menuforge

> Part of [ai-portfolio](../../README.md) · Personal project · **AI Systems & Architecture**

**In one line:** send a photo of a restaurant menu and get back clean, validated database records.

## Why it matters

Getting reliable structured data out of an AI model is hard. This forces the model to answer in a fixed format and checks every result before it is saved.

## Key results

| | |
|---|---|
| Extraction | One Claude call with forced tool use (no parsing of free-text JSON) |
| Validation | A Pydantic schema; a bad result is retried up to 2 times, then rejected |
| Storage | PostgreSQL |
| Security | Non-root container; API key from the environment only |
| Tests | 77, including an optional live test against the real API |

## The key decision

A result that fails validation is never stored. It is retried or rejected, so the database only ever holds data in the right shape.

## Honest limits

- A working prototype, not production-ready
- Right shape is not the same as right data: an invented item with a plausible price still passes
- Re-uploading a menu duplicates its rows; no login or rate limiting

## Run it

```bash
pip install -e ".[dev]"
uvicorn menuforge.main:app --reload
```

Needs Python 3.11+, PostgreSQL and an Anthropic API key. Step-by-step setup is in the full README.

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (setup, API, test layers, limitations)

🕘 **Development history:** first published here; there is no separate public repository.
