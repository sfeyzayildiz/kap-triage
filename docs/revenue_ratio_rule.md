# Revenue ratio in the importance score: rule (written before the prod archive refresh)

Date: 2026-11-10. Committed before `prod_refresh.py --run` and before any revenue number from prod is seen.

## Why
"Is this deal big for this company?" is best answered against the company's revenue, not only against its own earlier deals. Matriks gives `shf_ret` (shifted revenue of the related balance sheet, TRY) and `per` (balance-sheet period) in `new_business`. It stayed off because apitest and prod disagreed (34 rows, mostly a different `per`), and negative `shf_ret` appears in non-December periods (hypothesis: trailing 12 months built by subtraction).

## Definition (code: `scripts/importance.py`, switch `USE_REVENUE`)
- **Revenue base** for a disclosure, from prod `new_business` after the refresh:
  1. its own record (`n.url = d.kap_url`) if `shf_ret > 0`;
  2. else the same company's latest record with a December period (`per % 100 = 12`), `shf_ret > 0`, date on or before the disclosure;
  3. else none (no revenue component; the reason says so).
- **Ratio** = our extracted amount in TRY (same rate as the size component; for a revision, the increase) / revenue base. Matriks `rt` is not used (it uses the Matriks amount, wrong in some Set A cases).
- **Points:** ratio ≥ 0.10 → 3, ≥ 0.03 → 2, ≥ 0.01 → 1, else 0. The size component becomes the **maximum** of the history points and the revenue points (no double counting). Both reasons are shown; the one not counted shows 0 points.
- Ratio > 5 (deal more than 5 years of revenue) is shown as "olağandışı oran, tutarı kontrol edin" in the reason. It does **not** add a `needs_review` flag, so the measured flag rate does not change.
- Level thresholds unchanged (≥ 4 high, 2-3 medium).

## Gates before switching on (counts from `scripts/revenue_check.py` on the refreshed prod table, run by Feyza)
1. **Semantics on prod:** among rows with `rt > 0` and `shf_ret > 0`, `rt` equals TRY amount / `shf_ret` within 5% on ≥ 90% (apitest was 1286/1296).
2. **Coverage:** disclosures with a revenue base (step 1 or 2) ≥ 60% of all disclosures.
3. **Scale sanity:** among covered disclosures with a Matriks amount, Matriks TRY amount / revenue base > 5 on ≤ 2%.
All three → `USE_REVENUE=True` in its own PR. Otherwise it stays off and the counts are recorded.

## Not measured (say so)
- The weights and thresholds are judgment, like the rest of the score; there is no accuracy number for the score.
- Whether prod `shf_ret` is the "right" revenue is not proven; gate 1 only shows internal consistency. The open question to Matriks (negative values, period choice) stays open.
