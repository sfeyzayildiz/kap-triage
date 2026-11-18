# Data-vendor auditor: is this Matriks record consistent with the KAP text? (rule, written before code, run and labels)

Date: 2026-11-18. Written before `scripts/vendor_audit.py`, before any auditor number and before any new label. Decisions by Feyza (18 Nov): measure on the existing blind gold **and** on a new pool labeled by her; do not wait for the instructor's precision/recall answer (if it changes the priority, that is a v2 rule; this measurement stays as written).

## Why
Until now Matriks' structured record (`new_business`: `amount`, `cur`, `tcmb_ex_rt`) was a reference for us. The question here is turned around: can our extraction from the KAP text tell a data vendor **which of its records may be wrong**? We already saw it by hand: on Set A, 3 of 10 disagreements were Matriks errors (2 pre-revision amounts, 1 value not in the text; `docs/matriks_feedback.md` item 4). A vendor's checker reads each candidate, so a candidate list is only useful if a good share of it is real. **Precision is the primary metric**; recall is reported.

The auditor flags only. It never changes a Matriks value or our extraction. Nothing is sent anywhere; a report for Matriks is sent by Feyza by hand, if at all.

## Auditor (code, `scripts/vendor_audit.py`, frozen before M1)
Input per disclosure with a Matriks record for the same KAP link: Matriks `amount`, `cur`, `tcmb_ex_rt`; our result (`amount`, `currency`, `needs_review_reasons`, `error`); the text.

1. **Not auditable** (counted, never flagged): run error; our amount is null; Matriks amount null or ≤ 0; our result has any review reason other than `amount_vs_matriks` (that check is itself a disagreement signal; every other reason means our own reading is unsure, so we do not accuse the vendor). For result files written before the current checks, `currency_unclear`, `amount_is_projection` and `cumulative_total` (v2) are recomputed on the text, as `score_silent.py` level 2 does.
2. Currencies normalised with `norm_cur`.
3. **Same currency:** gap = |ours − Matriks| / Matriks.
   - gap ≤ 1% → `match` (the tolerance of every earlier Matriks comparison).
   - ours / Matriks or Matriks / ours in [1.175, 1.185] or [1.195, 1.205] → `definition_vat` (VAT 18% or 20% on one side).
   - otherwise → **flag `amount_differs`**.
4. **Different currencies:**
   - the two numbers within 1% of each other → **flag `currency_differs`** (same number, other currency).
   - Matriks foreign with a rate and ours TRY: ours / (Matriks × rate) within 3% → `definition_tl_equivalent` (the text gives the TL equivalent; 3% covers a different day's rate, Matriks' rate gap is p95 0.9%); otherwise **flag `amount_differs`**.
   - any other pair (Matriks TRY and ours foreign; two foreign currencies) → `no_basis`, not flagged.
5. Reported on flagged rows, not used in the decision: whether the disclosure is an update (`is_update`), the pre-revision pattern of item 4.
6. Reported only: `record_missing` = disclosures without a Matriks record where our clean extraction has an amount (coverage, item 5 of the feedback note).

## M1: existing blind gold (no new label, seconds, code only)
- Sets B, C, D (labeled by Feyza from the text only, no Matriks value, no model output). Set A is dev only: its gold is partly Matriks itself.
- Our results: Set B `data/eval_v3_e4b_set_b.jsonl` (frozen gold, not the corrected one), Set C `data/eval_set_c.jsonl` (run 1), Set D `data/set_d_run_a.jsonl` (run a). No new LLM run.
- Truth: the same comparison with the gold amount and currency in place of ours. Matriks error = `amount_differs` or `currency_differs` against gold, or gold amount null (no amount in the text) while Matriks has one. Gold `needs_review` rows are left out of truth and counted.
- Reported: flags, true positives, precision, Matriks errors, recall, and each false positive by type (gold agrees with Matriks = our extraction was wrong; gold `definition_*`; gold `no_basis`). Set D's targeted stratum U is included and said. **No bar on M1** (expected true errors are few, so the bounds are wide).

## M2: new pool, labeled blind by Feyza
- **Pool:** disclosures published before 2026-11-18 with text and a Matriks amount > 0, not in Set A, B, C, D, the prompt dev file, `test_label` or `eval_v1` (every disclosure with a gold amount or used to write the prompt), duplicate texts collapsed as in `sample_set_c.py`. Size printed by `--plan` before the run.
- **Run:** the live pipeline (`pipeline.analyze` + `judge_pass`, prompt v3, `gemma4:e4b`), one run per text (the nightly two-run flag is not used: it would double ~3 h). Feyza runs it, not 23:40-23:50; resumable. Not scored while running.
- **Sample** (seed 20261118): up to **30 candidates** (flagged rows, seeded random if more) + the **same number of controls** (seeded random from auditable, not flagged rows), shuffled together.
- **Labeling** (`--label`, Feyza's terminal): the text and Matriks' amount and currency only; no auditor output, no our extraction, no group. One answer per row:
  1. **tutarlı**: the record matches the text.
  2. **tanım farkı**: same deal, another convention (VAT, TL equivalent, company share, multi-currency part, first-year vs. total).
  3. **tutarsız**: the record is not supported by the text; sub-code a) value not in the text, b) pre-revision value, c) wrong currency, d) wrong scale (bin/milyon/milyar), e) other.
  4. **karar veremiyorum**.
  Labels go to `data/` (gitignored); stdout counts only.

## Decision (on M2, applied as written)
- Strict precision **P = (candidates labeled 3) / (candidates labeled 1, 2 or 3)**.
- **`ADOPT_AUDITOR`** if P ≥ 0.50 and at least 10 candidates are labeled 1-3.
- **`INSUFFICIENT`** if fewer than 10 candidates are labeled 1-3: reported, not adopted.
- **`AUDITOR_OFF`** otherwise.
- Why 0.50: a checker reads one short text per candidate (about a minute); at one real error per two candidates the list saves time compared with reading records at random (the control group gives that base rate).
- Reported, no bar: P with its 95% interval (Clopper-Pearson); lenient precision (2 + 3); the control group's rate of 3 and the estimated misses in the pool (rate × auditable not-flagged rows); counts per reason and per sub-code; flags on update disclosures; not-auditable and `no_basis` counts; `record_missing`; run errors and run time.

## What adoption means
- `scripts/vendor_audit.py --day D` writes the day's audit list to `data/` (amounts stay local), stdout counts only.
- The nightly path is not touched before the forward test ends: from 26 Nov, `morning_job.py` calls it and the nightly alert gets the count (`denetim N`).
- Item in `docs/matriks_feedback.md` with the measured precision; record ids only on request.
- Not adopted: the script stays as a report tool and the result is published the same way.

## Order
Rule commit → code + self-tests → dev on Set A (at most 2 code versions, reported) → code commit (frozen) → M1 scored once → M2 run (Feyza) → sample → labels (Feyza) → score once → record in PROJECT_NOTES, results, metrics_faq, matriks_feedback.

## Amendment 1 (2026-11-18, after the dev run on Set A, before M1; reporting only)
Dev on Set A counted 5 Matriks errors against the adjudicated gold, where the 28 Oct hand analysis found 3. The other two are gaps the guideline settles by a convention (R3 multiple orders, R4 company share), which M1's truth cannot tell from a real error. Truth and decision stay as written. **Added to the M1 report:** true positives and Matriks errors split by the gold's `rule` field: a convention rule (R1, R2, R3, R4, R6) vs. none or R5 (revision: the pre-revision value is a real error). M1 precision is therefore read as closer to M2's lenient precision; M2's strict precision stays the decision.

## Honest limits
- Truth is one annotator (no second annotator, stated earlier).
- If our extraction is wrong in the same way as Matriks (both wrong, same number), the auditor cannot see it.
- Rows our own checks flag are not audited, so recall is lower by design; disclosures without a record are not audited at all.
- Feyza sees the Matriks value while labeling M2; she does not see whether the row is a candidate.
