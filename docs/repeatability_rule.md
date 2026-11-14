# Repeatability of the extraction on Set C (rule, written before the second run)

Date: 2026-11-14. The MCP v1 measurement showed that two calls of the same extraction can differ at temperature 0. The headline result (Set C: 1 silent error in 100, level 2) came from one run. Question: how stable is it?

## Run (Feyza, once, about 25 min, Ollama on, not 23:40-23:50)
Same frozen system and the same commands as `docs/set_c_plan.md`, only a new output file:
`scripts/eval_vs_matriks.py --ids data/test_set_c.jsonl --prompt v3 --out data/eval_set_c_run2.jsonl`, then `scripts/score_silent.py data/eval_set_c_run2.jsonl --gold data/gold_set_c.jsonl` and `scripts/repeat_check.py`.

## Measures
- **R1 changes:** Set C items where the extracted (amount, currency) differs between run 1 (`data/eval_set_c.jsonl`) and run 2. Also: items where the flag set differs.
- **R2 run 2 result:** level-2 silent errors and flag rate of run 2 (same gold, same scorer).

## Decision (fixed now)
- R1 ≤ 2/100 → `STABLE`, else `UNSTABLE`.
- Run 2 meets the original Set C bar (silent ≤ 1, flag rate ≤ 15%) → `REPRODUCED`, else `NOT_REPRODUCED`.
- Reporting from now on: the headline becomes "1/100 in run 1, X/100 in run 2", whatever X is. `UNSTABLE` makes self-consistency (several runs, majority vote) the next candidate, with its own rule. Gold labels are not touched.
