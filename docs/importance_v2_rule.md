# Importance ordering v2 (rule, written before the dev choice and before round 2 exists)

Date: 2026-11-12. Follows `docs/importance_check_rule.md` (round 1: `AMOUNT_EXPLAINS`, score v1 AUC 0.681 = amount only 0.681; top pick amount 7/10, score 3/10).

## Dev material
Round 1 (10 days, 49 disclosures, 47 pairs) is now dev. Single-signal AUCs were looked at (metrics only, `importance_check.py --dev-report`): absolute amount 0.681, revenue ratio 0.638, history ratio 0.596, long contract 0.649 (7 of her yes, 0 of her no), foreign currency 0.585; related party, revision and `needs_review` near 0.5. The candidates below were written after seeing these numbers; that is why a held-out round decides.

## Candidates (fixed now; no weights are fitted)
Each is a sort key per disclosure (higher = look first; no amount or no rate = lowest amount):
- **C1 amount**: TRY amount; ties by the v1 score.
- **C2 v1 + amount**: v1 score; ties by the TRY amount.
- **C3 long, then amount**: long contract (≥ 2 years) first; then TRY amount.
- **C4 quality, then amount**: v1 points without the size part (foreign currency +1, foreign counterparty +1, long contract +1, related party −2); then TRY amount.

## Dev choice (mechanical)
Highest dev AUC wins. Gap below 0.005 → the simpler one, in the order C1, C3, C2, C4. The choice is committed before round 2 is sampled.

## Round 2 (held-out)
- 12 days with 4-8 disclosures, no saved morning list, not a round 1 day; seed 20261113. Same blind labeling as round 1 (`e`/`h` and the day's most important item). Same production pipeline, run once after the labels are complete.
- Files `data/importance_check_r2_*` (round 1 files stay untouched).

## Decision (fixed now)
- Fewer than 20 pairs → `INCONCLUSIVE`.
- The chosen candidate must beat chance: AUC > p95 of 10,000 within-day label shuffles. If not → `KEEP_V1`.
- `ADOPT_V2` if, in addition, AUC(chosen) − AUC(v1) ≥ 0.05 **or** top-1 days(chosen) − top-1 days(v1) ≥ 3, and AUC(chosen) ≥ AUC(v1) − 0.02. Otherwise `KEEP_V1`.
- Report alongside: all four candidates, v1 and amount only on round 2 (AUC, top-1, p-value). Not part of the decision.

## What changes if adopted
Only the order inside the two groups of the morning list and the panel ("önce bak": high or flagged; then the rest) uses the chosen key. Levels, points and the reasons shown stay v1, so every item still says why. The measured ranking is the pure key; the product keeps flagged and high items on top (stated).

## Limits
One analyst; she also labeled round 1, which is now dev. 12 days is still small: a 0.05 AUC gain is within the noise of about 50 pairs, which is why top-1 is a second route. Agreement with her is not a market outcome.
