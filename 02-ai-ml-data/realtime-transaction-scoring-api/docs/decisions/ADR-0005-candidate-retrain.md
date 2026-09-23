# ADR-0005 — Retraining writes a candidate, never overwrites production

- **Status:** Accepted
- **Date:** recorded 2026-06-27

## Context

`src/train.py` reproduces the `bundle_v1` pipeline. A naive script that writes straight to
the production model path would let any run silently replace the live model — a serious
operational risk with no review step.

## Decision

`src/train.py` writes the trained model to `model.candidate_path`
(`outputs/models/retrain_candidate.pkl`), **never** into the serving bundle at
`outputs/models/bundle_v1/`. Promotion to production is a manual, reviewed step.
The candidate path is git-ignored so a candidate is never auto-committed.

## Consequences

- **+** The live model can only change through a deliberate human action.
- **+** Candidate and production models can be compared before promotion.
- **+** DagsHub/MLflow logging is opt-in (`TRACK_WITH_DAGSHUB=1`), so training works fully offline by default.
- **−** Promotion is manual: the candidate has to be validated, then the bundle refreshed with the new model, its threshold and its feature list together. Acceptable at this project's scale; a model registry with a promotion step is the improvement, tracked in [../../ROADMAP.md](../../ROADMAP.md).

## Note on numbering

This ADR was **0006** in the source project. It became 0005 when the ADR that documented
routing `/explain` through an external gateway was removed along with the endpoint itself —
that gateway was shared sandbox infrastructure, not part of this system. See
[../../DECISIONS.md](../../DECISIONS.md).
