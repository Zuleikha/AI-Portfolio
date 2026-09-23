"""Stage 11 evaluation: score the agent against a fixed, reviewed question set.

::

    data/eval/questions.yaml ──▶ dataset.load_dataset()   validated expectations
                                     │
    agent + retriever ──────────────▶ runner.run_evaluation()
                                     │   per question: retrieval ranks, the answer,
                                     │   metrics.check_answer() rule checks
                                     ▼
                                 EvalReport ──▶ report.render_report()  (CLI)
                                            └─▶ failed_floors()         (pytest gates)

One engine, two callers (``docs/HANDOVER.md`` 11.D): pytest gates on it and
``python -m app.eval`` prints it. Free by default; ``--paid`` is opt-in (11.B).
"""
