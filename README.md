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
3. **Importance score (code).** Size against the company's own earlier deals, plus foreign currency, foreign counterparty, contract length and related party. Every point comes with its reason.
4. **Price reaction.** Return against XU100 on the first trading day the market could react.
5. **History.** The company's last 12 months, and its most similar earlier disclosures found by embedding search.
6. **Morning list.** A ranked Turkish report with a KAP link on every item; flagged items always show what to check.

An agent built with LangGraph answers questions such as "What should I look at today?", "What deals did ASELS announce this year?", "Why did KONTR fall on 28 October?" and "Disclosures about projects in Iraq". The LLM only reads the question. Every number and link in the answer comes from the database through code.

## Measured reliability
| what | result | notes |
|---|---|---|
| Extraction, held-out Set B (100 disclosures) | 4 silent errors, 8 flagged | Frozen system, scored once. Silent error = wrong amount or currency without a flag. |
| With the later code checks, Set B | 1 silent error, 12 flagged | Leaked: the checks were designed from Set B errors. An unseen Set C (100) is being labeled for the honest number. |
| Retrieval, `turkish-e5-large` (66 questions) | recall@5 0.864, recall@1 0.729 | Chosen by a rule written before the run. The same questions picked the model, so this is optimistic. |
| Abnormal price moves, 493 trading days | 92 of 1378 (6.7%) had a new-business disclosure in the 4 days before | So for most moves the agent says the cause may be elsewhere. |

The importance score has no measured accuracy yet; its rules are in `docs/importance_score.md`. Decision rules are committed before each measurement, and results are recorded as they come out, including failures.

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
```

Each script has a `--self-test`. Other entry points:
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
- The revenue ratio is not used until a difference between two Matriks environments is explained.
- `MONEY_RE` in the amount checks misses "ABD Doları" (10 of 81 Set B amounts); this is part of what Set C measures.
- This is a working prototype, not a product.

Development log and all decisions: `PROJECT_NOTES.md`.
