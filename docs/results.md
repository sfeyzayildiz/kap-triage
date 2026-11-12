# Results on one page

Every row below was decided by a rule committed before the run (`docs/*_rule.md`, or the dated entry in `PROJECT_NOTES.md`). "Dev" = used to build or choose. "Held-out" = not seen before the run. Rejected results are listed too. Last updated 2026-11-12.

## Extraction (the core)
| what | set | result | decision |
|---|---|---|---|
| Prompt v1 / v2, adjudicated amount | Set A (dev, 100) | 96/99 both | v1 = v2; error analysis led to rules R1-R5 |
| Frozen prompt v3 | Set B (held-out, 100) | 4 silent errors, 8 flagged | **FAIL** |
| v3 + code checks from the Set B error analysis | Set C (held-out, 100) | **1 silent error (95% upper 4.7%), 11 flagged** | **PASS** |
| Without an LLM: best regex / regex + all code checks | Set C | 25 / 23 silent errors out of 100 | an LLM is needed |
| Other model families (qwen3:14b, Turkish-Gemma-9b), plus e4b / 26b without thinking | Set A | 0/15, 5/27, 5/8, 9/4 (silent / flagged) vs. e4b with thinking 0/10 | e4b stays; report only |

## Search (RAG retrieval)
| what | set | result | decision |
|---|---|---|---|
| 3 embedding models | dev (59 answerable) | `turkish-e5-large` recall@5 0.864, @1 0.729 | chosen (tie rule, then the smaller model) |
| e5-large, embedding only | Set C questions (held-out, 48) | recall@5 0.875, @1 0.667 | below 0.85 at rank 1, so a hybrid was tried next |
| BM25 / hybrid (RRF) | Set D (20) | top 1 16 / 15 vs. embedding 15 | **rejected** (bar not met) |
| + cross-encoder rerank (`bge-reranker-v2-m3`) | Set D (20) | top 1 15 → **17**, top 5 **20/20**, +0.7 s | **adopted** |
| Rerank depth K = 10 / 20 / 50 | dev | same @1 and @3; @5 54 / 55 / 55 | K = 20 stays |
| Course-style chunks 420/80 | dev | rank 1 43 → 42 (with rerank) | **rejected**, one document per disclosure |

## Security (prompt injection)
| what | set | result | decision |
|---|---|---|---|
| One appended sentence, no defence | Set C texts 1-20 | amount changed 20/20, **14 silent** | the biggest open risk found |
| Text-pattern checks | sealed attacks, texts 21-40 | silent 10 → 10; 24/200 false alarms | **rejected** |
| Matriks cross-check alone | texts 41-60 | silent 11 → 2; 2/200 false alarms | **rejected** (bar ≤ 1) |
| Layered: Matriks cross-check + source-sentence judge | texts 61-78 | silent **9 → 0** (95% upper 15.3%); 3/200 false alarms | **adopted** |

## Agent (LangGraph)
| what | set | result | decision |
|---|---|---|---|
| LLM router vs. keyword router | 20 questions | 17/20 vs. 9/20 | LLM kept |
| Detail card v1 (ticker required) | 10 questions | routed 5/10, right disclosure 3/10 | switch **removed** |
| Router v2: company names, dates, card | 20 questions | intended link in the top 5: 11 → **18/20**; cards right 12/16 | **adopted** |
| Quantities on the card (code) | 15 texts | 10/15 lists right (bar 14) | **off** |
| Cited answers v1 (e4b) | dev 66 | citations right 44/45, but 3 of 7 unanswerable questions answered | **not adopted** |
| Cited answers v3 / v4 (gates, gemma4:26b) | dev 66 | v4: 51/54 shown, 5/7 negatives (bar 6/7) | **not adopted**; held-out set still unused |
| Company brief (multi-step flow) | 10 questions | routed 9/10, ticker 10/10, review yes 9/10, median 18.5 s | **adopted** |
| Scope guard (fixed word list) | 20 new + 185 earlier questions | blocked 7/10 out-of-scope (bar 9); false blocks 0/10 and 1/185 | **off** |

## Scoring, desks, themes
| what | set | result | decision |
|---|---|---|---|
| Revenue ratio data gates | prod archive | semantics 99.2%, coverage 84%, scale 0.6% | **on** |
| Importance score vs. the analyst's blind look-first choice | 10 unseen days, 49 disclosures, 47 pairs | AUC 0.681 (random p95 0.670) = amount only 0.681; top pick amount 7/10, score 3/10 | **AMOUNT_EXPLAINS**, weights unchanged |
| Ordering v2 (dev choice: long contract, then amount) | 12 new days, 52 disclosures, 53 pairs | AUC 0.877 vs v1 0.792; top pick 11 vs 5.5 of 12; amount alone 0.953, 12/12 | **adopted** (amount alone was not the dev choice) |
| Clustering k = 27 vs. Matriks sectors | 1288 disclosures | company-level ARI 0.144 vs. shuffled p99 0.032; ARI vs. company 0.298 | reflects sector, weakly; desks use the sector label, clusters only for the weekly themes page |
| Analyst review of flags in the panel | one day | 3 of 6 flags were real extraction errors | first real use, small sample |

## Speed and data
- Extraction: median 14.6 s, p90 20.6 s per disclosure; every other stage 0.003 s; a busy day takes about 3 minutes overnight.
- Abnormal price moves: 92 of 1378 (6.7%) had a new-business disclosure in the 4 days before, so for most moves the agent says the cause may be elsewhere.

## Exploration (not a measurement)
- Red team on the chat agent (16 questions, Feyza): 7 right. Failures: out-of-scope and unanswerable questions get an unrelated card (the scope guard above did not pass), counterparty taken as the company, "geçen hafta" not parsed, two-company questions. The name-matching failure could not be reproduced.

## What these numbers do not show
- Test sets are small (100 / 48 / 20 / 18 items), so the bounds are wide.
- One analyst built the system, labeled the gold data and wrote most of the questions.
- Agreement with the analyst is not a market outcome. Nothing here predicts price moves.
