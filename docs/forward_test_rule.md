# Sealed forward test: did "look first" move more the next day? (rule, written before any sealed list)

Date: 2026-11-14 (22:30). Every earlier measurement used past data. This one is prospective: the morning list is sealed each night **before the market opens**, and the market's answer is read only after the last sealed day. Nobody (Feyza or Claude) can choose the result afterwards.

## Sealing (from the first nightly run after this code is in kap-deploy)
- Right after the nightly morning list for day D is built (~23:45-00:00), `scripts/forward_seal.py` writes a canonical snapshot `data/seals/<D>.json`: for every disclosure of D, `news_id`, `symbol`, `published_at`, `look_first` (`needs_review` or level `high`, as in the panel), `level`, `score`; sorted by `news_id`; UTF-8, sorted keys, no spaces.
- SHA-256 of that file goes to `data/seal_log.jsonl` (day, hash, counts, time) and its **first 16 hex characters into the phone alert** (`KAP morning list ... | mühür <hash16>`). The ntfy alert carries an outside time stamp; the hash carries no data.
- A snapshot is never overwritten; a rebuild of the same day keeps the first seal (a different second hash is logged as `reseal_mismatch`).
- Sealed days: lists for **2026-11-15 .. 2026-11-25** (inclusive); the next trading day of the last one is 2026-11-26. One approved price pull after 26 Nov (bars to 26 Nov), then scoring once.

## Measurement (code, once, after the price pull)
- **Integrity:** recompute each snapshot's hash; all equal to the log and to the alert prefix (Feyza keeps the ntfy history) → `INTACT`, else the day is dropped and reported.
- **Unit:** each sealed disclosure. **t1** = the first trading day **after D** (strictly later than the seal), so the move cannot have been seen when sealing. **AR** = stock return − XU100 return on t1 (`price_moves.abnormal`, unadjusted closes).
- Excluded and counted: no price (e.g. EFORC), |stock return| > 22% on t1 (`price_moves.SPLIT_JUMP`, possible split).
- **Primary:** mean |AR| of look-first items minus mean |AR| of the others. One-sided permutation test (look-first labels shuffled 10,000 times, seed 20261114).
- **Decision (fixed now):** at least 4 look-first and 4 other items, difference > 0 and permutation p ≤ 0.10 → `SUPPORTED`; otherwise `NOT_SUPPORTED`; fewer items → `TOO_FEW` (no decision).
- Reported, not decided: the same for the reaction day (includes same-day reactions of intraday disclosures, so not fully forward), the signed mean AR, and counts per group.

## Limits (said in the presentation)
About 8 trading days and perhaps 10-30 disclosures: a signal, not proof. Direction is not predicted (the list says "look", not "buy"). Prices are unadjusted. The list ranks attention, so `NOT_SUPPORTED` is a valid, reportable result.

## Result (2026-11-24 ~00:30, scored once)
Bars loaded to 2026-11-23 (151 symbols, 0 dropped rows). Integrity **INTACT**: 3 sealed days (15, 16, 20 Nov; no seal on 17-19 Nov, Notes 3-6), 6 disclosures; the seal hash prefixes printed by the scorer match the ones in the phone alerts of 15, 16 and 20 Nov (checked by Feyza), so the lists were fixed before the prices existed. t1 (primary): look-first 3, other 3; mean absolute AR difference -1.87 percentage points, one-sided p 0.85. Reaction day (report): +0.73 points, p 0.20. No item excluded (no price 0, possible split 0). **Decision: `TOO_FEW`** (the bar needs at least 4 items per group), as Note 7 expected. What it shows: sealing before prices exist, the later price pull and the one-time scoring work end to end; it says nothing about whether the ordering predicts moves. Two-run count on the saved lists of 15-23 Nov (known issue A12, report only): 6 lists, 10 items, 0 disagreements, 0 run errors.

## Note 9 (2026-11-24 00:10, before the price pull and before any bar after 20 Nov exists; Feyza's choice)
The price pull moves from "about 10:00" (Note 8) to just after midnight on **Tue 24 Nov**, because Feyza is at school during the day. It is still 24 Nov and still that day's only Matriks pull; `price_collect.py` ends the bars on the day before, Mon 23 Nov, as Note 7 needs. The submission now closes at 23:59 (not 18:00, Note 8); the 14:00 fallback of Note 8 stays exactly as written. Nothing else changes: the scored window still ends with the list of 20 Nov, the decision line is unchanged, `forward_score.py` is not edited.

## Note 8 (2026-11-19 ~19:30, before the price pull and before any price after the first seal exists; Feyza's choice)
The submission closes on **Tue 24 Nov 2026 at 18:00**; nothing can be added after it. Plan for that day: about 10:00 the price pull and the one-time score (`price_collect.py --pull --yes`, `price_collect.py --load`, `forward_score.py --score`); until about 15:00 the notes, the timeline and the public copy; until 18:00 spare time.
**Fallback, fixed now:** if by **14:00** the bars are not loaded up to Mon 23 Nov (the pull or the load failed, also after the same-day resume that `pull_guard` allows for the price pull), or `forward_score.py --score` has not written its result, the forward test is **not scored**. The submission then says so plainly ("forward test not scored: <step> failed on 24 Nov"), with the seals and the scoring code left as they are. No score is added after 14:00 or after the submission, and no other window is scored instead. A result written before 14:00 is reported whatever it is (`SUPPORTED`, `NOT_SUPPORTED` or `TOO_FEW`).
The price pull is that day's only Matriks pull, so the nightly job skips the night of 24 Nov (one-pull-per-day guard); that list is outside the scored window (Note 7). Nothing else changes.

## Note 7 (2026-11-19 ~17:40, before any price after the first seal exists; Feyza's choice)
The project must be finished by the submission on **Tue 24 Nov**. The scored window therefore **ends with the list of 20 Nov** (was 25 Nov). One price pull on **Tue 24 Nov, daytime** (bars to Mon 23 Nov, the first trading day after 20 Nov), then scoring once, the same day. Sealed weekdays inside the window: 16 and 20 Nov (15 is a Sunday; 17-19 have no seal, Notes 3-6). Expected: very few items, most likely `TOO_FEW` under the unchanged decision line (at least 4 look-first and 4 other items); that is the honest outcome and is reported as such: the test then shows that sealing, the later price pull and the one-time scoring work end to end, not that the ordering predicts moves. The nightly job keeps sealing 21-25 Nov (`forward_seal.py` is on the nightly path and is not changed); those seals are not scored. `forward_score.py`: `LAST_DAY` 2026-11-20, `NEED_BAR` 2026-11-23. Nothing else changes.

## Note 6 (2026-11-19 15:10, before the pull and before any outcome exists; replaces Note 5)
The second pilot pull moves from Sat 21 Nov to **today, Thu 19 Nov, daytime**: the project submission deadline moved to Tue 24 Nov (instructor, 19 Nov), and Sat 21 Nov is a class day. The nightly job skips tonight under the one-pull-per-day guard, so **no list is sealed for 19 Nov** (the next night's lookback collects it, unsealed); 21 Nov is sealed again. Cost, stated before: one weekday with real items. Sealed days: **15-16, 20-25 Nov** (weekdays 16, 20, 23, 24, 25). Nothing else changes.

## Note 5 (2026-11-19 02:30, before the pull and before any outcome exists)
A second pilot pull (`docs/fdv_pilot_rule.md`) runs on **Saturday 21 Nov 2026** daytime. The nightly job skips that night under the one-pull-per-day guard, so **no list is sealed for 21 Nov**; a disclosure of that day is outside this test (the next night's lookback collects it, unsealed). Chosen over a weekday on purpose: a Saturday list is most likely empty. Sealed days: **15-16, 19-20 and 22-25 Nov**. Nothing else changes.

## Note 1 (2026-11-16, written before the day)
On Saturday 21 Nov 2026 the capital-increase pilot pull runs in the daytime (`docs/capital_increase_rule.md`, Note 1). The nightly job skips that night under the one-pull-per-day guard, so **no list is sealed for 21 Nov**; a disclosure published that day is outside this test. Decided in advance, not after seeing any result. The sealed days are therefore 15-20 and 22-25 Nov. Nothing else changes.

## Note 2 (2026-11-16, before any price after the first seal exists; how the code reads this rule)
`scripts/forward_score.py` was written from this rule and synthetic prices (20 self-test checks). Points the rule left open, fixed now:
- **p-value:** (1 + shuffles with a difference at least as large as observed) / 10,001, so it is never 0 and ties count against the claim.
- **Trading days** are the days with an `XU100` bar. **No price** also covers a disclosure without a symbol.
- **`INCOMPLETE`** (nothing scored) until `XU100` has a bar on or after 2026-11-26. The score is computed once and kept in `data/forward_score.txt`; a second call only prints it.
- **Integrity:** a day whose snapshot differs from its first logged hash is dropped and the line says `BROKEN`; days without a seal (21 Nov, Note 1) are listed. The script prints the 16-character prefixes; comparing them with the phone alerts is Feyza's step.
- The decision comes only from the t1 pass; the reaction-day pass is printed next to it.

## Note 3 (2026-11-18 00:10, before any price after the first seal exists; an unplanned gap)
The Mac was switched off at 23:43 on 17 Nov 2026, so the nightly job did not run and **no list was sealed for 17 Nov**. This was not planned and not chosen; it is recorded before any outcome exists (prices are pulled only after 26 Nov). Treated exactly like 21 Nov (Note 1): a disclosure published on 17 Nov is outside this test; the 3-day lookback of the 18 Nov night collects it, unsealed. No list is sealed by hand afterwards, because a list made later is not a sealed prediction. The sealed days are therefore 15-16, 18-20 and 22-25 Nov. The scorer already lists days without a seal; nothing else changes.

## Note 4 (2026-11-18 07:55, before the pull and before any outcome exists; replaces Note 1)
The capital-increase pull moved from Sat 21 Nov to Wed 18 Nov daytime (`docs/capital_increase_rule.md`, Note 1b), to finish the project early. The nightly job skips the night of 18 Nov under the one-pull-per-day guard, so **no list is sealed for 18 Nov**; 21 Nov is sealed again. Cost, stated before: a weekday with real items is replaced by a Saturday that is probably empty. The 3-day lookback of the 19 Nov night collects 17-18 Nov, unsealed. Sealed days: **15-16 and 19-25 Nov** (9 days, as before). Nothing else changes.

