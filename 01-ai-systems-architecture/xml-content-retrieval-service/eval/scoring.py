"""
Retrieval and metrics for the chunking comparison.

Retrieval is **BM25 by default, and deliberately so**. The question under test is
whether chunk *boundaries* help, so the retrieval function is held constant across
strategies and only the chunking changes. BM25 is exact, deterministic, needs no
API key and costs nothing, which means anyone can reproduce this run — including a
reviewer with no accounts. A dense-embedding backend is available behind an
explicit opt-in for anyone who wants to confirm the effect survives a change of
retriever.

Relevance is judged by containment: a chunk is relevant to a question when it
contains that question's ``answer_span``. That rule is applied identically to both
strategies, and it is the property that a badly-placed boundary destroys.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class BM25:
    """Standard Okapi BM25 over a fixed corpus."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.n = len(self.docs)
        self.lengths = [len(d) for d in self.docs]
        self.avgdl = (sum(self.lengths) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in self.docs]
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        # +0.5/+0.5 smoothing keeps the idf of a term appearing in every document
        # positive rather than negative, which matters on a corpus this small.
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for i in range(self.n):
            tf, dl, s = self.tf[i], self.lengths[i], 0.0
            for term in q:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += self.idf.get(term, 0.0) * f * (self.k1 + 1) / denom
            out.append(s)
        return out


def paired_bootstrap(
    a: list[float],
    b: list[float],
    *,
    resamples: int = 10000,
    seed: int = 0,
) -> dict:
    """Confidence interval on the mean per-question difference ``a - b``.

    Two strategies are scored on the *same* questions, so the comparison is
    paired and the question set is the only thing being resampled. On a few
    dozen questions a headline gap of a few points routinely fails to clear
    zero, and reporting the gap without saying so would be the difference
    between a finding and a coincidence.

    Returns the mean difference, a 95% interval, and whether it excludes zero.
    """
    if len(a) != len(b):
        raise ValueError("paired comparison needs equal-length score lists")
    n = len(a)
    if n == 0:
        raise ValueError("no questions to compare")

    diffs = [x - y for x, y in zip(a, b, strict=True)]
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    low = means[int(0.025 * resamples)]
    high = means[min(int(0.975 * resamples), resamples - 1)]
    return {
        "mean_difference": round(sum(diffs) / n, 4),
        "ci95": (round(low, 4), round(high, 4)),
        "excludes_zero": low > 0 or high < 0,
        "n": n,
    }


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def is_relevant(chunk: dict, answer_span: str) -> bool:
    """True when the chunk actually carries the fact the question asks for."""
    return _normalise(answer_span) in _normalise(chunk["text"])


def searchable_text(chunk: dict, use_metadata: bool) -> str:
    """What the retriever indexes.

    With ``use_metadata`` the authored hierarchy (topic and section titles, tags)
    is indexed alongside the body — which is how the production service behaves.
    Without it, only the body text is indexed, isolating the effect of the chunk
    boundary alone.
    """
    if not use_metadata:
        return chunk["text"]
    return " ".join(
        [
            chunk.get("topic_title", ""),
            chunk.get("section_title", ""),
            chunk.get("tags", ""),
            chunk["text"],
        ]
    )


def evaluate(
    chunks: list[dict],
    questions: list[dict],
    ks: tuple[int, ...] = (1, 3, 5),
    *,
    use_metadata: bool,
) -> dict:
    """Run every question against one chunking strategy and score the result."""
    if not chunks:
        raise ValueError("no chunks to evaluate")

    bm25 = BM25([searchable_text(c, use_metadata) for c in chunks])
    max_k = max(ks)

    hits = {k: 0 for k in ks}
    rr_total = 0.0
    cost_total, cost_counted = 0, 0
    per_question_rr: list[float] = []

    for q in questions:
        scores = bm25.scores(q["question"])
        ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:max_k]

        first = None
        chars = 0
        for rank, idx in enumerate(ranked, start=1):
            chars += len(chunks[idx]["text"])
            if first is None and is_relevant(chunks[idx], q["answer_span"]):
                first = rank
                cost_total += chars
                cost_counted += 1
        per_question_rr.append(1.0 / first if first is not None else 0.0)
        if first is not None:
            rr_total += 1.0 / first
            for k in ks:
                if first <= k:
                    hits[k] += 1

    n = len(questions)
    return {
        "chunks": len(chunks),
        # Per-question reciprocal ranks, kept so two strategies can be compared
        # question-by-question rather than only as two summary numbers. A
        # difference in means says nothing about whether it would survive a
        # different sample of questions; see paired_bootstrap.
        "rr": per_question_rr,
        "mean_chunk_chars": round(sum(len(c["text"]) for c in chunks) / len(chunks), 1),
        "total_chars": sum(len(c["text"]) for c in chunks),
        **{f"recall@{k}": round(hits[k] / n, 3) for k in ks},
        "mrr": round(rr_total / n, 3),
        # Budget fairness: bigger chunks trivially contain more answers, so also
        # report how much text you must feed a model before reaching the answer.
        "chars_to_answer": round(cost_total / cost_counted, 1) if cost_counted else None,
    }
