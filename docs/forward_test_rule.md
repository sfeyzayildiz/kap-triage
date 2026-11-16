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

## Note 1 (2026-11-16, written before the day)
On Saturday 21 Nov 2026 the capital-increase pilot pull runs in the daytime (`docs/capital_increase_rule.md`, Note 1). The nightly job skips that night under the one-pull-per-day guard, so **no list is sealed for 21 Nov**; a disclosure published that day is outside this test. Decided in advance, not after seeing any result. The sealed days are therefore 15-20 and 22-25 Nov. Nothing else changes.
