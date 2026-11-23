# Runbook: operating the system

Who runs what: I run everything that touches Matriks data or takes long, on my own machine; code changes arrive as pull requests with CI (`ruff` + `pytest`).
The nightly job runs from a separate clone that always stays on `main` (`deploy/com.feyza.kap-daily.plist`), so a branch in the development folder never affects it. That clone runs version 1 (the same logic, `scripts/`); the commands below are the version 2 ones.

## Nightly (automatic)
- 23:43 launchd (`com.feyza.kap-daily`) runs `.venv/bin/python main.py nightly` in the deploy clone: collection (one pull), then the morning list for the day.
- Two phone alerts, counts only: `KAP collector OK` (or `FAILED` with the error) and `KAP morning list` (or `KAP morning FAILED`).
- Needs: Mac awake or waking (launchd runs a missed job at wake), network, **Ollama running**.
- Nothing else may touch the DB between 23:40 and 23:50; the panel answers 503 on the pages that read it.

### If an alert says FAILED
| alert | first check |
|---|---|
| collector FAILED, DB lock | another Python process holds `data/kap.duckdb` (a panel, a notebook); the alert names the holder. Close it; the next night fills the gap. |
| collector FAILED, network | the Mac woke without network; the next night fills the gap. |
| collector FAILED, `KAP_TOKEN is missing` | `.env` is missing in the deploy clone. |
| morning FAILED, `ModuleNotFoundError` | the deploy venv is missing a package: see "After every merge". Then rebuild the day by hand (below). |
| morning list with `run_errors>0` | Ollama was not running; start it and rebuild the day. |

Rebuild one day's morning list by hand (after 23:50; no alert is sent):
```
.venv/bin/python -m kap_triage.analysis.morning --date YYYY-MM-DD
```

**Desk e-mails (07:30, weekdays):** the n8n workflow "KAP masa yönlendirme" sends the latest morning list to each sector desk (Mailpit inbox `http://127.0.0.1:8025`). Needs Docker running with the three services (`docker compose up -d`). If no e-mails came: n8n → Executions shows the failed node; to send one day again, call the workflow's webhook: `curl 'http://127.0.0.1:5678/webhook/desk-routing?day=YYYY-MM-DD'`. Setup: `docs/n8n_guide.md`.

**On-demand desk e-mail with approval (smtp-mcp, `docs/smtp_mcp_rule.md`):** once `cd mcp/smtp && npm ci --ignore-scripts` (Node ≥ 24; pinned `@ni-c/smtp-mcp` 0.2.0), Docker up (Mailpit SMTP on 127.0.0.1:1025). `python main.py mail --send --day YYYY-MM-DD` lists the desks; add `--desk NAME` to send: the server's approval text appears, only `e` sends; recipients outside `@masa.local` are refused by the server. Health check without data: `python main.py mail --check`. Upgrading the package needs a new review (`npm audit` notes in the rule, Amendment 1).

## After every merge to main (update the deploy clone)
```
git pull -q && .venv/bin/pip install -q -r requirements.txt && .venv/bin/pip install -q --no-deps -e .
.venv/bin/pytest -q
```
All tests must pass before the next night. Dry runs of the nightly path always use the deploy clone's Python.

## One-off pulls (each is that day's only pull; job paused; 18:00-23:30)
**Code guard (`kap_triage/collect/pull_guard.py`):** every pull writes `data/last_pull.txt` before its first request and refuses when a pull already happened that day (the price pull may resume itself; sectors may follow prices). The nightly job sends `KAP collector SKIPPED` instead of pulling. Pausing the job is still the clean way; the guard is the net under it. Override only knowingly: delete the marker. `python -m kap_triage.collect.pull_guard` shows the last pull.

Pause / resume the nightly job:
```
launchctl bootout gui/$(id -u)/com.feyza.kap-daily                                   # pause
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.feyza.kap-daily.plist    # resume (next morning, ALONE: never inside a block of other commands)
launchctl list com.feyza.kap-daily                                                    # paused = "Could not find service"
```

### Price refresh and sector labels (same session)
```
.venv/bin/python -m kap_triage.collect.prices --pull --yes && .venv/bin/python -m kap_triage.collect.prices --load
.venv/bin/python -m kap_triage.collect.sectors --pull --yes && .venv/bin/python -m kap_triage.collect.sectors --load
```
Then rebuild the clusters with k = number of sectors (`python -m kap_triage.assistant.clusters --build --k N`), run `--evaluate` once, and fill the desk map (`DESKS` in `kap_triage/web/panel.py`).

Finished one-off procedures (prod archive refresh, 10 Nov; capital-increase and stake pilots, 18-19 Nov; the forward-test scoring on 24 Nov) are recorded in `docs/PROJECT_NOTES.md` and the rule files; their scripts are in the development repository, not here ([`v1_to_v2_map.md`](v1_to_v2_map.md)).

## Daily use
```
.venv/bin/python main.py panel               # http://127.0.0.1:8765 = chat, /genel = overview, /days = morning lists; Ctrl+C to stop
.venv/bin/python main.py panel --sample      # the same panel on made-up data (sample/data/)
.venv/bin/python main.py panel --stats       # review decisions per flag type
.venv/bin/python main.py agent "Bugün neye bakmalıyım?"
```
Stop the panel before 23:40.

## Measurements
- Rule first (`docs/*_rule.md`, committed), then the run in my terminal, then the score. No scoring while a run is in progress; `INCOMPLETE` means wait.
- Paste only score lines (counts, ids, metrics). Files with amounts go to `/tmp` and are not pasted.
- Held-out sets that were not used: Set C questions + `data/rag_questions_neg.jsonl` (meant for cited answers with a stronger model).

## Backups
`~/kap-backups/`: gold sets, RAG questions. Refresh after every label or question change:
```
cp data/gold_set_c.jsonl data/rag_questions*.jsonl ~/kap-backups/
```
