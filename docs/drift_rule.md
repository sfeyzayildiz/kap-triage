# Drift check: does extraction still agree with Matriks after Set C? (rule, written before the run)

Date: 2026-11-13. Set C (sampled up to 2026-10-08) is the last held-out measurement. Question: on disclosures published **after** Set C, does the production extraction (prompt v3) agree with Matriks' own amount record as often as on Set C? No labeling: Matriks is the reference here. It is not gold (Matriks can be wrong too), so this detects drift; it does not measure silent errors.

- Baseline (already stored in `data/eval_set_c.jsonl`): Set C items with a Matriks amount, amount and currency both agree: **72/78 (92.3%)**.
- New: every disclosure published after 2026-10-08 with a Matriks amount (**40** at rule time). One run of `scripts/eval_vs_matriks.py --prompt v3` on them (`scripts/drift_check.py --ids` writes the id list), about 10 min; then `scripts/drift_check.py --score` once.
- **Decision (fixed now):** new agreement ≥ baseline − 10 points (≥ 82.3%) → `NO_DRIFT_SEEN`; lower → `DRIFT_SUSPECTED` (stated in the docs; next step a new labeled set). Output: counts and mismatch ids only; amounts go to `/tmp` (never pasted or read).
- Limits: 40 items (wide interval); Matriks is a reference, not gold; some of these days were seen by Feyza in the panel, but no code or prompt was changed from them.
