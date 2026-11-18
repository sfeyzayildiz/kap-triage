# KAP Bildirim Önceliklendirme Asistanı

(KAP disclosure prioritisation assistant.) A morning triage assistant for equity analysts who follow "Yeni İş İlişkisi" (new business relationship) disclosures on KAP, Borsa İstanbul's public disclosure platform.

## In 30 seconds
- **What:** every night it reads the day's KAP disclosures (licensed Matriks data), extracts the deal facts with a local LLM, checks them in code, and gives the analyst a ranked morning list: what to read first, why, and which numbers to double-check. Every item links to the KAP source.
- **How reliable:** on 100 disclosures it had never seen, 1 wrong amount or currency went through unflagged (95% upper bound 4.7%); the best rule-based baseline let 25 through. A hidden instruction in the text changed the amount silently in 9 of 18 attacks; after the defence, in 0.
- **How it was built:** every decision rule was committed before its measurement, test sets were held out and scored once, and failures are published next to successes (`docs/results.md`, `docs/known_issues.md`).
- **Stack:** Python, Ollama (`gemma4:e4b`), pydantic, LangGraph, sentence-transformers + cross-encoder reranker, DuckDB, MCP, n8n, Docker; about 70 modules with self-tests, run in GitHub Actions on every pull request.
- **Runs on one laptop.** Data never leaves the machine (licence and compliance), so there is no public demo link; `docs/docker.md` reproduces it with your own Matriks token.
- **Author:** Feyza Yıldız ([LinkedIn](https://www.linkedin.com/in/feyza-yildiz/)). Built during the BTK Akademi AI workshop at Entertech İstanbul Teknokent, Oct-Nov 2026.

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
8. **Desk panel.** A local web page with a chat box for the agent, the list per sector desk (Matriks sector label), a confirm / reject step for flagged items (decisions are logged and counted per flag type), a weekly themes page built from embedding clusters, a price chart (stock vs XU100 around the disclosure) on every card, and a reliability page with the measured results as charts. Light / dark theme switch; no JavaScript.
9. **Desk e-mails (n8n).** Every weekday at 07:30 a self-hosted n8n workflow sends each sector desk one e-mail with its part of the morning list (company, look-first / check flags, reasons, KAP link; no amounts). The desk, the order and the text are decided in code; n8n only delivers. Delivery goes to a local mail server (Mailpit), so nothing leaves the machine; in a firm only the SMTP setting changes.

An agent built with LangGraph answers questions such as "What should I look at today?", "What deals did ASELS announce this year?", "Why did KONTR fall on 28 October?", "Disclosures about projects in Iraq", "ASELS geçen ay ne aldı?" (relative periods: this / last week, month, quarter, year, "son 3 ay", read by code) and "ASELS'e bak" (a multi-step company brief: latest disclosure with its card and importance level, price reaction, 12-month history, similar earlier disclosures). The LLM only reads the question. Every number and link in the answer comes from the database through code. A guided form (`/form`) offers the same tools without free text: the analyst picks the question type, then the company and the day, so nothing can be misunderstood; free questions stay in the chat.

## Measured reliability
| what | result | notes |
|---|---|---|
| Extraction, held-out Set B (100 disclosures) | 4 silent errors, 8 flagged | Frozen system, scored once: FAIL. Silent error = wrong amount or currency without a flag. |
| Extraction + code checks, held-out Set C (100) | **1 silent error (95% upper bound 4.7%), 11 flagged** | PASS. The checks were designed from Set B errors; Set C was unseen. A second run gave 1/100 again (another item): temperature 0 is not fully repeatable (3/100 extractions changed). |
| MCP server (agent tools over the Model Context Protocol, stdio, read-only) | transport exact 10/10, overhead 0.011 s; a free tool-calling agent picked the right tool 12/16, our constrained router 14/16 | Adopted. Local clients only (results hold licensed data). |
| Retrieval, `turkish-e5-large`, held-out Set C questions (48) | recall@5 0.875, recall@1 0.667 | Model chosen on 66 dev questions by a pre-written rule. |
| + cross-encoder rerank (`bge-reranker-v2-m3`), 20 hand-written questions | top 5: 20/20, top 1: 17/20 (was 15/20) | Adopted. BM25 and hybrid search were tried and rejected by their bars. |
| Amount injection attack, 18 new texts, sealed attack wording | silent successes 9 → **0** with the layered defence; 3/200 extra flags on real texts | Adopted. Two weaker defences were rejected by their bars. |
| Without an LLM, same Set C | best regex 25 silent errors out of 100 | So the LLM is needed where the text is free Turkish. |
| Agent routing with company names (router v2), 20 questions | intended link in the top 5: 18/20 (was 11/20) | Company brief flow: 9/10 routed, 10/10 right ticker, median 18.5 s. |
| Importance score vs. the analyst's blind choice, 10 unseen days | AUC 0.681, same as sorting by amount | Better than chance, but the extra components did not show added value. |
| Ordering v2 (long contract, then amount), 12 new days | top pick 11/12 (v1 5.5), AUC 0.877 (v1 0.792) | Adopted. Amount alone did even better (12/12) but was not the dev choice. |
| Analyst review of flags, one demo day | 3 of 6 flags were real extraction errors | First real use of the panel; small sample. |
| Relative periods ("geçen hafta", "son 3 ay"), 15 new questions + 205 earlier | exact period 10/10; false period 1/5; wrong fires 0/9 | Adopted. Parsed by code from a fixed phrase table. |
| Desk e-mails via n8n, all 15 saved days | 43 items, 33 e-mails: 0 lost, 0 duplicated, 0 wrong desk, 0 amount leaks; 0.2 s per day | Adopted. Measures the delivery, not whether the sector desk is the right recipient. |
| Latency | median 14.6 s per disclosure (LLM); all other stages 0.003 s | A busy day takes about 3 minutes, overnight. |
| Abnormal price moves, 493 trading days | 92 of 1378 (6.7%) had a new-business disclosure in the 4 days before | So for most moves the agent says the cause may be elsewhere. |

Decision rules are committed before each measurement (`docs/*_rule.md`), and results are recorded as they come out, including failures. Tried and not adopted, with numbers: text-pattern injection checks, the Matriks cross-check alone, BM25 / hybrid search, chunking, quantities on the card, a word-list scope guard (blocked 7 of 10 out-of-scope questions, bar 9), a router-based scope guard (blocked 10 of 10 but also 29 of 185 normal questions, bar 3), and LLM-written answers with citations (citations were right, but the model answered unanswerable questions). Every result on one page: `docs/results.md`.

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

# desk panel -> http://127.0.0.1:8765 (chat), /form (guided), /days, /themes, /guvenilirlik
.venv/bin/python scripts/panel.py --serve
```

With Docker: `docker compose up --build` (Ollama stays on the host; `data/` is mounted, never baked in). See `docs/docker.md`. The same command starts n8n (`127.0.0.1:5678`) and the local mail inbox Mailpit (`127.0.0.1:8025`); importing the desk workflow once: `docs/n8n_guide.md`.

MCP (local clients only): `.venv/bin/python scripts/mcp_client.py --list`, `scripts/mcp_agent.py --ask "ASELS son 3 ayda hangi işleri aldı?"`, or the official Inspector: `npx -y @modelcontextprotocol/inspector@2.13.0 .venv/bin/python scripts/mcp_server.py`. Never connect a cloud client: tool results contain licensed data.

Each script has a `--self-test`; `scripts/run_self_tests.py` runs them all (also in CI on every pull request). Operations: `docs/runbook.md`. Architecture: `docs/architecture.md`. Other entry points:
- `scripts/price_collect.py`: daily price bars.
- `scripts/rag_index.py --build`: search index.
- `scripts/price_moves.py --scan DATE`: abnormal moves.
- `scripts/score_silent.py`: evaluation scoring.

## Data and privacy
- Data comes from the Matriks API (new-business data, KAP disclosure texts, daily bars), used with Matriks' permission. Raw data stays in `data/` and is never committed.
- All models run locally (Ollama, sentence-transformers). No disclosure text or result is sent to an external service. n8n and Mailpit run locally with telemetry and update checks switched off; desk e-mails carry no amounts.

## Limits
- Scope is only "Yeni İş İlişkisi" disclosures. A second type (capital increases) was tested once as a pilot on 18 Nov: 0/30 silent errors but 16/30 flagged, so not adopted by its pre-written bar (`docs/capital_increase_rule.md`).
- Prices are unadjusted. Moves above 22% are treated as possible splits or bonus issues and not explained.
- The revenue ratio uses Matriks prod revenue (balance sheet chosen by Matriks); its data-quality gates passed (`docs/revenue_ratio_rule.md`), its weights are judgment.
- The money regex of the code checks did not read "ABD Doları" (10 of 81 Set B amounts). Closed on 15 Nov by `amount_checks_v2.py`; no flag changed on any measured set, so no effect was observed. Other spellings ("US Doları") are still not read.
- The agent has no scope check (two designs failed their bars): an out-of-scope question (dividend, target price) that names a company and asks a detail can get an unrelated disclosure card. Two-company comparisons are not supported. Relative periods outside the phrase table ("önceki hafta", "son günlerde") are not read.
- Desk = Matriks sector (27 desks); a firm would group sectors into its own desks (a config change).
- Test sets are small (100 / 48 / 20 / 18 items), so the bounds are wide. The injection test used one attack wording.
- Disclosure texts come from the Matriks test environment (same counts as prod); new-business data from prod.
- This is a working prototype, not a product.

One-page system card (purpose, data, measured performance, limits): `docs/system_card.md`. How it would extend to other disclosure types: `docs/extending.md`.
Where we were wrong, and what we did about it: `docs/known_issues.md`.

Development log and all decisions: `PROJECT_NOTES.md`.
