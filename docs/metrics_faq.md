# Metrics cheat sheet (for questions from the instructor or a company)

Every number here was measured with a rule written before the run, unless marked. "dev" = the set used to build or choose; "held-out" = never seen before the run. Updated 2026-11-10.

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

## Agent routing
- 20 questions by Feyza: LLM router **17/20** vs. keyword router 9/20 → LLM kept. Ticker right 4/8 (2 wrong tickers from company names: known risk).

## Security (prompt injection, red team)
- Amount attack without defence: 20/20 success, 14 silent (Set C texts 1-20).
- Layered defence (adopted): silent attacks **9 → 0** on 18 new texts (95% upper bound 15.3%), 3/200 extra flags on real texts.

## Generation (cited answers): tried, not adopted
- Citations right 45/46 when shown; but 3 of 7 unanswerable questions answered (bar ≥ 5/7 stay silent). Median 3.4 s. Off.

## Human in the loop
- Panel, one demo day: 6 flags reviewed on KAP, 3 were real extraction errors.

## Speed
- Extraction median 14.6 s per disclosure (p90 20.6 s); all other stages 0.003 s; busy day ~3 min overnight. Routing 3.2 s.

## Data
- ~1288 disclosures since 2024-10-31 (new-business data back to 2024-01), 1-2 new per day; 129 symbols with deals.
- Revenue ratio: on; coverage 84% of disclosures; data check 99.2% consistent.

## Not measured (say it before they ask)
- Importance score weights (judgment). Document-to-document similarity. Clustering (waits for sector labels). Test sets are small (100 / 48 / 20 / 18), so bounds are wide.
