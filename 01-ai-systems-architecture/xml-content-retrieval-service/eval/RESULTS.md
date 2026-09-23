# Chunking comparison — results

**Question:** does deriving chunk boundaries from authored markup retrieve better
than deriving them from a character budget?

**Reproduce:**

```bash
python -m eval.run_comparison                     # DITA corpus  (ships in repo)
python -m scripts.fetch_pmc --limit 30            # build the JATS corpus (free, no API key)
python -m eval.run_comparison --data data/pmc     # JATS corpus
python -m eval.verify_questions --data data/pmc   # check the labels first
```

Free, offline and deterministic once the corpus exists. No API key, no cost.

| Run | Corpus | Documents | Chunks | Questions |
|---|---|---|---|---|
| **A — DITA** | Authored technical documentation | 3 | 12 | 22 |
| **B — JATS** | PubMed Central research articles | 30 | 656 | 38 |

---

## Headline

> **Structure-aware chunking is not more accurate than a well-tuned fixed-size
> window. Its defensible advantages are context cost and usable metadata.**
>
> Run A (small corpus) suggested this and blamed the corpus. **Run B was built
> to test that excuse, and refutes it.** On 30 full research articles — where a
> large window is 6% of a document, not half of one — a 2400-character window
> still matches structure-aware chunking on every accuracy measure.
>
> Against **small or badly-tuned** windows, structure-aware wins clearly and the
> difference survives a significance test. Against a **well-tuned** window, at
> these sample sizes, **the difference is not statistically separable from zero.**

---

## Run A — DITA corpus (22 questions, 12 chunks)

### Body text + authored metadata (how the service actually indexes)

| strategy | chunks | mean chars | recall@1 | recall@3 | recall@5 | MRR | chars to answer |
|---|---|---|---|---|---|---|---|
| **structure-aware** | 12 | 306 | **0.500** | 0.773 | 0.909 | 0.653 | **576** |
| naive-150c-o0 | 31 | 138 | 0.182 | 0.364 | 0.455 | 0.288 | 297 |
| naive-150c-o50 | 43 | 146 | 0.273 | 0.591 | 0.682 | 0.422 | 318 |
| naive-300c-o0 | 16 | 267 | 0.182 | 0.636 | 0.682 | 0.403 | 587 |
| naive-300c-o50 | 18 | 279 | 0.409 | 0.727 | 0.818 | 0.558 | 563 |
| naive-600c-o0 | 9 | 475 | 0.409 | 0.864 | **1.000** | **0.668** | 994 |
| naive-600c-o50 | 9 | 508 | 0.409 | **0.909** | 0.955 | 0.640 | 994 |

Best naive = `naive-600c-o0`. MRR **0.653 vs 0.668** (−0.015).
Paired bootstrap on MRR, n=22: **−0.015, 95% CI −0.149 to +0.116 — not separable.**

*(body-text-only table and the full sweep are in `results.json`)*

---

## Run B — JATS / PMC corpus (38 questions, 656 chunks)

### Body text + authored metadata

| strategy | chunks | mean chars | recall@1 | recall@3 | recall@5 | MRR | chars to answer |
|---|---|---|---|---|---|---|---|
| **structure-aware** | 656 | 1788 | 0.474 | 0.684 | **0.868** | 0.611 | 3786 |
| naive-300c-o0 | 4027 | 298 | 0.342 | 0.447 | 0.553 | 0.403 | **628** |
| naive-300c-o50 | 4819 | 299 | 0.447 | 0.605 | 0.711 | 0.536 | 566 |
| naive-600c-o0 | 2019 | 596 | 0.395 | 0.553 | 0.711 | 0.497 | 1244 |
| naive-600c-o50 | 2200 | 596 | 0.447 | 0.684 | 0.737 | 0.556 | 1050 |
| naive-1200c-o0 | 1015 | 1185 | 0.395 | 0.658 | 0.763 | 0.531 | 2400 |
| naive-1200c-o50 | 1059 | 1184 | 0.447 | **0.711** | 0.816 | 0.581 | 2322 |
| naive-2400c-o0 | 514 | 2340 | 0.447 | **0.711** | 0.789 | 0.584 | 4239 |
| naive-2400c-o50 | 527 | 2329 | **0.526** | **0.711** | 0.842 | **0.646** | 4188 |

Best naive = `naive-2400c-o50`. MRR **0.611 vs 0.646** (−0.035).
Paired bootstrap on MRR, n=38: **−0.035, 95% CI −0.145 to +0.073 — not separable.**

### Every pairwise comparison, with its uncertainty

Structure-aware minus each naive configuration, MRR, metadata mode, n=38:

| comparison | Δ MRR | 95% CI | verdict |
|---|---|---|---|
| vs naive-300c-o0 | **+0.208** | +0.041 to +0.371 | ✅ **separable — structure-aware wins** |
| vs naive-600c-o0 | +0.113 | −0.026 to +0.255 | not separable |
| vs naive-1200c-o0 | +0.079 | −0.050 to +0.206 | not separable |
| vs naive-300c-o50 | +0.075 | −0.047 to +0.206 | not separable |
| vs naive-600c-o50 | +0.055 | −0.071 to +0.184 | not separable |
| vs naive-1200c-o50 | +0.030 | −0.085 to +0.146 | not separable |
| vs naive-2400c-o0 | +0.026 | −0.078 to +0.129 | not separable |
| vs naive-2400c-o50 | −0.035 | −0.145 to +0.073 | not separable |

**Exactly one comparison clears zero**, and it is against the worst configuration
in the sweep. Every headline gap quoted anywhere else in this document is inside
its own confidence interval.

---

## What the numbers actually say

**1. Structure-aware beats badly-tuned windows, and that result is real.**
Against `naive-300c-o0` it gains **+0.208 MRR (CI +0.041 to +0.371)**. If the
alternative is a splitter dropped in at a default window size with no overlap and
no tuning, authored boundaries are a genuine improvement.

**2. Against a well-tuned window it is a tie, and the corpus excuse is gone.**
Run A blamed its 3,673-character corpus: a 600-char window was half a document,
so the baseline was effectively "retrieve the whole document". Run B removes that
objection — articles average ~39,000 characters, so a 2400-char window is **~6% of
a document**. The large window still matches. The prediction Run A made
("the large-window baseline should degrade") **did not survive contact with a
realistic corpus, and is withdrawn.**

**3. The context-cost advantage is real on DITA and much weaker on JATS.**

| | DITA | JATS |
|---|---|---|
| structure-aware chars to answer | **576** | 3786 |
| best naive chars to answer | 994 | 4188 |
| saving | **42%** | **10%** |

The 42% figure was the strongest claim in Run A. It does **not** generalise: on
real articles the saving against the best naive window is ~10%. Against
*comparably-sized* windows (1200c) structure-aware still reaches the answer in
less text while scoring higher, but the headline "40% less context" belongs to
the DITA corpus only and should not be quoted as a general result.

**4. Authored metadata helps, but not separably at this sample size.**
Indexing titles and tags lifts structure-aware recall@5 from 0.789 → **0.868** and
MRR 0.571 → 0.611 on JATS. The direction is consistent across both corpora and
across window sizes, and metadata *hurts* the smallest naive windows (−0.024),
which is what you would expect when the only metadata available is a document
title repeated across thousands of fragments. But the paired bootstrap on the
structure-aware gain gives **+0.040, CI −0.029 to +0.118 — not separable.**
Run A's claim that this is "the part of the thesis the data supports most cleanly"
was **overstated**: it was never significance-tested.

**5. The one thing windows cannot do at all.**
A fixed-size window has no section to name. Structure-aware chunks carry
`section_path` (e.g. `Methods > Analysis > Software`), `section_depth`,
`section_title` and `topic_id`. That is filterable, displayable, citable metadata —
"which section did this come from?" is answerable for one strategy and not the
other, at any corpus size. This is an **architectural** property, not a retrieval
score, and it is the claim that does not depend on any of the numbers above.

---

## ⚠️ Limits — what would have to change to settle this

| Limit | Effect | Fix |
|---|---|---|
| **38 and 22 questions** | The dominant limitation. Nearly every interesting gap is inside its CI. Separating a 0.03–0.05 MRR difference needs several hundred questions | Expand the labelled sets |
| BM25, not dense retrieval | Production uses embeddings; lexical overlap may favour different boundaries | Re-run behind the dense opt-in |
| Containment-based relevance | A chunk that *implies* the answer without the literal span scores as a miss | Multi-span or judged relevance |
| Questions written by the author who read the corpus | Risk of vocabulary leakage in either direction | `verify_questions.py` enforces span uniqueness and flags echoes, but cannot substitute for independent authors |
| One topical slice of PMC | 30 clinical-trial-flavoured articles; results may not transfer to other JATS content | Sweep several queries |

**Calibration note on Run A.** The DITA numbers in this document differ slightly
from the first published version, because `verify_questions.py` — added for Run B —
found a defect in the DITA question set: `q04`'s answer span occurred in **two**
sections, making "the right chunk" ambiguous and inflating recall. Two further
questions echoed their own answer spans. All three were fixed and Run A re-run.
The conclusions did not change direction; the margins narrowed.

---

## What should change as a result

1. **Restate the project's claim.** Supported: *authored section boundaries match
   a tuned fixed-size window on retrieval accuracy, beat an untuned one, and
   preserve document hierarchy as filterable metadata that a splitter discards.*
   Not supported: "better retrieval", or "~40% less context" as a general figure.
2. **Expand the labelled sets** before quoting any gap under ~0.10 MRR. This is
   the single highest-value next step and it is cheap.
3. **Re-run under dense retrieval** to confirm none of this is a BM25 artefact.
4. **Keep the retrieval stack plain.** Nothing here argues for reranking; that
   remains the sibling project's job.
