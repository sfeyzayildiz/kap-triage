# System card: KAP Disclosure Triage Assistant (KAP Bildirim Önceliklendirme Asistanı)

One page, in the spirit of model cards and model-risk documentation. Version: main as of 2026-11-22. Details: `docs/results.md` (numbers), `docs/known_issues.md` (what we got wrong), `docs/architecture.md` (how it works).

## Purpose
Morning triage of KAP "Yeni İş İlişkisi" (new business relationship) disclosures for a brokerage equity analyst: which ones to read first, why, and how reliable the extracted facts are. Every item carries its KAP link.

**Intended use:** a first look and a ranking aid; the analyst reads the KAP text before any decision.
**Not intended for:** investment advice, price prediction, other disclosure types, unattended automated trading or publication of the extracted numbers.

## Data
- Source: Matriks API (licensed, used with permission): new-business records (prod), KAP disclosure texts (test environment, counts match prod), daily price bars, sector labels. About 1,290 disclosures since 2024-10-31, 1-2 new per day.
- Collected once a night on one Mac (one pull per day, enforced in code). Data never leaves the machine: local models, no external services, nothing in git or in the Docker image.

## How it works (short)
A local LLM (`gemma4:e4b`, Ollama) extracts the facts (amount, currency, counterparty, duration, revision, related party). Code checks contradictions and flags them (`needs_review`) instead of fixing them; a layered defence checks the amount against Matriks' own record and the sentence it came from. Code computes the importance score, the ordering (long contract first, then amount), the price reaction against XU100, the history and similar disclosures (embedding search + reranker). The LLM never writes a number or a link shown to the analyst.

## Measured performance (rule written before each run; held-out unless noted)
| What | Result |
|---|---|
| Silent errors in amount / currency (wrong, not flagged) | 1/100 on unseen Set C (95% upper bound 4.7%); 11/100 sent to a human. A second run: again 1/100 (a different item); 3/100 extractions changed between runs |
| Sent to a human in live use (all layers: code checks, vendor cross-check, source judge, two readings) | 20-22% of disclosures (Set D, 50 new texts; 21-24% on its random 38, the other 12 are a census of one text type); about 78-80% go straight through |
| Source sentence shown on the card | it was the amount's source in 32/32 checked saved cards (95% upper bound on errors 8.9%) |
| Without an LLM, same set | the strongest regex in the repo (written for the code checks): 25/100 silent errors |
| Hidden instruction in the disclosure text (amount attack) | silent successes 9 → 0 of 18 with the layered defence; 3/200 extra flags on real texts |
| Ordering vs the author's blind choice (not an external analyst), 12 new days | top pick 11/12 (old score 5.5); AUC 0.877 |
| Search (embedding + rerank), 20 questions | right disclosure in the top 5: 20/20; at rank 1: 17/20 |
| Agent routing with company names, 20 questions | intended link in the top 5: 18/20 |
| Relative periods ("geçen hafta", "son 3 ay"), 15 new questions | exact 10/10; false period 1/5; wrong fires 0/9 on 205 earlier questions |
| Desk e-mails (n8n, local mail), all 15 saved days | 43 items: 0 lost, 0 duplicated, 0 wrong desk, 0 amount leaks |
| Speed | extraction about 15 s per reading, about 31 s per disclosure in the nightly list (two readings); everything else under 0.01 s; a company brief about 18 s |

## Known limits
- Fields other than amount and currency were measured once on 50 Set C texts (13 Nov): long contract 3/50 errors (kept), foreign counterparty 7/50 and related party 5/50 (both switched off in the score).
- Which items enter "Önce bak" (look first) is decided by the v1 importance level (high = score ≥ 4, weights set by judgment) or a review flag; ordering v2 changes only the order inside each group. The score did not beat sorting by amount.
- Post-hoc (not a rate): on the 34 saved cards checked for the source sentence, 2 amounts were wrong, 1 flagged and 1 not, so one silent error was seen in live lists (known_issues B13). The measured rate stays 1/100 (Set C).
- One person labeled the gold data and wrote most questions; no second rater (planned, cancelled), so no agreement number.
- Small test sets, wide bounds. Single disclosure type in production; two more types were piloted once each and not adopted: capital increases (18 Nov: 0/30 silent, 16/30 flagged) and stake acquisitions and sales (19 Nov: 2/30 silent, 6/30 flagged). The data-vendor auditor (Matriks record vs. KAP text) reached 6/14 strict precision, below its 50% bar, so it is a hand-run report tool, not part of the nightly path. Nightly, not real time.
- The chat cannot always say "the data cannot answer this"; an out-of-scope question with a company name can get an unrelated card (the guided form avoids it; three scope guards failed their bars).
- Desk = Matriks sector; whether that desk is the right recipient is not measured.
- Search's typical miss is the right company's wrong disclosure; a card belongs to the first hit only.
- Prices are unadjusted (a 22% jump rule guesses splits). Weekly themes are weak (template effect).
- The injection test used one attack wording, and only instructions written into the text. Drafting that hides or buries information (for example in the middle of a long text) was not tested, and the effect of an amount's position in a long text was not measured.
- The revenue ratio uses Matriks prod revenue (balance sheet chosen by Matriks); its data-quality gates passed (`docs/revenue_ratio_rule.md`), its weights are set by judgment.
- The money regex now reads "ABD Doları" (`amount_checks_v2.py`, no flag changed on any measured set); other spellings ("US Doları") are still not read.
- The agent does not support two-company comparisons; relative periods outside the phrase table ("önceki hafta", "son günlerde") are not read.
- Disclosure texts come from the Matriks test environment (same counts as prod); new-business data from prod.

## Human oversight
Flagged items show the reason and a confirm / reject step; decisions are logged with the reasons at review time (first real use: 3 of 6 flags were real errors; the panel page "Kontrol geçmişi" counts decisions per flag type). Every answer links to the KAP source.

## Security and privacy
Disclosure text is treated as untrusted input (injection tested and defended); the panel binds to the local machine, sends no scripts (strict CSP) and escapes all text. Desk e-mails go to a local mail server, carry no amounts, and n8n / Mailpit run with telemetry off. No personal data is processed.

## Maintenance
Self-tests on every change (CI); nightly alerts (OK / FAILED / SKIPPED) and postmortems in [`PROJECT_NOTES.md`](PROJECT_NOTES.md); a pull guard enforces the provider's rate rule. Any change to a measured part needs a new rule and a new measurement.
