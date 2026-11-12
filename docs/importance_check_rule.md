# Importance score vs. the analyst's blind look-first choice (rule, written before any label or run)

Date: 2026-11-12. Written and committed before the days are sampled, before any label exists and before any pipeline run on these days. Report only: nothing in the code changes on this result before the final.

## Question
The importance score v1 (`docs/importance_score.md`, revenue ratio on) has judgment weights and no measured accuracy. Does it order a day's disclosures the way an analyst would, better than chance, and better than sorting by amount alone?

## Days
- Pool: days with 4 to 8 disclosures, with no saved morning list (`data/morning_<day>.jsonl`; Feyza has seen those days, including every demo day).
- Sample: 10 days, `random.Random(20261112)`, written to `data/importance_check_days.json` (`--sample`, refuses to overwrite). Fewer than 10 in the pool → all of them.
- Disclosures in Set A/B/C are not removed: this measures the ranking, not the extraction (stated limit: Feyza labeled some of these texts for amounts).

## Labels (Feyza, blind)
- `--label` shows each day's disclosures in a seeded shuffled order: symbol, time, KAP link, headline and the disclosure text. No Matriks value, no extraction, no score.
- Per disclosure: "Sabah ilk bakardın mı?" `e` / `h`. After the last one of the day: "Günün en önemlisi hangisi?" (number, or `-` if none stands out).
- Labeling refuses to start once a results file exists. The run stores the sha1 of the label file; scoring refuses if the labels changed afterwards.

## Systems compared (same disclosures, same day)
1. **Score**: production `importance.score_result` on the production pipeline output (v3 + code checks + layered defence, same calls as `morning.extract_day`). Ties count as half.
2. **Amount only**: our extracted amount in TRY (amount × rate from `importance.fx_rate`, the stated amount also for revisions); no amount or no rate ranks lowest (ties as half).
3. **Random**: the null distribution below.

Disclosures with `run_error` are left out of the pairs and counted.

## Main number
Within-day pairwise agreement (AUC): over all pairs (Feyza `e`, Feyza `h`) from the same day, the share where the system ranks the `e` item higher (ties 0.5). Days where all or none are `e` contribute no pairs (counted). Null: 10,000 within-day shuffles of Feyza's labels (`random.Random(20261112)`), AUC of the score each time; p95 recorded.

## Decision (fixed now)
- Fewer than 20 pairs → `INCONCLUSIVE` (reported, nothing claimed).
- Score AUC > null p95 and Score AUC − Amount AUC ≥ 0.05 → `SCORE_ADDS`: the score agrees with the analyst beyond chance and beyond amount alone.
- Score AUC > null p95 and the margin < 0.05 → `AMOUNT_EXPLAINS`: beyond chance, but amount alone does as well on this sample; the other components are not shown to add value.
- Score AUC ≤ null p95 → `NO_EVIDENCE`: the score's order is not shown to match the analyst's.
- Whatever the result: weights and thresholds stay (fitting them to these labels would be tuning); the number goes to `docs/importance_score.md`, `docs/metrics_faq.md` and the presentation. A score v2 needs new days and its own rule.

## Reported alongside (not part of the decision)
- Amount AUC against the same null (p-value).
- Top-1: days where the system's first item is Feyza's "most important" (ties split), against the random expectation (mean of 1/n over those days).
- Level `high` vs. Feyza's `e`: 2×2 counts.
- Score with the TRY amount as tie-break (AUC).
- Counts: days, disclosures, `e`, pairs, days without pairs, `run_error`, `needs_review`, ties in the score.

## Limits (state them)
One analyst, who also built the system and knows the score's components; about 10 days and 40-60 disclosures; her "look first" is a judgment about the text, not a market outcome. Agreement with her is not proof that the score predicts price moves.
