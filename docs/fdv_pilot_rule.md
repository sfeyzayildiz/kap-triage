# Second-type pilot 2: "Finansal Duran Varlık Edinimi / Satışı" (design and measurement rule, written before any pull, sample, label, prompt or code)

Date: 2026-11-19. Labels under `docs/fdv_guidelines.md`. Same method as the capital-increase pilot (`docs/capital_increase_rule.md`), whose result was `PILOT_NOT_ADOPTED` (0/30 silent, 16/30 flagged) and `LLM_ADDS`.

## Why this type
Stake acquisitions and sales (a company buys or sells shares of another company, founds a subsidiary, joins another company's capital increase) are among the disclosures an analyst reads first, and they raise the same questions as "Yeni İş İlişkisi": how big, in which currency, is it with a related party. KAP publishes them with a form template plus a free-text explanation, so the instructor's question "could it be solved without an LLM?" is measured a second time, on a type that mixes form and text.

## Questions
1. **Transfer:** does the method give a usable system for a second type within days?
2. **LLM or not:** does the LLM add anything over a code-only form reader on this type?

## Source (no tag for this type; documented filter `headline`)
- Matriks docs (`analistdocs.matriksdata.com`, news page, read 19 Nov): the news `query` accepts `category, symbol, source, headline, fundCode, date, before, after, tag, content`; how `headline` matches is not documented. There is no tag for this type.
- Our own corpus: 1296 of 1296 "Yeni İş İlişkisi" disclosures carry the KAP subject in the Matriks headline (counts only, 19 Nov). So the subject should be findable by headline.
- Query per month: `source:KAP headline:"Finansal Duran Varlık" after:.. before:..`. If that form errors or returns nothing for the whole window, `source:KAP headline:Duran` is tried in the same session.
- **Local filter decides, not the API:** an item is kept only if its headline contains "Finansal Duran Varlık Edinimi" or "Finansal Duran Varlık Satışı" (Turkish case folding). Printed per month: returned, kept, dropped. Loose API matching therefore cannot let another type in.
- A month whose search reaches the 2000 cap stops the pull (nothing is cut silently).

## Pull (one session, the day's only pull)
- **Saturday 21 Nov 2026, daytime** (not 23:30-23:59), `pull_guard.claim('fdv', resume=True)`; the nightly job skips that night; no list is sealed for 21 Nov (`docs/forward_test_rule.md`, Note 5). Raw files only, then load into separate tables (`fdv_disclosures`); the rows never enter `disclosures`.
- Window **2026-08-01 to 2026-11-20**. If the pool has fewer than 38 symbols, 2026-05-01 to 2026-07-31 is pulled in the same session. Still fewer: the pilot stops before anything is labeled.
- No structured Matriks record exists for this type: there is no cross-check layer and nothing report-only from Matriks.

## Order (each step only after the previous one)
1. This rule merged (Feyza's approval). 2. Pull, load, counts-only profile (`long_text` threshold set from it, as Note 4 of the capital rule). 3. Sample. 4. Feyza labels 8 dev texts (guideline shakedown, v0.2 if needed), then 30 held-out texts blind. 5. Form reader, prompt and checks written and tried on dev only. 6. Freeze commit; held-out run once; scoring once.

No held-out text goes through any reader before step 6. No scoring while a run is in progress.

## Sample (fixed)
- Seed **20261121**, `data/fdv_dev.jsonl` and `data/fdv_test.jsonl` (`text_sha1` per row, refuses to overwrite).
- Pool: `fdv_disclosures` in the window, with text and symbol; texts equal after normalization kept once.
- At most one disclosure per symbol over dev and held-out: shuffle with the seed, walk, take the first of each new symbol; first 8 dev, next 30 held-out. No strata: the pool's own mix of acquisitions, sales and updates.

## Labeling (Feyza, blind)
`scripts/label_fdv.py`: the text only (the whole content as plain text, as the readers get it), no reader output. Dev first. Labels are not changed after any reader has run on the held-out set; a later typo is reported separately.

## Systems under test (frozen at the commit of the run)
- **F, form reader:** code only (`scripts/fdv_form.py`), reads the form's label/value cells, plus the code checks. No LLM.
- **L, LLM:** `prompts/extract_fdv_v1.txt`, `gemma4:e4b`, thinking on, temperature 0, `num_ctx 8192`, plus the same code checks.
- **C, combined:** as in the capital pilot after its Notes 5-6: if F found anything, F's fields are used and L fills only what F cannot give; the code checks run again on C's values; if the primary keys of F and L differ, or one failed, `reader_disagree`.
- Dev limit: at most 3 prompt versions and 3 form-reader versions on the 8 dev texts; the chosen ones are named in the freeze commit.

## Measures (held-out 30, `scripts/fdv_score.py --score`, once)
**Primary key** of a record: `direction` (acquisition / sale / none); `amount` with `currency` (the transaction value as written); `stake_pct` (share of the target's capital acquired or sold in this transaction); `related_party` (y / n / not stated). Numbers match within 0.5% relative; an amount only matches with the same currency code. A number where gold has `-` is `fabricated`, a missing number where gold has one is `missed`.

- **Silent error:** not flagged and primary key ≠ gold (gold `needs_review` rows included; run errors count as flagged). **Flag rate:** flagged / 30. **Resolved:** not flagged and key = gold. **Latency:** median seconds per record (L and C).
- Reported for F, L and C; one-sided 95% upper bound on silent errors; error types (missed / fabricated / wrong number / wrong currency / wrong direction / wrong related party).
- Report only, no bar: target name match (normalized), `stake_after_pct`, the share of texts where the form carries the amount, the mix of acquisition / sale / founding. Repeatability of L not measured.

## Decision (fixed now; same lines as the capital pilot)
**Transfer (system C):** `ADOPT_PILOT` if silent ≤ 1/30 **and** flagged ≤ 9/30 **and** run errors ≤ 1 **and** median seconds ≤ 30. Otherwise `PILOT_NOT_ADOPTED`, reported as it is; nothing is changed to rescue the number.

**LLM or not (F against C):** `PARSER_ENOUGH` if F has ≤ 1 silent error **and** resolved(F) ≥ resolved(C) − 2. `LLM_ADDS` if silent(F) − silent(C) ≥ 2 **or** resolved(C) − resolved(F) ≥ 3. Otherwise `NO_CLEAR_DIFFERENCE`.

## What adoption means
`ADOPT_PILOT` allows a clearly labeled pilot line in the talk ("30 kayıtla ölçüldü"). It does not put this type into the morning list, the score, search or desk e-mails. Nothing on the nightly path changes before 26 Nov, whatever the result.

## Honest limits
- 30 records bound little (0/30 → upper 9.5%; 1/30 → 14.9%). The headline reliability numbers stay those of "Yeni İş İlişkisi".
- One labeler; guideline written blind and adjusted on 8 dev texts; readers written in a day by the same person.
- The headline route is undocumented; the local filter guards precision, but recall of the API (disclosures it does not return) is unknown and not measured.
- No vendor record for this type, so no cross-check layer.
