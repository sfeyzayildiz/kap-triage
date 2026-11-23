# Version 1 → version 2: where each file went

Version 1 (submitted to the workshop as `kap-disclosure-triage`) kept the running system in one folder, `scripts/`, and ran each file as a script. Version 2 is the same system as a package, `kap_triage/`, with one entry point (`main.py`), a FastAPI panel and pytest. The measured logic was moved, not rewritten: the panel pages and the morning lists of the sample data are byte-identical in both versions (pull requests #1 and #2).

The rule files and `PROJECT_NOTES.md` are a record of what was measured, so they keep the version 1 file names. Use this table to find a file they mention.

## Moved
| version 1 (`scripts/`) | version 2 (`kap_triage/`) |
|---|---|
| `collector.py`, `parse_form.py` | `collect/collector.py` |
| `daily_collect.py`, `morning_job.py` | `collect/nightly.py` (`python main.py nightly`) |
| `pull_guard.py` | `collect/pull_guard.py` |
| `price_collect.py` | `collect/prices.py` |
| `sector_collect.py` | `collect/sectors.py` |
| `forward_seal.py` | `collect/seal.py` |
| `schema.sql` | `collect/schema.sql` |
| `llm_extract.py` (prompt v3 only) and `prompts/extract_v3.txt` | `analysis/llm.py` and `analysis/prompt_v3.txt` |
| `amount_checks.py`, `amount_checks_v2.py`, `currency_check.py` | `analysis/rules.py` (live behaviour: v1 amount checks with the v2 money regex) |
| `source_check.py`, `matriks_crosscheck.py` | `analysis/defence.py` |
| `pipeline.py` | `analysis/pipeline.py` |
| `importance.py` | `analysis/importance.py` |
| `price_moves.py` | `analysis/prices.py` |
| `morning.py` | `analysis/morning.py` |
| `desk_mail.py` | `analysis/desks.py` |
| `normalize.py`, `build_docs.py`, `rag_index.py` | `assistant/search.py` (`python main.py index`) |
| `clusters.py` | `assistant/clusters.py` |
| `themes.py` | `assistant/themes.py` |
| `agent.py` | `assistant/agent.py` (`python main.py agent`) |
| `names.py` | `assistant/names.py` |
| `periods.py` | `assistant/periods.py` |
| `panel.py` | `web/panel.py` (pages) and `web/app.py` (FastAPI routes; `python main.py panel`) |
| `chat.py`, `form.py`, `reliability.py`, `watchlist.py` | `web/` (same names) |
| `price_chart.py` | `web/charts.py` |
| `mcp_server.py` | `web/mcp_server.py` (`python main.py mcp`) |
| `mail_mcp.py` | `web/mail_mcp.py` (`python main.py mail`) |
| `sample_data.py` | `sample.py` (`python main.py sample`) |
| `kap_kart/kap_kart.py` and its frozen copies | `web/kart.py` (`/kart` in the panel, `python main.py kart`); examples in `sample/kart/` |
| the `_self_test()` function inside each module | `tests/test_<module>.py` (pytest) |

## Not in version 2
| version 1 | why |
|---|---|
| `demo_mode.py`, `demo_leak_check.py` | demo mode hid licensed values in screenshots and the video; version 2 shows the made-up sample data instead |
| `run_self_tests.py`, `e2e_check.py`, `deploy_check.py` | replaced by pytest (`tests/test_sample_data.py` runs the nightly chain with a fake model) and CI |
| `eval_retrieval.py`, `eval_vs_matriks.py`, `route_eval.py`, `score_silent.py`, `tcmb_check.py`, `quantities.py` | measurement tools; their results are recorded, and the few functions the live code used were moved next to it |
| `forward_score.py`, `two_run_count.py`, `make_timeline.py` | development tools that read the licensed data or the private history; they stay in the development repository |
| `mcp_client.py`, `mcp_agent.py` | test clients for the MCP server; they stay in the development repository |
| `kap_kart_check.py`, `kap_kart_leak_scan.py`, `desk_route_check.py` | checks for version 1 release steps; they stay in the development repository |
| `prompts/extract_v1.txt`, `extract_v2.txt`, `extract_v4.txt` | earlier prompt versions; only v3 is live |
| switches that were off in production: scope guards v1-v3, card quantities, TCMB rate fill, foreign-counterparty and related-party points | measured and not adopted; the rule files keep the results |
