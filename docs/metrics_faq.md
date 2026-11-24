# Metrics cheat sheet (for questions from the instructor or a company)

Every number here was measured with a rule written before the run, unless marked. "dev" = the set used to build or choose; "held-out" = never seen before the run. Updated 2026-11-24. All results on one page: `docs/results.md`.

## Search (RAG retrieval)
Hit@k = recall@k = share of answerable questions whose correct disclosure is in the top k.

| system | set | Hit@1 | Hit@3 | Hit@5 |
|---|---|---|---|---|
| **live: e5-large + cross-encoder rerank** | Set D, 20 hand-written (second use, after the BM25 / hybrid test) | 17/20 = 0.85 | **20/20 = 1.00** | 20/20 = 1.00 |
| live: e5-large + rerank | dev, 59 | 43/59 = 0.73 | 52/59 = 0.88 | 55/59 = 0.93 |
| e5-large, embedding only | **Set C, 48 (held-out)** | 32/48 = 0.67 | 37/48 = 0.77 | 42/48 = 0.875 |
| e5-large, embedding only | Set D, 20 | 15/20 | 19/20 | 19/20 |
| BM25 only / hybrid (RRF) | Set D, 20 | 16 / 15 | 17 / 17 | 20 / 20 |
| bge-m3 / qwen3-embedding-0.6b (embedding only) | dev, 59 | 40 / 39 | 51 / 46 | 53 / 50 |
| rerank depth K=10 / 20 / 50 (ablation, same session) | dev, 59 | 43 / 43 / 43 | 52 / 52 / 52 | 54 / 55 / 55 (0.31 / 0.72 / 1.79 s) |
| course-style chunks 420/80, embedding only / + rerank | dev, 59 | 39 / 42 | 48 / 51 | 53 / 53 |

- Hit@3 was computed afterwards from the stored ranks of these runs (no new run); the decisions used @1 and @5.
- Rerank on Set C was not run (Set C was measured once, before the rerank existed).
- Typical miss: right company, wrong disclosure.
- Why K=20: K does not change @1/@3; 10→20 gains 1 at @5; 50 only costs time. Why no chunking: chunks lose 1-4 at rank 1 and the same-company confusion grows (16→20); texts are short (median 52 words).
- Pipeline: embedding top 20 → cross-encoder rerank → top 5; +0.7 s per question.

## Extraction (the core)
- Held-out Set C (100): **1 silent error** (wrong amount/currency, not flagged), 95% upper bound **4.7%**; 11/100 sent to a human. PASS.
- **How a silent error is counted** (the scoring script is not in this repository, see known_issues E4; this is its definition):
  - Reference: the blind human label (gold) of each text. Gold rows marked "needs review" stay in the set.
  - Flagged = the system sent the item to a human (any review reason, or a run error). A flagged item is never a silent error.
  - Silent error = not flagged, and one of: the amount differs from the gold amount by **more than 1% (relative)**; the currency differs; the model gave an amount where gold has none (fabricated); the model gave none where gold has one (missed).
  - Levels, all from the same run: level 0 = the frozen extraction's review reasons; level 1 = + `currency_unclear`; level 2 = + `amount_is_projection` and `cumulative_total`. The Set C number is level 2 (`docs/set_c_plan.md`).
  - Upper bound: one-sided 95% Clopper-Pearson (1 of 100 → 4.7%).
- History: dev 0/100 → held-out Set B 4/100 (FAIL) → error analysis → code checks → Set C 1/100.
- **Without an LLM (same Set C, same gold):** the strongest regex in the repo (written for the code checks, not as an extractor) 25/100 silent errors (63/100 found an amount at all); regex + all code checks still 23/100 silent. The LLM system: 1/100. Earlier small number: regex 12/15 vs LLM 15/15 (dev).
- Ops terms: escape rate 1%. Straight-through rate: 89% for extraction + code checks alone (Set C, level 2); about **78-80% for the live pipeline** with the Matriks cross-check and the source judge (Set D flagged 20-22%; 21-24% on its random 38). The live figure is the one that applies to the panel.

- Model families on Set A, same frozen prompt and scoring (12 Nov, report only): e4b thinking on **0 silent / 10 flagged**; qwen3:14b thinking off 0 / 15 (same raw 89/100, slower to flag-free parity: it flags more); Turkish-Gemma-9b-T1 5 / 27; e4b thinking off 5 / 8; 26b thinking off 9 / 4; qwen3:14b thinking on did not finish (thinking exhausts the token budget). Three families, no one beats e4b thinking on; remaining errors are definition questions, not capacity.

## Agent routing
- 20 questions written by me: LLM router **17/20** vs. keyword router 9/20 → LLM kept. Ticker right 4/8 (2 wrong tickers from company names: known risk).
- Name → ticker in code (router v2): intended link in top 5 **18/20** (v1 11/20). Adopted.
- Company brief (multi-step LangGraph: latest → history → reaction → similar → compose), 10 questions: routed **9/10**, ticker **10/10**, passed the manual review **9/10**, median **18.5 s** (14 s of it is the extraction). Adopted.
- **Red team** (exploration, 16 questions written by me): 7 right.
- **Scope guards** (all three off). The trade-off in one line: a word list misses wordings, a small-model judge over-blocks, wherever it sits (v2 29/185, v3 28/185). Limit: an out-of-scope question with a company name can still get an unrelated card.
  - v1, word list before the router: blocked **7/10** out-of-scope (bar 9), false blocks 0/10 new and 1/185 earlier → off.
  - v2, the router may say out of scope: blocked **10/10** but falsely blocked **29/185** earlier in-scope questions (bar 3) → off.
  - v3 (19 Nov), router untouched, a separate yes/no judge only where a card or list would be shown: 10/10 out-of-scope got no card, but **28/185** earlier questions blocked (bar 3) → off.
- **Repeatability:** a second run of Set C changed amount/currency on 3/100 (temperature 0 is not fully deterministic), but again 1/100 silent (a different item), flagged 12%; that is, 1/100 in each of two runs.
- **Two readings (Set D, 50 new, 15 Nov):**
  - A "two readings disagree → review" flag added **0** new flags over run a and caught run b's only silent error (1/1); with Set C that is 3 of 3 silent errors among disagreeing items (Set C post-hoc) → adopted for the nightly list (twice the extraction time, ~31 s per disclosure).
  - Live flag rate on Set D 20-22% (all layers).
  - Bounds: 12 of the 50 are a census of the "ABD Doları" zone, so the bounds use the random 38, not 0/50: run a 0/38 (95% upper 7.6%), run b 1/38 (11.9%).
  - Set C (level 2) and Set D (live, with the Matriks record) are two systems; do not pool them.
- **MCP:** the agent's tools are an MCP server (stdio, read-only, local clients only); transport exact 10/10, overhead 0.011 s; a free tool-calling agent picked the right tool 12/16, our constrained router 14/16 (16 dev questions the router was built on, so the result reads "not better", not "worse").
- **Drift after Set C** (40 newer disclosures, Matriks as reference, not gold): agreement 87.5% vs 92.3% on Set C, bar ≥ 82.3% → no drift seen; 4 of the 5 misses returned no amount.
- **Other extracted fields** (50 Set C, bar ≤ 3 errors): long contract 3/50 → kept in ordering v2; foreign counterparty 7/50 and related party 5/50 → removed from the score (the model misses them, never invents them).
- **Desk routing** (n8n sends one e-mail per sector desk to a local Mailpit; desk and text decided in code): 15 days, 43 items, 33 e-mails, **0 lost / 0 duplicated / 0 wrong desk / 0 amount leaks**, 0.2 s per day → adopted. Says nothing about whether the sector desk is the right recipient.
- **Relative periods** ("geçen hafta", "son 3 ay"; code, not the LLM): exact **10/10**, false period 1/5, wrong fires 0/9 on 205 earlier questions → adopted.

## Security (prompt injection, red team)
- Amount attack without defence: 20/20 success, 14 silent (Set C texts 1-20).
- Layered defence (adopted): silent attacks **9 → 0** on 18 new texts (95% upper bound 15.3%), 3/200 extra flags on real texts.

## Generation (cited answers): tried, not adopted
- Citations right 44/45 when shown (v1); but 3 of 7 unanswerable questions answered (bar ≥ 5/7 stay silent). Median 3.4 s. Off.

## Importance score vs. the author's blind choice (report only)
- 10 unseen days, 49 disclosures, I labeled blind, 47 within-day pairs. AUC score **0.681** (random p95 0.670, p 0.042), amount-only **0.681**, margin 0 → `AMOUNT_EXPLAINS`: better than chance, but sorting by amount does as well. Day's top pick: amount 7/10, score 3/10 (random 2.1). Level high: 9 of 11 were my picks, but it caught 9 of my 29.

- **Ordering v2 (adopted, 12 new days):** long contract first, then amount: AUC **0.877** vs v1 0.792, top pick **11/12** vs 5.5. Amount alone did even better (0.953, 12/12) but was not the dev choice; switching on the test round would be tuning.

## Human in the loop
- Panel, one demo day: 6 flags reviewed on KAP, 3 were real extraction errors.

## Second disclosure type: capital increase pilot (18 Nov, held-out 30, rule first)
- Combined (form reader + LLM, disagreement flagged): **0/30 silent** (95% upper 9.5%), but **16/30 flagged** (bar 9) → **not adopted**. Median 21.2 s.
- Code-only form reader: 3/30 silent (upper 23.9%), 3 flagged, 24/30 resolved. LLM alone: 1/30 silent, 21 flagged, 8 resolved.
- "Could it be done without an LLM?" For this form-based type, code reads most of it; the LLM's value is the cross-check that catches the code's 3 silent errors (`LLM_ADDS`), at the price of many flags. For free-text "Yeni İş İlişkisi" it was the other way round (regex 25/100 silent).
- Pull to score in one day; the method transferred, the Matriks cross-check did not (no KAP link in that record; 11/20 rates found).

## Second disclosure type 2: stake acquisitions and sales (19 Nov, held-out 30, rule first)
- No Matriks tag for this type: pulled by the documented `headline` filter; a local check kept only real subject headlines (101 kept, 0 dropped, 72 companies).
- Combined: **2/30 silent** (95% upper 19.5%), **6/30 flagged** (bar 9), median 9.9 s → **not adopted** (bar: at most 1 silent). Form reader alone 4/30 silent, LLM alone 4/30, on different texts → combining halves them: **LLM_ADDS**.
- The lesson: both remaining errors are cases where the form reader and the LLM agree on the same wrong value. Companies sometimes fill the KAP form wrong (nominal capital in "Toplam Tutar", the seller in the target cell); a disagreement check cannot catch an error both readers share. The form alone is not reliable; the text must be read.
- Two pilots, one method, one day each: capital increase 0/30 silent but 16/30 flagged; stake deals 2/30 silent with 6/30 flagged. Neither passed its pre-written bar; both answered "LLM or not" the same way (the LLM adds as a cross-check).

## Data-vendor auditor: is a Matriks record wrong? (18 Nov, rule first, not adopted)
- 641 unseen disclosures, 14 records flagged (2.2%). Blind check of all 14 + 14 random controls: **6/14 record-text mismatches** by the strict definition (details offered to Matriks privately), 8 convention differences (VAT, TL equivalent, share), 0 consistent. Strict precision 43% (95% CI 18-71%) < bar 50% → **AUDITOR_OFF**.
- Random controls: 0/14 errors, so the list is far richer than random, but the bar was "one real error per two candidates" and it missed.
- Recall is low by design: records where our own checks are unsure are not audited (M1 on the gold sets: 1 of 9 record-text mismatches caught; the other 8 were in texts we also flag).
- In short: it was measured, it missed its pre-written bar, so it is a report tool, not a nightly feature.

## kap-kart: can anyone try it without your data? (19 Nov, rule first, adopted)
- Paste a public KAP text, get the card on your own computer (local model, nothing sent or saved). Same extraction code as the nightly job (copies checked by hash, 26/26 synthetic cases equal), minus the Matriks cross-check and the importance score.
- Leak scan before showing it: 3 rounds. Rounds 1-2 found one real disclosure fragment in the self-tests of two copied modules; fixed (synthetic text in v2; v1 is frozen, so its copy leaves the test out). Round 3: 0.
- Trap examples (clean, unclear currency, revision, hidden instruction): 12/12; median 27 s per card (two readings + judge).
- kap-kart has only the source-sentence layer. On the sealed attacks that layer alone also reached 0/18, mostly through amount_not_in_text, but only on texts that had a Matriks record; texts without one are not measured.

## Speed
- Extraction median 14.6 s per reading (p90 20.6 s); live the list reads each disclosure twice (Set D median 30.9 s for both); all other stages 0.003 s; busy day of 8 ~4-6 min overnight (computed). Routing 3.2 s.

## Data
- ~1288 disclosures since 2024-10-31 (new-business data back to 2024-01), 1-2 new per day; 129 symbols with deals.
- Revenue ratio: on; coverage 84% of disclosures; data check 99.2% consistent.

## Related work (20 Nov, public pages; their claims not verified)
- **"Others already do this?"** KAP summary sites (for example Borsacoo) summarise every disclosure; MCP servers for Borsa İstanbul (for example Borsa MCP) fetch KAP news and market data. We found no published accuracy number for either. This system extracts fields from one disclosure type and measures how often a wrong value is shown without a warning (Set C 1/100, upper 4.7%).
- **Structured data vendors** sell one record per material contract (Matriks `new_business` here; sec-api.io for SEC 8-K Item 1.01 in the US). Here the vendor record is a second opinion, and the text is read for every disclosure, including the 16% without a record.
- **Closest research:** [Dolphin et al., "Grounded Event Extraction from SEC 8-K Filings with a Fine-Grained Taxonomy", arXiv 2607.08346](https://arxiv.org/abs/2607.08346) (July 2026, SEC 8-K): every LLM label tied to a verbatim quote, graded again in a second pass; precision measured by an LLM judge (96% in the top quality band). Same two ideas here on a small scale (source sentence, separate judge call, second reading); accuracy here from blind human labels on unseen sets.
- **Drafting against AI tools** (Bloomberg Tax, May 2026): not covered by our injection test (instructions in the text only). Stated as a limit (known_issues B11).

## Not measured
- Importance score weights (judgment; the order was checked once against the author's blind choice, see above, weights not fitted). Document-to-document similarity. Test sets are small (100 / 48 / 20 / 18), so bounds are wide.

## Precise wording (after the 16 Nov review)
- **Matriks rate vs TCMB:** Matriks documents `tcmbExRt` as the previous day's closing central bank rate. Against that definition **972/1045 = 93.0%** are within 0.5% (bar 95% → "differs"); 913/1045 = 87.4% is the same-day bulletin, the rule's primary reference, not Matriks' definition. Median difference 0.16%. On 83 FX amounts the importance level changed 0 times; the rank order was not measured.
- **amount_checks v2 ("ABD Doları"):** the parser gap is closed; no flag changed on the 12 texts it can affect or on Set C. "Closed, no observed effect", not "fixed an error".
- **smtp-mcp:** 12 chosen cases with an automated approval on a local Mailpit: allowlist 7/7, declined 0 sent, accepted exactly 1, replay 0. It shows the mechanism, not a person's attention and not adversarial coverage. One high `npm audit` finding (nodemailer) is accepted after reading its source code. The LLM never calls this server.
- **Source sentence:** the first sentence in the text that contains the extracted number, verbatim. Measured 20 Nov on all 34 saved items with an amount: it was the amount's source in **32/32** (95% upper bound on errors 8.9%; 2 items had a wrong amount, so the question did not apply) → `SOURCE_OK`. In short: the shown sentence was the amount's source in 32 of 32 checked cards. Post-hoc: of those 2 wrong amounts, 1 was flagged and 1 was not (known_issues B13).
