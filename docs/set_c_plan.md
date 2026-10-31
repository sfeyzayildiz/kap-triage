# Set C: held-out test plan (written before sampling)

Date: 2026-11-01. Committed before Set C is sampled, labeled or run.

## Why
Set B is leaked for the code checks: `amount_is_projection` and `cumulative_total` were designed from its errors. Set C gives the combined system its first honest number.

## Sample (fixed)
- Script: `scripts/sample_set_c.py`, seed 20261101, 80 matched + 20 unmatched, same mix as Set B.
- Excluded by news_id: dev, eval_v1, Set A, the old label set, Set B.
- Also excluded: any disclosure whose normalized text equals an excluded one, so a repeated update cannot leak a seen text.
- Frozen file: `data/test_set_c.jsonl` (not in git), with `text_sha1` per row. Source: apitest.

## System under test (frozen)
- Prompt v3, `postprocess_v3`, `currency_unclear`, `amount_is_projection`, `cumulative_total`, `gemma4:e4b`, thinking default on.
- These are level 2 of `score_silent.py` and the checks in `scripts/pipeline.py`.
- No change to the prompt or checks from now until the result is recorded. `amount_checks.py` stays as it is, so the "ABD Doları" limitation is part of what is measured.

## Labeling
- Feyza labels blind with `scripts/label_set_b.py` under guidelines v1.3: text only, no Matriks values, no model output.
- Run `scripts/check_gold_amounts.py` on the finished gold, before the model run.
- A label is not changed after the model run. A typo found later is reported separately as post-hoc.

## Run and scoring
- One run, only after all 100 are labeled. No partial scoring.
- Commit first, then: `scripts/eval_vs_matriks.py --ids data/test_set_c.jsonl --prompt v3 --out data/eval_set_c.jsonl`, then `scripts/score_silent.py data/eval_set_c.jsonl --gold data/gold_set_c.jsonl`.
- Same scoring rules as Set B: gold `needs_review` rows are included, run errors count as flagged.

## Decision
- The number is level 2, `+projection+cumulative`.
- PASS: at most 1 silent error in 100 and a flag rate of at most 15%. Same limits as Set B.
- Report the one-sided 95% upper bound with the result.
- FAIL is reported as it is. No prompt or check is changed to rescue this number; a new version needs a new held-out set.

## RAG questions (optional, written while labeling)
- Feyza writes questions in `data/rag_questions_c.jsonl` under the same question guidelines.
- `ytu-ce-cosmos/turkish-e5-large` is measured once on them, with no change to the model or prefixes. Recall@5 and recall@1 are reported as the held-out retrieval number. No pass limit; these are not used to pick a model again.

## Honest limit
100 cases cannot show a very low error rate: 0/100 only says the rate is probably below about 3%. Texts are apitest data until prod texts are compared.
