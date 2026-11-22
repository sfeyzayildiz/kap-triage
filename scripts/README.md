# scripts/: the running system (55 modules)

Run every module from the repository root (`.venv/bin/python scripts/<module>.py`). Modules import each other by name. 48 of the 55 have a self-test (`--self-test` for most), and `run_self_tests.py` runs them all. The other 7 have none: `run_self_tests.py` itself, `collector.py`, `parse_form.py`, `llm_extract.py` (it runs inside `e2e_check.py` with a fake model), `build_docs.py`, `eval_vs_matriks.py` and `score_silent.py`.

## Start with these six files
1. `daily_collect.py`: the nightly entry point; what runs, in which order, and what happens when a step fails.
2. `pipeline.py`: one disclosure from text to fields and flags (extraction, code checks, injection defence, second reading).
3. `llm_extract.py`: the extraction call: prompt v3, the pydantic schema and the model settings.
4. `importance.py`: the importance level and its reasons, all in code.
5. `morning.py`: the morning list: order, reasons and a KAP link on every item.
6. `agent.py`: the LangGraph agent; the LLM picks a tool, code writes the answer.

The panel (`panel.py`) puts these on screen.

## By role
- **Nightly path:** `daily_collect.py` (entry point) → `collector.py` (`parse_form.py`), `pull_guard.py` → `morning_job.py` → `morning.py` → `pipeline.py` (`llm_extract.py`, `amount_checks.py`, `amount_checks_v2.py`, `currency_check.py`, `matriks_crosscheck.py`, `source_check.py`), `importance.py`, `price_moves.py`, `rag_index.py`, `forward_seal.py`. `deploy_check.py` checks the environment.
- **Analyst tools:** `panel.py` (with `watchlist.py`, `chat.py`, `form.py`, `themes.py`, `reliability.py`, `price_chart.py`, `demo_mode.py`), `agent.py` (`names.py`, `periods.py`), `mcp_server.py` / `mcp_client.py` / `mcp_agent.py`, `desk_mail.py`, `mail_mcp.py`.
- **Other data collection (Matriks, run by the author only):** `price_collect.py`, `sector_collect.py`.
- **Search index:** `build_docs.py`, `normalize.py`, `clusters.py` (weekly themes).
- **Forward test:** `forward_score.py`, `two_run_count.py` (scored once, on submission day).
- **Tests and checks:** `run_self_tests.py` (all self-tests, also in CI), `e2e_check.py` (the real nightly chain on made-up disclosures, fake model), `kap_kart_check.py` and `kap_kart_leak_scan.py` (kap-kart copies and leak scan), `demo_leak_check.py` (demo mode), `sample_data.py` (made-up sample data for `panel.py --sample`, with its leak scan), `desk_route_check.py` (desk e-mail chain), `make_timeline.py` (`docs/timeline.md` from git).
- **Helpers with evaluation names:** `eval_vs_matriks.py` (`norm_cur`), `eval_retrieval.py` (embedding models), `route_eval.py` (`word_date`), `score_silent.py` (scoring, 95% bound), `tcmb_check.py` (rate fill, off), `quantities.py` (card quantities, off). The live code imports them, so they stay here; giving them system names is listed as architecture debt in `docs/known_issues.md` (E1).

`schema.sql` is the database schema. The measurement scripts are kept outside this repository (as little test code as possible); every result and its rule is in [`../docs/results.md`](../docs/results.md).
