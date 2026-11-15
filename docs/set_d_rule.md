# Set D: two-run disagreement flag and amount_checks v2 (rule, written before sampling)

Date: 2026-11-15. Committed before any code, sample, label or run. One labeled set answers two questions.

## Why
1. **Two-run disagreement flag (T).** The repeatability run (14 Nov) changed (amount, currency) on 3/100 Set C items, and both silent errors (run 1: 6060372, run 2: 6041099) were among those 3. Hypothesis: "two extractions disagree → `needs_review`" catches silent errors cheaply. Seen post-hoc on Set C, so it needs new data.
2. **amount_checks v2 (V).** Known issue B5: `MONEY_RE` does not read "ABD Doları" / "Amerikan Doları" (the word "ABD" sits between the number and "Dolar"), so `cumulative_total` cannot see USD amounts written that way. v1 stays frozen; v2 is a new file.

What v2 can change (checked in code before this rule, counts only): `money_values` is used by the pipeline only inside `cumulative_total`, which fires only when cumulative wording is present. In the Set D pool (below) 136 texts contain "ABD/Amerikan Doları" and only **12** of them also contain cumulative wording. v2 can change a flag only on those 12; adding values can only raise the largest amount, so v2 can only add flags, never remove one.

## Sample (fixed)
- Script `scripts/sample_set_d.py`, seed **20261115**, output `data/test_set_d.jsonl` (not in git, `text_sha1` per row, refuses to overwrite).
- Pool: disclosures with text published before 2026-11-15 (the forward-test lists start that day), excluding by news_id dev, eval_v1, Set A, the old label set, Set B, Set C, the 40 drift ids, importance rounds 1 and 2; also excluding any text equal (normalized) to an excluded one, and duplicate texts inside the pool. Pool at rule time: 736.
- Strata: **U** = every pool text with "ABD/Amerikan Doları" and cumulative wording (`amount_checks.CUMULATIVE`), all of them (12 at rule time; if more than 15, a seeded 15); **R** = a seeded random draw from the rest of the pool so that U + R = 50. Shuffled together, so the labeler does not know the stratum.

## Labeling (Feyza, blind)
- `scripts/label_set_b.py --set-d`, guidelines v1.3 (same as Set C), text only, no Matriks value, no model output, no RAG question.
- Then `scripts/check_gold_amounts.py data/gold_set_d.jsonl` before any run. Labels are not changed after a run; a typo found later is reported separately as post-hoc.

## System under test (frozen at the commit of the runs)
The live pipeline as the morning list runs it: `pipeline.analyze` (prompt v3, `gemma4:e4b`, thinking on, code checks, Matriks cross-check) + `judge_pass` (source check).

## Runs (Feyza, after all 50 are labeled)
- `scripts/set_d.py --run a`, then `scripts/set_d.py --run b`: two **separate processes**, same commit, not 23:40-23:50, each about 15-25 min. Each row stores amount, currency, flag reasons, error, seconds.
- No scoring until both runs have 50 rows (`--score` refuses otherwise).

## Measures (scored once, `scripts/set_d.py --score`)
Silent error = not flagged and (amount, currency) differs from gold (`score_silent.compare`); gold `needs_review` rows included; run errors count as flagged. "Disagree" = (amount, currency) of run a ≠ run b after currency normalisation (`repeat_check.key`).
- **S (report):** silent errors and flag rate of run a and of run b, overall and per stratum, with one-sided 95% upper bounds.
- **T1 cost:** items that disagree and are not flagged in run a (new flags from T).
- **T2 benefit:** silent errors of run a that disagree (caught) vs. that do not (missed). Same numbers with run b as the base, reported.
- **T3 latency:** median of (seconds a + seconds b) per item.
- **V1 new flags:** items where v2's `cumulative_total` flags and run a had no flag; split into **catches** (run a's answer is wrong vs. gold) and **false alarms** (run a's answer is right).
- **V report only:** v2 applied to the Set C run 1 and run 2 outputs (gold exists, no LLM call): new flags, catches, false alarms. No decision from it.

## Decision (fixed now)
- **T:** `ADOPT_TWO_RUN` if T1 ≤ 3/50 **and** caught ≥ missed **and** T3 ≤ 60 s; else `TWO_RUN_OFF`. If run a has no silent error, the result line says "benefit not observed on Set D" and the evidence for the benefit stays the Set C observation (stated in the docs as such).
- **V:** `ADOPT_V2` if false alarms ≤ 1; else `V2_OFF`. Catches are reported; 0 catches with ≤ 1 false alarm still adopts (v2 repairs a parser gap and cannot remove a flag), and the docs say the benefit was not observed.
- Wiring if adopted: T only in the nightly morning list (batch, second extraction per disclosure; interactive card and brief stay single-run because of latency); V replaces v1's `cumulative_total` in `pipeline.apply_checks` through `amount_checks_v2.py` (v1 file unchanged). Headline Set C numbers stay as measured; Set D numbers are reported next to them.

## Note 1 (before sampling, descriptive only)
The pool count 736 above was counted without removing duplicate texts inside the pool; with the dedup this rule already prescribes, the sampler's dry run gives **732** (zone U still 12). No definition or decision changes.

## Honest limits
- 50 items, one labeler. With about 1 silent error per 100, Set D will most likely show 0-1 silent errors, so T's benefit is barely testable here; T is mainly a cost measurement.
- U is a census of v2's whole effect zone in this pool, but only 12 items; the R stratum carries no information about v2 by construction.
- Run b in a separate process repeats the conditions under which the Set C disagreement was seen; it is not a test of more than two runs (majority vote would need its own rule).
