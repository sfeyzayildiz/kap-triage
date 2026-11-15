# Metrics cheat sheet (for questions from the instructor or a company)

Every number here was measured with a rule written before the run, unless marked. "dev" = the set used to build or choose; "held-out" = never seen before the run. Updated 2026-11-12. All results on one page: `docs/results.md`.

## Search (RAG retrieval)
Hit@k = recall@k = share of answerable questions whose correct disclosure is in the top k.

| system | set | Hit@1 | Hit@3 | Hit@5 |
|---|---|---|---|---|
| **live: e5-large + cross-encoder rerank** | Set D, 20 hand-written (held-out for the rerank decision) | 17/20 = 0.85 | **20/20 = 1.00** | 20/20 = 1.00 |
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
- History: dev 0/100 → held-out Set B 4/100 (FAIL) → error analysis → code checks → Set C 1/100.
- **Without an LLM (same Set C, same gold):** best regex 25/100 silent errors (63/100 found an amount at all); regex + all code checks still 23/100 silent. The LLM system: 1/100. Earlier small number: regex 12/15 vs LLM 15/15 (dev).
- Ops terms: escape rate 1%, straight-through rate 89%.

- Model families on Set A, same frozen prompt and scoring (12 Nov, report only): e4b thinking on **0 silent / 10 flagged**; qwen3:14b thinking off 0 / 15 (same raw 89/100, slower to flag-free parity: it flags more); Turkish-Gemma-9b-T1 5 / 27; e4b thinking off 5 / 8; 26b thinking off 9 / 4; qwen3:14b thinking on did not finish (thinking exhausts the token budget). Three families, no one beats e4b thinking on; remaining errors are definition questions, not capacity.

## Agent routing
- 20 questions by Feyza: LLM router **17/20** vs. keyword router 9/20 → LLM kept. Ticker right 4/8 (2 wrong tickers from company names: known risk).
- Name → ticker in code (router v2): intended link in top 5 **18/20** (v1 11/20). Adopted.
- Company brief (multi-step LangGraph: latest → history → reaction → similar → compose), 10 questions: routed **9/10**, ticker **10/10**, review yes **9/10**, median **18.5 s** (14 s of it is the extraction). Adopted.
- Red team (exploration, 16 questions by Feyza): 7 right. Scope guard (word list before the router): blocked **7/10** out-of-scope (bar 9), false blocks 0/10 new and 1/185 earlier → off. Repeatability: a second run of Set C changed amount/currency on 3/100 (temperature 0 is not fully deterministic), but again 1/100 silent (a different item), flagged 12%; say "1/100 in each of two runs". Set D (50 new, 15 Nov): a "two readings disagree → review" flag added **0** new flags over run a and caught run b's only silent error (1/1); with Set C that is 3 of 3 silent errors among disagreeing items (Set C post-hoc) → adopted for the nightly list (twice the extraction time, ~31 s per disclosure). Live flag rate on Set D 20-22% (all layers). MCP: the agent's tools are an MCP server (stdio, read-only, local clients only); transport exact 10/10, overhead 0.011 s; a free tool-calling agent picked the right tool 12/16, our constrained router 14/16. Drift after Set C (40 newer disclosures, Matriks as reference, not gold): agreement 87.5% vs 92.3% on Set C, bar ≥ 82.3% → no drift seen; 4 of the 5 misses returned no amount. Other extracted fields (50 Set C, bar ≤ 3 errors): long contract 3/50 → kept in ordering v2; foreign counterparty 7/50 and related party 5/50 → removed from the score (the model misses them, never invents them). Desk routing (n8n sends one e-mail per sector desk to a local Mailpit; desk and text decided in code): 15 days, 43 items, 33 e-mails, **0 lost / 0 duplicated / 0 wrong desk / 0 amount leaks**, 0.2 s per day → adopted. Says nothing about whether the sector desk is the right recipient. Relative periods ("geçen hafta", "son 3 ay"; code, not the LLM): exact **10/10**, false period 1/5, wrong fires 0/9 on 205 earlier questions → adopted. Scope guard v2 (router may say out of scope): blocked **10/10** but falsely blocked **29/185** earlier in-scope questions (bar 3) → off. The trade-off in one line: a word list misses wordings, a small-model judge over-blocks. Say it: an out-of-scope question with a company name can still get an unrelated card.

## Security (prompt injection, red team)
- Amount attack without defence: 20/20 success, 14 silent (Set C texts 1-20).
- Layered defence (adopted): silent attacks **9 → 0** on 18 new texts (95% upper bound 15.3%), 3/200 extra flags on real texts.

## Generation (cited answers): tried, not adopted
- Citations right 45/46 when shown; but 3 of 7 unanswerable questions answered (bar ≥ 5/7 stay silent). Median 3.4 s. Off.

## Importance score vs. the analyst (blind, report only)
- 10 unseen days, 49 disclosures, Feyza labeled blind, 47 within-day pairs. AUC score **0.681** (random p95 0.670, p 0.042), amount-only **0.681**, margin 0 → `AMOUNT_EXPLAINS`: better than chance, but sorting by amount does as well. Day's top pick: amount 7/10, score 3/10 (random 2.1). Level high: 9 of 11 were her picks, but it caught 9 of her 29.

- **Ordering v2 (adopted, 12 new days):** long contract first, then amount: AUC **0.877** vs v1 0.792, top pick **11/12** vs 5.5. Amount alone did even better (0.953, 12/12) but was not the dev choice; switching on the test round would be tuning.

## Human in the loop
- Panel, one demo day: 6 flags reviewed on KAP, 3 were real extraction errors.

## Speed
- Extraction median 14.6 s per disclosure (p90 20.6 s); all other stages 0.003 s; busy day ~3 min overnight. Routing 3.2 s.

## Data
- ~1288 disclosures since 2024-10-31 (new-business data back to 2024-01), 1-2 new per day; 129 symbols with deals.
- Revenue ratio: on; coverage 84% of disclosures; data check 99.2% consistent.

## Not measured (say it before they ask)
- Importance score weights (judgment; the order was checked once against one analyst, see above, weights not fitted). Document-to-document similarity. Test sets are small (100 / 48 / 20 / 18), so bounds are wide.
