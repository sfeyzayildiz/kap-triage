# KAP New Business Triage

A morning triage assistant for equity analysts who follow "Yeni İş İlişkisi" (new business relationship) disclosures on KAP, Borsa İstanbul's public disclosure platform.

## The problem
An analyst sees several of these disclosures every day and has to decide which ones matter:
- Is the deal big for this company?
- Is it good business: foreign currency, foreign counterparty, multi-year?
- Is it real new business, or a related-party deal, a revision of an earlier order, or a one-year revenue estimate presented as contract value?
- What did the company announce before?

Doing this by hand is slow and error-prone. Our error analysis found TL/USD confusion, revisions read as new orders, and projections read as contract values.

## What it does
For each day's disclosures:
1. **Extraction (local LLM).** Amount, currency, counterparty, duration, revision and related-party flags.
2. **Code checks.** Rules flag contradictions (`needs_review`) instead of silently fixing them: unclear currency, projected amounts, cumulative totals.
3. **Injection defence.** Disclosure text is external input. The extracted amount is cross-checked against Matriks' own record, and a one-sentence judge checks that the amount comes from a statement of fact, not from an instruction hidden in the text.
4. **Importance score (code).** Size against the company's own earlier deals, plus foreign currency, foreign counterparty, contract length and related party. Every point comes with its reason.
5. **Price reaction.** Return against XU100 on the first trading day the market could react.
6. **History.** The company's last 12 months, and its most similar earlier disclosures found by embedding search.
7. **Morning list.** A ranked Turkish report with a KAP link on every item; flagged items always show what to check. It runs by itself after the nightly collection and sends a counts-only phone alert.
8. **Desk panel.** A local web page with the list per sector desk and a confirm / reject step for flagged items; decisions are logged and counted per flag type.

An agent built with LangGraph answers questions such as "What should I look at today?", "What deals did ASELS announce this year?", "Why did KONTR fall on 28 October?" and "Disclosures about projects in Iraq". The LLM only reads the question. Every number and link in the answer comes from the database through code.

## Measured reliability
| what | result | notes |
|---|---|---|
| Extraction, held-out Set B (100 disclosures) | 4 silent errors, 8 flagged | Frozen system, scored once: FAIL. Silent error = wrong amount or currency without a flag. |
| Extraction + code checks, held-out Set C (100) | **1 silent error (95% upper bound 4.7%), 11 flagged** | PASS. The checks were designed from Set B errors; Set C was unseen. |
| Retrieval, `turkish-e5-large`, held-out Set C questions (48) | recall@5 0.875, recall@1 0.667 | Model chosen on 66 dev questions by a pre-written rule. |
| + cross-encoder rerank (`bge-reranker-v2-m3`), 20 hand-written questions | top 5: 20/20, top 1: 17/20 (was 15/20) | Adopted. BM25 and hybrid search were tried and rejected by their bars. |
| Amount injection attack, 18 new texts, sealed attack wording | silent successes 9 → **0** with the layered defence; 3/200 extra flags on real texts | Adopted. Two weaker defences were rejected by their bars. |
| Analyst review of flags, one demo day | 3 of 6 flags were real extraction errors | First real use of the panel; small sample. |
| Latency | median 14.6 s per disclosure (LLM); all other stages 0.003 s | A busy day takes about 3 minutes, overnight. |
| Abnormal price moves, 493 trading days | 92 of 1378 (6.7%) had a new-business disclosure in the 4 days before | So for most moves the agent says the cause may be elsewhere. |

Decision rules are committed before each measurement (`docs/*_rule.md`), and results are recorded as they come out, including failures. Tried and not adopted, with numbers: text-pattern injection checks, the Matriks cross-check alone, BM25 / hybrid search, and LLM-written answers with citations (citations were right, 45/46, but the model answered 3 of 7 unanswerable questions). The importance score has no measured accuracy; its rules are in `docs/importance_score.md`.

## How to run
Requirements: Python 3.12, [Ollama](https://ollama.com) with `gemma4:e4b`, and a Matriks API token in `.env` (`KAP_TOKEN`) for collection.

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama pull gemma4:e4b

# daily collection (scheduled with launchd: deploy/com.feyza.kap-daily.plist)
.venv/bin/python scripts/daily_collect.py

# morning list for a day -> data/morning_<date>.md
.venv/bin/python scripts/morning.py --date 2026-10-30

# ask the agent
.venv/bin/python scripts/agent.py "Bugün neye bakmalıyım?"

# desk panel -> http://127.0.0.1:8765
.venv/bin/python scripts/panel.py --serve
```

Each script has a `--self-test`; `scripts/run_self_tests.py` runs them all (also in CI on every pull request). Operations: `docs/runbook.md`. Architecture: `docs/architecture.md`. Other entry points:
- `scripts/price_collect.py`: daily price bars.
- `scripts/rag_index.py --build`: search index.
- `scripts/price_moves.py --scan DATE`: abnormal moves.
- `scripts/score_silent.py`: evaluation scoring.

## Data and privacy
- Data comes from the Matriks API (new-business data, KAP disclosure texts, daily bars), used with Matriks' permission. Raw data stays in `data/` and is never committed.
- All models run locally (Ollama, sentence-transformers). No disclosure text or result is sent to an external service.

## Limits
- Scope is only "Yeni İş İlişkisi" disclosures.
- Prices are unadjusted. Moves above 22% are treated as possible splits or bonus issues and not explained.
- The revenue ratio is coded but switched off until its data-quality gates pass on the refreshed prod data (`docs/revenue_ratio_rule.md`).
- `MONEY_RE` in the amount checks misses "ABD Doları" (10 of 81 Set B amounts).
- Test sets are small (100 / 48 / 20 / 18 items), so the bounds are wide. The injection test used one attack wording.
- Disclosure texts come from the Matriks test environment; new-business amounts from prod.
- This is a working prototype, not a product.

Development log and all decisions: `PROJECT_NOTES.md`.
