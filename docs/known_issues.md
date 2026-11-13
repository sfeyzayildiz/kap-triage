# Where we were wrong, and what we did about it

Written 2026-11-12 after a review of the whole project (PROJECT_NOTES.md, docs/results.md, the code). Each item is either **fixed**, **fixable** (planned, with its own rule), or **accepted** (a limit we state). Nothing here is new data; it collects what the notes already record.

## A. Measurement and method
| # | What was wrong or weak | Status |
|---|---|---|
| A1 | The dev set made us overconfident: 0/100 silent errors on Set A, then 4/100 on the first held-out set (Set B, FAIL). | **Fixed by process:** every decision since then uses a rule written before the run and a set not seen before. |
| A2 | The code checks were designed from the Set B errors, so their Set B number (1/100) was leaky. | **Fixed:** measured again on unseen Set C (1/100, 95% upper bound 4.7%). |
| A3 | Importance score v1 was shipped as the ranking without any test. When tested against the analyst, it was no better than sorting by amount (AUC 0.681 both). | **Fixed:** ordering v2 measured on 12 new days and adopted (top pick 11/12 vs 5.5). |
| A4 | On that round, amount alone did better than the adopted key (12/12). We kept the dev choice; switching on the test round would be tuning. Also the analyst knew round 1's result before labeling round 2, which may have pulled her labels towards amount. | **Accepted**, stated. Amount-only as the order would need its own rule and a new round. |
| A5 | The adopted ordering puts long contracts first, but the duration field it relies on was never measured for accuracy (only amount and currency were). Counterparty origin and related party, used in the score, are also unmeasured. | **Fixable:** label duration / origin on a new set. Until then: stated limit. |
| A6 | One person built the system, labeled the gold data, wrote most questions and reviewed the answers. No second rater, no agreement number. | **Accepted**, stated. A second labeler on a sample would be the first step. |
| A7 | Test sets are small (100 / 48 / 20 / 18), so bounds are wide; the rerank was adopted exactly at its bar (17/20), and on dev it fixed and broke 5 each at rank 1. | **Accepted**, stated with the bounds. |
| A8 | Detail card v1 assumed analysts write tickers; 0/10 did, so it failed (5/10 routed). | **Fixed:** name table (router v2, 18/20) and the guided form. |
| A9 | Several things were tried and did not pass their bars: cited answers (v1, v3, v4), quantities on the card, text-pattern injection checks, the Matriks cross-check alone, the word-list scope guard, BM25 / hybrid, chunking. | **Accepted**, reported as results, not hidden. |

## B. The product
| # | What is wrong or weak | Status |
|---|---|---|
| B1 | In the chat, an out-of-scope question that names a company and a detail ("ASELS temettü ne kadar?") gets an unrelated disclosure card. Scope guard v2 (router intent `out_of_scope`) blocked 10/10 out-of-scope but also 29/185 earlier in-scope questions (bar 3) → off (13 Nov). | **Accepted** for the final: both guards failed their bars. The guided form avoids it; in the demo, no such questions. A v3 would need a different design (e.g. a check only after the router said `company`), its own rule and new questions. |
| B2 | Relative periods ("geçen hafta") are not parsed; two companies in one question → only the first; a counterparty's name can be taken as the company. | **Fixable** (relative periods planned); the other two **accepted** for now. The form avoids all three. |
| B3 | The system rarely says "the data cannot answer this": unanswerable questions still get a list or a card. | **Accepted**; cited answers that abstain did not pass their bar. |
| B4 | Search's typical miss: right company, wrong disclosure (all 16 rank-1 misses on Set C). A card can therefore show the wrong disclosure of the right company. | **Accepted**, stated on every card ("the card belongs to the first hit; read the KAP text"). |
| B5 | `MONEY_RE` misses "ABD Doları" (10 of 81 Set B amounts), so some currency checks do not fire. | **Fixable:** `amount_checks` v2, needs a new labeled set (frozen v1 stays). |
| B5b | Live use, 12 Nov morning list (Feyza's review): 2/2 flagged disclosures had wrong extractions, both caught by the flag (none silent). Types: mixed currency / split amounts not read (importance 0); a TL revision where only the FX part was scored. | **Fixable** with B5 (same family); not changed from these two cases, a v2 must be measured on a new labeled set. |
| B6 | Weekly themes: about half of the theme words are generic; clusters follow company templates more than sectors. | **Accepted**, stated on the page; desks use the Matriks sector label. |
| B7 | Prices are unadjusted; splits are guessed by a 22% jump rule. EFORC has no prices and no sector. | **Accepted**, stated. |
| B8 | Disclosure texts come from the Matriks test environment, amounts from prod; revenue uses Matriks' choice of balance sheet. | **Accepted**, stated; counts match prod. |

## C. Operations and our own process
| # | What went wrong | Status |
|---|---|---|
| C1 | Two pulls on 10 Nov and again on 11 Nov, against Matriks' one-pull-per-day rule (the job was resumed in the same block as other commands). | **Fixed in code:** `pull_guard` refuses a second pull on the same day; the resume command is given alone. |
| C2 | Nightly runs of 6-7 Nov failed on a DB lock; the first live morning list failed on a missing package in the deploy environment. | **Fixed:** lock logging and retries; `pip install` after every deploy pull; `deploy_check`. |
| C3 | Agent output with Matriks amounts was pasted into the chat with the assistant twice (10 Nov), against our data rule. | **Fixed by habit:** only counts and short observations come back. |
| C4 | The assistant (Claude) gave wrong diagnoses twice on 12 Nov (name matching, review statistics) and once blocked a branch checkout with its own worktree. | **Fixed:** each corrected in the notes the same day; rule: reproduce before fixing, close own worktrees before handing over. |
| C5 | "Today" questions answered "no disclosures" before the night's collection. | **Fixed:** shows the last collected day with a note. |

## What this means for the presentation
Say A1-A3 as the story (it is the strongest part), A4-A6 and B1-B4 as limits before anyone asks, and C1 as an honest process slip that we turned into code.
