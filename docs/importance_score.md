# Importance score v1 (rules, written before any measurement)

Date: 2026-11-02. The LLM extracts facts; this score is computed in code from those facts and from our own database. It is a ranking aid for the morning list, not a prediction.

## Inputs
- From the pipeline (prompt v3 + code checks): `amount`, `currency`, `counterparty_origin`, `related_party`, `is_revision`, `previous_amount`, `duration`, `needs_review`.
- From `new_business`: the central bank rate `tcmb_ex_rt` for the currency (latest on or before the disclosure date, at most 10 days back), and the company's earlier deals.

## Components (points)
| component | rule | points |
|---|---|---|
| size vs. company history | deal in TRY / median TRY value of the company's earlier deals (strictly before the disclosure date, at least 3 deals) | ratio >= 3: +3, >= 1.5: +2, >= 0.5: +1, else 0 |
| size, no history | fewer than 3 earlier deals: absolute TRY value | >= 1 billion: +2, >= 100 million: +1, else 0 |
| foreign currency | currency is not TRY | +1 |
| foreign counterparty | `counterparty_origin` is `foreign` | +1 |
| long contract | duration parsed as at least 2 years | +1 |
| related party | `related_party` is true | -2 |

- Revision: size uses the increase (`amount - previous_amount`, same currency). An increase of zero or less scores 0 for size. The kind is shown as `revision`.
- No amount, or no rate for the currency: size scores 0 and the reason says why.
- Level: score >= 4 `high`, 2-3 `medium`, else `low`.
- `needs_review` does not change the score. It is shown next to it as a reliability flag, and flagged items are always listed.

## Not used yet
- Revenue ratio: on since 2026-11-10 (our TRY amount / prod `shf_ret`, December fallback; size = max of history and revenue points; gates in `docs/revenue_ratio_rule.md` passed). Matriks `rt` and the market value ratio (`mar_val_rt`) are not used.
- Price reaction: not used as input.

## Honest limits
- Weights and thresholds are judgment, not fitted to data. There is no measured accuracy for the score.
- The company baseline uses Matriks amounts, which were wrong in some Set A cases; the median limits the effect of one bad value.
- Any later check of the score (for example against abnormal returns after the disclosure) needs its own decision rule, committed before measuring.
