## What changed

## Why

## Checklist

- [ ] `ruff check .` clean
- [ ] `ruff format --check .` clean
- [ ] `pytest -q` green
- [ ] New Dagster assets added to `all_assets`
- [ ] No new hardcoded config — deployment values in `src/config.py`, hyperparameters in `config/pipeline.yaml`
- [ ] No `print()` in `src/`
- [ ] No model bundles, datasets or `mlruns/` added to git
- [ ] `docs/DECISIONS.md` updated if this reverses a recorded decision
- [ ] `docs/` updated if behaviour or setup changed
