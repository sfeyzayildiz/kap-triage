# Regex baseline on Set C: "could it be done without an LLM?" (rule written before the run)

Date: 2026-11-11. Committed before any baseline output on Set C exists. Report only: nothing in the system changes.

## Why
The only number behind "regex was not enough" is 12/15 vs 15/15 on the 15 manual samples (October), and the prompt was tuned on those samples. Set C has 100 frozen gold labels that the live system was measured on once (1/100 silent, 11/100 flagged). Scoring a regex extractor on the same gold gives the LLM-free number on held-out data.

## Baselines (fixed now, both already in the repo, not edited for this run)
- **A. October regex** (`scripts/baseline.py: extract`, unchanged since the 15-sample baseline): first `number + currency word` match in the text; currencies USD / EUR / TRY only.
- **B. Money regex** (`scripts/amount_checks.py: money_values`, frozen): first number written next to a currency (TL, USD, EUR, GBP, symbols, scale words). The strongest regex we have, written for the code checks, not for extraction.
- Neither has a flag of its own, so every error is silent. A third level is reported with the frozen code checks on top (`score_silent.py` levels: `currency_unclear`, `amount_is_projection`, `cumulative_total`), which is the best LLM-free system this repo could build: regex + code checks.

## Measurement
- `scripts/regex_baseline.py --run`: Set C texts (ids from `data/gold_set_c.jsonl`, texts from the DB) → `data/eval_regex_a_set_c.jsonl` and `data/eval_regex_b_set_c.jsonl`, rows in the eval result format (`llm_amount`, `llm_cur`, empty `needs_review_reasons`, `model='regex-a'|'regex-b'`). No LLM call.
- Scored with the existing `scripts/score_silent.py RESULTS --gold data/gold_set_c.jsonl`, unchanged, all three levels. Reported per baseline: silent errors (with types: missed / fabricated / wrong amount / wrong currency), 95% upper bound, flag rate at level 2.
- Compared with the live system's Set C numbers already recorded (v3 + code checks: 1/100 silent, 11/100 flagged).

## Decision
None. This is a comparison table for the question "why an LLM?". No threshold, nothing is adopted or removed. The gold is not touched.

## Honest limits
- The regexes were not tuned for this task beyond what existed; a better regex could score higher, but every rule it would need (equivalent currency, VAT, revisions, totals vs. shares) is exactly what the annotation guidelines R1-R5 describe, and those are meaning rules.
- One set, 100 texts; bounds are wide.
