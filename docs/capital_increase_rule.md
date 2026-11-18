# Capital-increase pilot: measurement rule (written before any pull, sample, label, prompt or code)

Date: 2026-11-16. Design in `docs/capital_increase_pilot.md`, labels under `docs/capital_increase_guidelines.md`. The numbers below use the recommended options D1-D5 of the design; Feyza's choices are recorded as Note 1 before sampling, and nothing else changes after that.

## Questions
1. **Transfer:** does the method (reader extracts, code checks and flags, blind gold, rule first) give a usable system for a second disclosure type within days?
2. **LLM or not:** on a form-based type, does the LLM add anything over a code-only form reader?

## Order (each step only after the previous one)
1. This rule merged.
2. One pull (D1, D4, D5), raw files only; load; counts-only profile.
3. Sample.
4. Feyza labels the 8 dev texts (guideline shakedown, v0.2 if needed), then the 30 held-out texts blind.
5. Form reader, prompt and checks are written and tried on dev only.
6. Freeze commit. Held-out run, once. Scoring, once.

No held-out text is run through any reader before step 6. No scoring while a run is in progress.

## Sample (fixed)
- Script `scripts/sample_capital.py`, seed **20261116**, output `data/capital_dev.jsonl` and `data/capital_test.jsonl` (not in git, `text_sha1` per row, refuses to overwrite).
- Pool: `capital_disclosures` published from 2026-08-01 to the day before the pull, with text; texts equal after normalization are kept once.
- At most one disclosure per symbol over dev and held-out together, so 38 different companies. Draw: shuffle the pool with the seed, walk it, take the first disclosure of each new symbol; the first 8 are dev, the next 30 are held-out.
- No strata: the pool's own mix (many bonus issues, many update steps) is what an analyst sees. The mix by component and stage is reported from the gold labels afterwards.
- If the pool has fewer than 38 symbols, the pilot stops and the window is discussed before anything is labeled.

## Labeling (Feyza, blind)
- `scripts/label_capital.py`: text only (the full form as the readers will get it), no Matriks record, no reader output. Dev first.
- Labels are not changed after any reader has run on the held-out set. A typo found later is reported separately as post-hoc; the decision uses the frozen gold.

## Systems under test (frozen at the commit of the run)
- **F, form reader:** code only, reads the form cells and tables, plus the code checks. No LLM call.
- **L, LLM:** `prompts/cap_v1.txt`, `gemma4:e4b`, thinking on, temperature 0, `num_ctx 8192`, plus the same code checks.
- **C, combined:** F and L both run; values are F's where F has them, else L's; if the primary keys of F and L differ, or one of them failed, the record is flagged `reader_disagree`. Code flags, it does not pick the "right" one.
- Dev limit: at most 3 prompt versions and 3 form-reader versions are tried on the 8 dev texts. The one chosen is named in the freeze commit.

## Measures (held-out 30, `scripts/capital_score.py --score`, once)
**Primary key** of a record: `subject`; `rights` and its rate; `bonus` and its total rate (internal + dividend, added in code on both sides); `restricted` and its amount; cancelled or not (`stage == cancelled`). Numbers match within 0.5% relative. A number where gold has `-` is an error (`fabricated`), a missing number where gold has one is an error (`missed`).

- **Silent error:** not flagged and primary key ≠ gold. Gold `needs_review` rows are included; run errors count as flagged.
- **Flag rate:** flagged / 30.
- **Resolved:** not flagged and primary key = gold.
- **Latency:** median seconds per record (L and C).

Reported for F, L and C; one-sided 95% upper bound on silent errors (`score_silent.upper_95`); error types (missed / fabricated / wrong number / wrong component / wrong subject / cancelled missed).

Report only, no bar:
- `stage` exact match (7 classes) and the confusion counts.
- `rights_price_try` match, on records where gold has a price.
- Bonus source split (internal vs. dividend) match.
- Matriks record (if D5a): of the held-out records with a rights or bonus rate in gold, how many have a `capital_matriks` row of the same symbol with that rate (0.5%); ids of the rest.
- Price bridge (if D5a, code only): of the "possible split" days in `daily_bars` (`price_moves.SPLIT_JUMP`), how many have a `capital_matriks` row of that symbol starting within 3 calendar days.
- Repeatability of L is not measured (one run).

## Decision (fixed now)
**Transfer (system C):**
- `ADOPT_PILOT` if silent ≤ 1/30 **and** flagged ≤ 9/30 **and** run errors ≤ 1 **and** median seconds ≤ 30.
- Otherwise `PILOT_NOT_ADOPTED`, reported as it is. No prompt, reader or check is changed to rescue the number; a new version needs new held-out texts.

**LLM or not (F against C):**
- `PARSER_ENOUGH` if F has ≤ 1 silent error **and** resolved(F) ≥ resolved(C) − 2.
- `LLM_ADDS` if silent(F) − silent(C) ≥ 2 **or** resolved(C) − resolved(F) ≥ 3.
- Otherwise `NO_CLEAR_DIFFERENCE`.

The three lines cannot hold together. Each is a reportable answer to "could it be done without an LLM?" for this type; none of them changes the "Yeni İş İlişkisi" system.

## What adoption means
- `ADOPT_PILOT` allows a separate, clearly labeled pilot view ("30 kayıtla ölçüldü") and one line in the talk. It does not put this type into the morning list, the importance score, the search index or the desk e-mails.
- Until 26 Nov nothing on the nightly path changes (`collector.py`, `daily_collect.py`, `morning*.py`, `pipeline.py`, `importance.py`, `schema.sql`), whatever the result: the sealed forward test runs on one system.
- The capital-increase rows never enter the `disclosures` table.

## Note 1 (2026-11-16, Feyza's choices; before any pull, sample or label)
- **D1 → (c), moved to Saturday 21 Nov 2026, daytime.** The nightly job is not paused: `pull_guard` makes it skip that night (`KAP collector SKIPPED`), which is accepted. Consequence, stated before the day: there is no sealed morning list for 21 Nov, so any disclosure of that day is outside the forward test (the 3-day lookback collects it the next night, unsealed). A weekend list is most likely empty. The pull claims `capital` once (`pull_guard.claim('capital')`), not 23:30-23:59, raw files only.
- **D2 → (a):** 8 dev + 30 held-out.
- **D3 → (a):** core gold fields, as in guideline v0.1.
- **D4 → (a), with a fixed fallback:** window 2026-08-01 to 2026-11-20. If the pulled disclosures have fewer than 38 different symbols, the start date moves to **2026-05-01**. The count is taken from the raw files during the same pull session, so the extension needs no second pull day. If there are still fewer than 38 symbols, the pilot stops before anything is labeled. This replaces the last line of "Sample".
- **D5 → (a):** one request to `v1/capital-increase` in the same session (`start=2024-09-01`, `end=2026-11-21`, `type=CPI`), report only.
- Nothing else in this rule changes: seed, draw, systems, measures and decision lines are as written above.

## Note 1b (2026-11-18 morning, before any pull, sample or label; Feyza's choice)
- **D1 moved from (c) Sat 21 Nov to (d) Wed 18 Nov, daytime.** Reason: finish the project early (Feyza has the day for labeling). No capital-increase text, sample or result exists yet, so the change cannot be shaped by data.
- **Window:** 2026-08-01 to **2026-11-17** (the day before the pull); fallback start 2026-05-01 unchanged. The `v1/capital-increase` request uses `end=2026-11-18`.
- Cost for the forward test, stated before the day: no list is sealed for 18 Nov (a weekday with real items); 21 Nov is sealed again. See Note 4 of `docs/forward_test_rule.md`.
- Nothing else changes: seed, draw, sizes, systems, measures and decision lines are as written above.

## Note 4 (2026-11-18, after the pull and the counts-only profile, before any sample or label)
- Pull: 213 disclosures (2026-08-03..2026-11-17), **80 symbols**, so no fallback; 296 `v1/capital-increase` records (233 symbols, 53 shared with the disclosures). Every text has a form table, 212/213 a multi-column one; the "Açıklama" cell exists in 1/213 (trap T19 confirmed; readers use `text`, not `aciklama`). `is_update` is 0 for all: the update question has another label in this form; not used by any measure.
- **Long-text threshold:** prompt 2,838 tokens; the 10 longest texts have 2.70-3.09 characters per token. With a 2,048-token answer reserve, 3,306 tokens are left for the text, about 8,900 characters at the lowest ratio. `LONG_TEXT_CHARS` is set to **8,000** (10% margin); 4 of 213 texts are longer. The 2,048 reserve is an estimate (thinking length varies); an answer that does not fit becomes a run error, which counts as flagged.
- Nothing else changes.

## Note 5 (2026-11-18, after the first dev run, before any reader touched a held-out text)
Dev run 1 (8 texts, prompt v1, form reader v1, checks v1): F 3 silent (2 wrong subject, 1 cancelled missed), 4 flagged; L 0 silent, 7 flagged; C 0 silent, 8 flagged. Diagnosed with counts and our own field names only (no text, no amount):
- **Checks v2:** the `simultaneous_decrease` word check fired on 4/8 texts while the gold has it on 0/8 (the words occur outside the form labels, in wording every such form carries). Removed; the prompt's own review code of that name stays. Other checks unchanged; `long_text` 8,000 (Note 4).
- **Form reader v2:** in 2 of the 3 dev forms with a tahsis section the nominal amount cell is empty, so v1 found no component at all (both wrong-subject errors). A filled tahsis / kısıtlama cell (not unused or cancelled shares) now marks `restricted`; the amount stays empty.
- **System C, read per record:** "F's values where F has them" now means: if F found anything, every field a form can give, the component flags and the subject come from F (None included) and L fills only the fields F cannot give. Field-by-field mixing counted one bonus twice on a dev text (F read it as dividend-sourced, L as internal) and raised `arith_mismatch`.
- Prompt unchanged (v1). L's own `arith_mismatch` flags (L's amounts do not add up on 5/8) are left as they are: they caught every L error on dev.
- Versions used so far: prompt 1 of 3, form reader 2 of 3. Dev run 2 follows; then the freeze.

## Note 2 (2026-11-16, before any pull; descriptive, no decision changes)
- First drafts of the two readers were written before the pull, from the public form layout and synthetic examples only: `scripts/capital_form.py` (form reader F, 28 self-test checks) and `prompts/extract_ci_v1.txt` (the prompt this rule calls `prompts/cap_v1.txt`; the file name follows `extract_v3.txt`). The order above puts this step after labeling; writing it earlier exposes no text, since none exists yet.
- These drafts are **version 1 of the three** allowed for each reader. Any change after the dev texts are seen is version 2.
- The form reader's label table was written from memory of the KAP form, not from Matriks' rendering. If the counts-only profile shows that the content carries no tables, F falls back to whatever LLM-free reader can be written within the three versions, and that is reported.

## Note 3 (2026-11-16, before any pull; how the code reads this rule, no decision changes)
`scripts/capital_checks.py` (checks, primary key, combination) and `scripts/capital_score.py` (scorer) were written from this rule and synthetic rows. Points the rule left open, fixed now:
- **Subject of a reader that found nothing** is read as `none` in the primary key (the form reader cannot tell `other` from `none`; against a gold `other` that is a wrong subject).
- **Error types:** the rule's list, plus `cancelled_fabricated` for a system that says cancelled where gold does not.
- **System C:** the code checks run on the combined values, the reasons of both readers are kept, then `reader_disagree` is added if the keys differ or one reader failed.
- **Check list, version 1:** `arith_mismatch`, `rate_mismatch`, `ceiling_as_value`, `rate_not_in_text` (the design's `rate_not_anchored`: a rate cell of the form carries no "%" sign, so the check asks only that the number is written in the text), `no_component`, `simultaneous_decrease`, `long_text` (15,000 characters, an estimate to set from the profile), `reader_disagree`. Not checked: amounts against the text (the form reader sums share groups).
- **Files:** gold `data/gold_capital_test.jsonl`, runs `data/capital_run_f.jsonl`, `_l`, `_c`. The scorer refuses unless the gold and all three runs hold the same 30 ids (`INCOMPLETE`), scores once and keeps the result in `data/capital_score.txt`.
- The Matriks-record and price-bridge reports print "not available" if the tables are missing.

## Note 3b (2026-11-16, before any pull; how the runner and the labeling tool read this rule, no decision changes)
`scripts/label_capital.py` and `scripts/capital_extract.py` were written from this rule and synthetic rows. Points it left open, fixed now:
- **What each reader gets.** The labeler and L get the same `text` (the whole content as plain text, one line per row or block, cells joined by " | "); F gets the HTML `content`. The headline is shown to neither.
- **A version** of a reader is the sha1 of its file (`prompts/extract_ci_<v>.txt`, `scripts/capital_form.py`). Every dev run is logged (`data/capital_dev_versions.jsonl`) and a fourth distinct version of either is refused. Any edit counts, a comment included.
- **"Once"** for the held-out run: it may resume after a crash at the same commit; a run at another commit is refused. It starts only when all 30 held-out labels exist, `scripts/` and `prompts/` are committed, and the prompt and form reader in use were run on dev.
- **Run errors:** a reader exception (Ollama timeout, 120 s as in `llm_extract.py`; invalid JSON after one retry) is a run error. Thinking is passed explicitly (`think=True`).
- **Labeling order:** held-out labeling refuses until the 8 dev labels exist; all held-out labels carry one guideline version; held-out labels cannot be redone once a held-out run file exists. Dev labels can be redone (shakedown).
- **Latency:** C's seconds are F's plus L's for the same record.

## Honest limits
- **30 records bound very little.** 0/30 silent only says the rate is probably below 9.5%; 1/30 below 14.9%; 2/30 below 19.5%. `ADOPT_PILOT` means "the method transferred and nothing alarming was seen", not "measured reliable". The headline reliability numbers stay those of "Yeni İş İlişkisi" (Set C, Set D).
- One labeler, a guideline written blind and adjusted on 8 dev texts.
- One company per symbol and a window of a few months: no claim about all companies or all years.
- The primary key leaves out the price, the stage (except cancelled) and the amounts; those are report-only here.
- Unlike "Yeni İş İlişkisi", there is no exact Matriks record per disclosure, so the cross-check layer is not part of what is measured.
- The dev set is tiny; the three-version limit keeps tuning small but does not remove it.
- The LLM-or-not lines compare two readers written in a day by the same person; a better parser or a better prompt could move either.
