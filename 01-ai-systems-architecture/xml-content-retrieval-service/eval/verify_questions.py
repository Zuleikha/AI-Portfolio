"""
Check a labelled question set against the corpus it claims to describe.

    python -m eval.verify_questions --data data
    python -m eval.verify_questions --data data/pmc --questions eval/questions_pmc.yaml

An evaluation is only worth the labels under it. This enforces the three
properties the question sets claim, and exits non-zero when one breaks:

1. **The span is present.** It occurs verbatim (whitespace-normalised) in the
   section the question names. A typo here silently drops recall for every
   strategy at once, which looks like a finding and is not.
2. **The span is unique.** It occurs in exactly one structure-aware chunk in the
   whole corpus. A span in two sections makes "the right chunk" ambiguous.
3. **The question is a paraphrase.** Content-word overlap between question and
   answer span is reported, so an accidental keyword echo is visible rather than
   flattering every strategy equally.

The PMC corpus is fetched live and gitignored, so this is the guard that stops a
stale question set being scored against a re-issued article.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.chunkers import structure_aware_chunks
from eval.scoring import _normalise, tokenize

# Words too common to count as an echo when they appear in both the question and
# the span. Overlap on "the" is not a leak; overlap on "clonidine" is.
STOPWORDS = frozenset(
    {
        # articles, prepositions and copulas
        "a", "an", "and", "are", "as", "at", "be", "been", "by", "during", "for",
        "from", "had", "has", "have", "in", "into", "is", "it", "its", "of", "on",
        "or", "over", "that", "the", "their", "there", "these", "this", "to",
        "was", "were", "with",
        # interrogatives and quantifiers — every question here opens with one
        "how", "many", "much", "what", "when", "where", "which", "who", "why",
        "did", "does", "do",
    }
)  # fmt: skip

ECHO_WARN_RATIO = 0.5


def content_words(text: str) -> set[str]:
    return {t for t in tokenize(text) if t not in STOPWORDS and not t.isdigit()}


def verify(chunks: list[dict], questions: list[dict]) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for a question set against a corpus."""
    errors: list[str] = []
    warnings: list[str] = []

    by_key = {(c["source_file"], c["section_id"]): c for c in chunks}

    for q in questions:
        key = (q["source_file"], q["section_id"])
        span = q["answer_span"]
        needle = _normalise(span)

        target = by_key.get(key)
        if target is None:
            errors.append(f"{q['id']}: no chunk {key[0]}/{key[1]} in the corpus")
            continue

        if needle not in _normalise(target["text"]):
            errors.append(f"{q['id']}: span not found in {key[0]}/{key[1]} — {span!r}")
            continue

        carriers = [c["chunk_id"] for c in chunks if needle in _normalise(c["text"])]
        if len(carriers) > 1:
            errors.append(
                f"{q['id']}: span occurs in {len(carriers)} chunks, not 1 "
                f"({', '.join(carriers[:4])}) — {span!r}"
            )

        q_words, s_words = content_words(q["question"]), content_words(span)
        if s_words:
            overlap = q_words & s_words
            ratio = len(overlap) / len(s_words)
            if ratio > ECHO_WARN_RATIO:
                warnings.append(
                    f"{q['id']}: question echoes {ratio:.0%} of the span's content words "
                    f"({', '.join(sorted(overlap))})"
                )

    ids = [q["id"] for q in questions]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        errors.append(f"duplicate question ids: {', '.join(sorted(duplicates))}")

    return errors, warnings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--questions", default=None)
    args = ap.parse_args()

    from eval.run_comparison import load_questions, questions_for

    path = Path(args.questions) if args.questions else questions_for(args.data)
    questions = load_questions(path)
    chunks = structure_aware_chunks(args.data)

    print(f"corpus:    {args.data} — {len(chunks)} structure-aware chunks")
    print(f"questions: {path} — {len(questions)} labelled\n")

    errors, warnings = verify(chunks, questions)

    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"FAIL  {error}")

    if errors:
        print(f"\n{len(errors)} problem(s). The question set does not describe this corpus.")
        sys.exit(1)
    print(f"\nOK — every span present, unique, and paraphrased ({len(warnings)} warning(s)).")


if __name__ == "__main__":
    main()
