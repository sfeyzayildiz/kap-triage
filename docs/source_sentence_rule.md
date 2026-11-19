# Source sentence on the card: is it the amount's source? (rule, written before code, sample and labels)

Date: 2026-11-20 (about 03:00). Feyza's request after the related-work look (20 Nov): the closest research ties every label to a quote and measures how good that link is; our cards show a "Kaynak cümle" but nobody has checked that it is the right sentence (`docs/known_issues.md` B9). Written before `scripts/source_eval.py`, before the pool is counted and before any label.

## What is measured
The sentence the panel shows today, nothing new: `panel.sources_for_items` → `source_check.source_sentence(text, amount)` = the first sentence of the disclosure text (`aciklama`) that contains a number equal to the saved extracted amount (0.5% tolerance), verbatim, cut around the amount when longer than 300 characters. No LLM call, no Matriks request, no change to the panel or the nightly path.

## Pool and sample
- Items in the saved morning lists (`data/morning_<day>.jsonl`) for days up to and including **2026-11-19** (fixed now, so later nightly lists do not change the pool), with an extracted amount and no `run_error`; one row per `news_id` (first saved day if repeated).
- Items whose sentence is `None` (the card then says the amount is not in the text) are counted and reported, not labeled.
- If the pool holds at most **40** items, all are labeled; otherwise 40 are drawn with seed **20261120**. `--plan` prints the counts (days, items, with amount, sentence `None`, pool) before the sample; `--sample` writes the list once and refuses to overwrite.

## Labeling (Feyza, her terminal, once)
`python scripts/source_eval.py --label` shows, per item: the disclosure text, the extracted amount and currency, and the shown sentence with the amount marked. One answer:
1. **doğru**: this sentence states the extracted amount in the role the card uses it (the deal amount); a reader who checks this sentence verifies the card's amount.
2. **yanlış**: the number in this sentence has another role (previous amount, total, a TL equivalent, another deal, a date or count that happens to be equal), or the amount is stated as the deal amount in another sentence.
3. **tutar yanlış**: the extracted amount itself is not the deal amount, so the question does not apply (counted, not in the metric).
4. **karar veremiyorum**.
A short note (tags, never the text) is optional. Resumable; `q` stops.

Not blind to the system output: the shown sentence and the amount are what is judged. No Matriks value is shown. Feyza may have seen some of these items before in the panel (stated).

## Decision (applied as written)
- n = items labeled 1 or 2; wrong = items labeled 2.
- **`INSUFFICIENT`** if n < 20 (reported, no claim).
- **`SOURCE_OK`** if n ≥ 20 and wrong ≤ 1.
- **`SOURCE_WEAK`** otherwise.
- Reported, no bar: right / n, the one-sided 95% upper bound on the wrong rate (Clopper-Pearson, `score_silent.upper_95`), counts of 3 and 4, the `None` count, pool size and whether it was a census.

## What the decision changes (before the submission on 24 Nov: documents only)
- Either way: a row in `docs/results.md`, `docs/known_issues.md` B9 updated with the number, a line in `docs/metrics_faq.md`.
- `SOURCE_OK`: the documents may say "the shown sentence was the amount's source in x/n (95% upper bound on errors …)". The card keeps its wording until after the submission (no panel change now; it would change the demo-mode hash and need a new leak check).
- `SOURCE_WEAK` or `INSUFFICIENT`: the documents keep saying "the sentence where the amount appears", the number is reported, and the README limit line names it.

## Honest limits
- One labeler, who built the system; items from the saved lists only (live nightly lists and demo days), not a random draw from all disclosures.
- Correctness of the amount itself is not re-measured here (Set C is the measurement for that).
- Amounts written in another form than the extracted number (for example "15 milyon" when the code looks for 15.000.000) are found by the number parser, but a sentence that states the amount only in words would be missed; such items appear as `None` and are counted.

## Result (20 Nov 2026 ~02:40; sample, labels and score by Feyza, once; code at main 4f02895)
- `--plan`: days 19 (<= 2026-11-19), items 46, with amount 34, sentence `None` 0, pool 34 → census.
- `--score`: sample 34: right 32, wrong 0, amount wrong 2, unsure 0 → right **32/32**; wrong rate 95% upper bound 8.9%.
- **Decision: `SOURCE_OK`** (n = 32 ≥ 20, wrong 0 ≤ 1). Applied as written: `docs/results.md` row, `docs/known_issues.md` B9, `docs/metrics_faq.md`. No panel change before the submission.
- Post-hoc, not part of this rule: of the 2 items labeled "amount wrong", 1 carried a review flag and 1 did not (counts only; `docs/known_issues.md` B13).
