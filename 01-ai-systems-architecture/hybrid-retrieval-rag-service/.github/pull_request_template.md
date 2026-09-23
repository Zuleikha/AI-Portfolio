## What changed

## Why

## Checklist

- [ ] `ruff check .` clean
- [ ] `ruff format --check .` clean
- [ ] `mypy src config` clean
- [ ] `pytest -q` green
- [ ] No new hardcoded config — new tunables added to `config/settings.py`
- [ ] No `print()` in `src/`
- [ ] Async paths stayed async
- [ ] ADR added under `docs/decisions/` if this reverses or replaces a decision
- [ ] `docs/` updated if behaviour or setup changed
