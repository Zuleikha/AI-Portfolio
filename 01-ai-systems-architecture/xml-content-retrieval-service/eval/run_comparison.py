"""
Run the chunking comparison and print the report.

    python -m eval.run_comparison                      # DITA corpus
    python -m eval.run_comparison --data data/pmc      # JATS corpus
    python -m eval.run_comparison --json out.json

Free and offline: no API key, no network, no cost. (Building the JATS corpus in
the first place needs one free, unkeyed call to NCBI — see scripts/fetch_pmc.py.)

Each corpus has its own labelled question set, chosen automatically from the
vocabulary the data directory holds. Scoring a question set against the wrong
corpus would report zero recall for every strategy, which is a broken run and
not a finding, so an unrecognised corpus is an error rather than a default.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from app.dispatch import detect_vocabulary
from eval.chunkers import strategies
from eval.scoring import evaluate, paired_bootstrap

QUESTION_SETS = {
    "dita": Path(__file__).parent / "questions.yaml",
    "jats": Path(__file__).parent / "questions_pmc.yaml",
}
QUESTIONS = QUESTION_SETS["dita"]
COLUMNS = (
    "chunks",
    "mean_chunk_chars",
    "recall@1",
    "recall@3",
    "recall@5",
    "mrr",
    "chars_to_answer",
)


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]


def questions_for(data_dir: str) -> Path:
    """The labelled set belonging to whichever corpus ``data_dir`` holds."""
    vocabulary = detect_vocabulary(data_dir)
    if vocabulary not in QUESTION_SETS:
        raise ValueError(
            f"{data_dir}: no recognised corpus (expected DITA or JATS documents). "
            f"Build the PMC corpus with: python -m scripts.fetch_pmc"
        )
    return QUESTION_SETS[vocabulary]


def run(data_dir: str = "data", questions_path: Path | None = None) -> dict:
    questions = load_questions(questions_path or questions_for(data_dir))
    built = strategies(data_dir)
    results: dict[str, dict] = {}
    for mode, use_meta in (("text_only", False), ("text_plus_metadata", True)):
        results[mode] = {
            name: evaluate(chunks, questions, use_metadata=use_meta)
            for name, chunks in built.items()
        }
    return {"questions": len(questions), "results": results}


def _table(rows: dict[str, dict]) -> str:
    head = "| strategy | " + " | ".join(COLUMNS) + " |"
    sep = "|" + "---|" * (len(COLUMNS) + 1)
    lines = [head, sep]
    for name, r in rows.items():
        cells = [str(r.get(c, "")) for c in COLUMNS]
        label = f"**{name}**" if name == "structure-aware" else name
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _verdict(rows: dict[str, dict]) -> str:
    sa = rows["structure-aware"]
    naive = {k: v for k, v in rows.items() if k != "structure-aware"}
    # Compare against the BEST naive configuration, not a convenient one.
    best_name = max(naive, key=lambda n: (naive[n]["mrr"], naive[n]["recall@3"]))
    best = naive[best_name]
    d_mrr = sa["mrr"] - best["mrr"]
    d_r3 = sa["recall@3"] - best["recall@3"]
    boot = paired_bootstrap(sa["rr"], best["rr"])
    low, high = boot["ci95"]
    call = (
        "real at this sample size" if boot["excludes_zero"] else "NOT separable at this sample size"
    )
    return (
        f"best naive configuration: {best_name}\n"
        f"  MRR       structure-aware {sa['mrr']:.3f} vs naive {best['mrr']:.3f}  "
        f"({d_mrr:+.3f})\n"
        f"  recall@3  structure-aware {sa['recall@3']:.3f} vs naive {best['recall@3']:.3f}  "
        f"({d_r3:+.3f})\n"
        f"  chars to answer  {sa['chars_to_answer']} vs {best['chars_to_answer']}\n"
        f"  paired bootstrap on MRR, n={boot['n']}: "
        f"{boot['mean_difference']:+.3f} (95% CI {low:+.3f} to {high:+.3f}) — {call}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--questions", default=None, help="override the labelled set")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    out = run(args.data, Path(args.questions) if args.questions else None)
    print(f"\nChunking comparison — {out['questions']} labelled questions, BM25 retrieval")
    print(f"corpus: {args.data}\n")
    for mode, rows in out["results"].items():
        title = (
            "Body text only (isolates the chunk boundary)"
            if mode == "text_only"
            else ("Body text + authored metadata (how the service actually indexes)")
        )
        print(f"### {title}\n")
        print(_table(rows))
        print()
        print(_verdict(rows))
        print()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"written: {args.json_out}")


if __name__ == "__main__":
    main()
