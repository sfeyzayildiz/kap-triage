# Results on one page

Every row below was decided by a rule committed before the run (`docs/*_rule.md`, or the dated entry in `PROJECT_NOTES.md`). "Dev" = used to build or choose. "Held-out" = not seen before the run. Rejected results are listed too. Last updated 2026-11-19.

## What Matriks already gives, and what this system adds (existing measurements, no new run)
The first question a data company asks: Matriks sells a structured `new_business` record per disclosure, so why extract anything?
| | Matriks `new_business` record | This system |
|---|---|---|
| Coverage | **205 of 1,269 disclosures (16%) have no record**; Matriks creates one almost only when an amount is written (87% of matched texts mention an amount, 14% of unmatched) | every disclosure is read |
| Fields | amount, currency, a short description, ratios (deal / revenue, cumulative, market cap), the FX rate used | amount, currency **plus** revision and previous amount, related party, counterparty and origin, duration, subject, the **source sentence** with the amount marked, and review flags (`needs_review`) with reasons |
| Amount + currency agreement with our extraction | Set C 72/78 (92.3%); after Set C 35/40 (87.5%). Matriks is a reference here, not gold | — |
| Errors in the vendor record | 9 Matriks errors in our blind gold sets B/C/D (`docs/vendor_audit_rule.md`, M1); 6 real errors among 14 auditor flags in 641 newer disclosures (M2) | silent errors 1/100 on held-out Set C |
| FX rate | 93.0% within 0.5% of the official TCMB rate under Matriks' own convention (`docs/tcmb_rule.md`) | uses Matriks' rate for TL sizes; the difference is reported to Matriks |
| Flags what is uncertain | no | yes: unclear currency, projection, cumulative total, revision, injection, two readings disagree |

Reading: the vendor record is good where it exists (~92% agreement), but it is missing for 1 in 6 disclosures, carries no context fields (revision, related party, duration) and never says when it is unsure. The system reads the text for all of them, shows where each number comes from and flags what a person must check. The Matriks record is used as a second opinion (injection cross-check), not replaced.

## How to read these numbers
- **Bounds.** Small sets are reported with a one-sided 95% upper bound on errors: 1/100 → 4.7%; 0/38 → 7.6%; 0/30 → 9.5%; 0/18 → 15.3%. Differences of 1-2 items on 16-20 questions (rerank 15 → 17/20, router 17 → 18/20, constrained 14/16 vs free 12/16, ordering 11/12 vs amount 12/12) are **directional**, not statistically shown.
- **Held-out means unseen disclosures, not unseen companies.** No disclosure appears in two sets (A/B/C/D overlaps 0), but companies repeat: 35 of Set C's 59 companies also appear in Set B, 24 of Set D's 32 in Set C. Repeat issuers write similar boilerplate, so "held-out" is at disclosure level.
- **Labels and questions.** All gold labels, blind choices and evaluation questions are by one person (Feyza, the author), not by an external analyst; no LLM produced any gold label. Retrieval questions were written by her with the disclosure in view, which favours lexical overlap. No second annotator (cancelled) and no inter-annotator agreement.
- **Injection batches.** Each defence was measured on its own sealed batch of Set C texts that have a Matriks record (78 of 100): no defence on texts 1-20, text patterns on 21-40, Matriks cross-check on 41-60, the layered defence on **61-78, hence 18**. No case was dropped. On 61-78 each layer alone also reached 0/18 (the source-sentence layer mostly through `amount_not_in_text`); on texts without a Matriks record only the source-sentence layer exists, and that case is not measured.
- **Embeddings.** Three embedding models were compared on 66 dev questions by a pre-written rule before `turkish-e5-large` was chosen (Search table below); BM25, hybrid, chunking and rerank depth were tested against it.
- **Model versions.** `gemma4:e4b` via Ollama, ID `eb2177adf764`, 9.5 GB (thinking on, temperature 0); `ytu-ce-cosmos/turkish-e5-large` at revision `02e2362d503bbdeafcb17143b2165c0743f9fdb1`; `BAAI/bge-reranker-v2-m3` at `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`.

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
| MCP server v1 (12 calls, exact text) | 12 fixed calls | 11/12 (the difference was the LLM card of one brief), overhead 0.011 s | **off** |
| MCP server v2 (non-LLM tools exact, brief code sections) | 10 + 2 new fixed calls | 10/10, 2/2, overhead 0.011 s | **adopted** |
| Tool-calling agent over MCP vs constrained router | 16 dev route questions | right tool 12/16 vs router 14/16 | report only (router stays); "not better": the router was built on these questions |
| Extraction repeatability, Set C run 2 | 100 | changed amount/currency 3/100 (bar 2) → unstable; run 2 silent 1/100, flagged 12% → reproduced | **reported** |
| Matriks' FX rate vs official TCMB rate (tcmb-mcp, registry) | 1045 Matriks FX records, 542 days | within 0.5% of TCMB forex buying: against Matriks' documented convention (previous day's closing rate) **972/1045 = 93.0%** (bar 95%); against the rule's primary reference (same-day bulletin) 913/1045 = 87.4%; median difference 0.16%; on 83 extracted FX amounts 0 importance-level changes (rank order not measured) | **differs** (reported to Matriks); gap filling **off** |
| smtp-mcp (registry MCP server, `@ni-c/smtp-mcp` 0.2.0 pinned) for on-demand desk e-mail | 7 allowlist + 5 behaviour checks: chosen cases, synthetic message, automated approval | refused 7/7 outside `@masa.local` (2 from nodemailer advisories); declined 0 sent; accepted exactly 1, fields and text equal; replay 0; invented token rejected; 0.10 s | **adopted** (mechanism shown; a person's attention and adversarial coverage not measured; 1 high `npm audit` finding accepted on a source reading) |
| Source sentence on the cards (display only) | 43 saved items, 32 with an amount | a sentence containing the amount found 32/32; whether it is the right sentence was not checked | shown as "the sentence where the amount appears" |
| Two-run disagreement flag, Set D (live pipeline, two separate runs) | 50 new (12 zone + 38 random), labeled before the runs | disagree 3/50; new flags over run a **0/50** (bar 3); run a silent 0/50, run b silent **1/50**, caught by the flag (1/1); on the random 38 alone 0/38 (95% upper 7.6%) and 1/38 (11.9%); median a+b 30.9 s | **adopted** (nightly list only) |
| amount_checks v2 ("ABD Doları" read as USD), Set D | 12 zone texts (whole effect zone) + Set C runs 1-2 | new flags 0, catches 0, false alarms 0 (bar 1) | **adopted** (parser gap closed; no flag changed anywhere, no observed effect) |
| Drift: agreement with Matriks after Set C | 40 disclosures after 2026-10-08 | 35/40 (87.5%) vs Set C 72/78 (92.3%); bar ≥ 82.3%; 4 of 5 misses are "no amount" | **no drift seen** |
| Fields used by the score: long contract / foreign counterparty / related party | 50 Set C, labeled before the run | errors 3/50 / 7/50 / 5/50 (bar 3 each); all misses, no invented "yes" | long **kept**; foreign, related **off** |
| Desk e-mails via n8n + local Mailpit | all 15 saved days, 43 items, 33 e-mails | lost 0, duplicated 0, wrong desk 0, amount leaks 0; median 0.2 s per day (bar 10 s) | **adopted** |
| Relative periods (code phrase table) | 15 new + 205 earlier questions | exact period 10/10 (bar 9); false period 1/5 (bar 1); wrong fires 0/9 of 205 earlier (bar 2) | **adopted** |
| Data-vendor auditor: which Matriks records disagree with the KAP text (`docs/vendor_audit_rule.md`) | M2: 641 unseen disclosures, all 14 flags + 14 random controls, labeled blind | strict precision **6/14 = 43%** (95% CI 18-71%, bar 50%); every flag a real difference (14/14 incl. 8 convention differences); controls 0/14 errors; M1 on gold sets B/C/D: 1 of 2 flags right, 1 of 9 Matriks errors caught | **AUDITOR_OFF** (report tool only) |
| kap-kart: card from pasted public KAP text, no Matriks data (`docs/kap_kart_rule.md`) | synthetic checks + leak scan on 1,296 texts + 4 trap examples × 3 + visual check | copies identical, equivalence with the nightly path 26/26, sockets / raw tags / outside imports 0; leaks 0 in round 3 (rounds 1-2 found a real fragment in two self-tests); examples **12/12**, median 27.0 s per card (max 31.5 s) | **adopted** (Matriks agreed to publishing the code, 19 Nov) |
| Scope guard v2 (word list or router `out_of_scope`) | 20 new + 185 earlier questions | blocked 10/10 out-of-scope (bar 9); false blocks 0/10 new, **29/185** earlier (bar 3), 1/14 correctly routed (bar 1); median 4.4 s | **off** |
| Scope guard v3 (router untouched; separate yes/no judge only where a card or list would be shown) | 20 new + 185 earlier questions | out-of-scope without disclosure content 10/10 (blocked 6/10); false blocks 1/10 new, **28/185** earlier (bar 3), 1/14 correctly routed; median 3.2 s | **off** |

## Scoring, desks, themes
| what | set | result | decision |
|---|---|---|---|
| Revenue ratio data gates | prod archive | semantics 99.2%, coverage 84%, scale 0.6% | **on** |
| Importance score vs. the author's blind look-first choice (Feyza, not an external analyst) | 10 unseen days, 49 disclosures, 47 pairs | AUC 0.681 (random p95 0.670) = amount only 0.681; top pick amount 7/10, score 3/10 | **AMOUNT_EXPLAINS**, weights unchanged |
| Ordering v2 (dev choice: long contract, then amount) | 12 new days, 52 disclosures, 53 pairs | AUC 0.877 vs v1 0.792; top pick 11 vs 5.5 of 12; amount alone 0.953, 12/12 | **adopted** (amount alone was not the dev choice) |
| Clustering k = 27 vs. Matriks sectors | 1288 disclosures | company-level ARI 0.144 vs. shuffled p99 0.032; ARI vs. company 0.298 | reflects sector, weakly; desks use the sector label, clusters only for the weekly themes page |
| Analyst review of flags in the panel | one day | 3 of 6 flags were real extraction errors | first real use, small sample |

## Second disclosure type: capital increase pilot (`docs/capital_increase_rule.md`)
| what | set | result | decision |
|---|---|---|---|
| Combined system C (form reader + LLM, disagreement flagged) | held-out 30 (80 companies in the pool, one per company) | silent **0/30** (95% upper 9.5%), flagged **16/30** (bar 9), run errors 0, median 21.2 s | **PILOT_NOT_ADOPTED** |
| Form reader F (code only) / LLM L alone | held-out 30 | F: silent 3 (upper 23.9%), flagged 3, resolved 24; L: silent 1, flagged 21, resolved 8 | **LLM_ADDS** (as a cross-check: silent F 3 → C 0) |
| Report only | held-out 30 | stage exact F 27, L 23, C 27; rights price 6/6; bonus source split C 12/14; Matriks record has the gold rate for 11/20; price bridge 0/13 split days | reported |
| Dev (8 texts, 3 rounds) | dev | form reader v1 → v3, checks v1 → v2 (a word check with 4/8 false alarms removed), prompt v1 kept | frozen before the held-out run |

## Second disclosure type 2: stake acquisitions and sales (`docs/fdv_pilot_rule.md`, 19 Nov)
| what | set | result | decision |
|---|---|---|---|
| Pull by the documented `headline` filter (no tag exists) | Aug-Nov 2026 | 107 returned, 101 kept, 0 dropped by the local headline check; 72 companies | enough (bar 38) |
| Combined system C | held-out 30, one per company | silent **2/30** (95% upper 19.5%), flagged **6/30** (bar 9), run errors 0, median 9.9 s | **PILOT_NOT_ADOPTED** (bar: silent ≤ 1) |
| Form reader F / LLM L alone | held-out 30 | F: silent 4 (28.0%), flagged 2, resolved 24; L: silent 4, flagged 1, resolved 25 | **LLM_ADDS** (silent F 4 → C 2) |
| Where C still fails | held-out 30 | both remaining errors are texts where F and L agree on the same wrong value (one direction, one amount); companies sometimes fill the form wrong and the text says otherwise | reported |
| Dev (8 texts, 2 rounds) | dev | form reader v2 (currency from the same number in the text), prompt v2 (negotiation stage = none), guideline v0.2 | frozen before the held-out run |

## Speed and data
- Extraction: median 14.6 s, p90 20.6 s per reading; live the nightly list reads every disclosure twice (Set D median 30.9 s for both); every other stage 0.003 s; a busy day (8 disclosures) takes about 4-6 minutes overnight (computed, not measured).
- Abnormal price moves: 92 of 1378 (6.7%) had a new-business disclosure in the 4 days before, so for most moves the agent says the cause may be elsewhere.

## Exploration (not a measurement)
- Red team on the chat agent (16 questions, Feyza): 7 right. Failures: out-of-scope and unanswerable questions get an unrelated card (the scope guard above did not pass), counterparty taken as the company, "geçen hafta" not parsed, two-company questions. The name-matching failure could not be reproduced.

## What these numbers do not show
- Test sets are small (100 / 48 / 20 / 18 items), so the bounds are wide.
- One analyst built the system, labeled the gold data and wrote most of the questions.
- Agreement with the analyst is not a market outcome. Nothing here predicts price moves.
