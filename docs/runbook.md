# Runbook: operating the system

Who runs what: Feyza runs everything that touches Matriks or takes long; Claude writes code and gives the commands.
Two folders: `~/projects/kap-explore` (development, branches) and `~/projects/kap-deploy` (always `main`, used by launchd).

## Nightly (automatic)
- 23:43 launchd (`com.feyza.kap-daily`) runs `kap-deploy/.venv/bin/python scripts/daily_collect.py`: collection (one pull), then the morning list for the day.
- Two phone alerts, counts only: `KAP collector OK` (or `FAILED` with the error) and `KAP morning list` (or `KAP morning FAILED`).
- Needs: Mac awake or waking (launchd runs a missed job at wake), network, **Ollama running**.
- Nothing else may touch the DB between 23:40 and 23:50.

### If an alert says FAILED
| alert | first check |
|---|---|
| collector FAILED, DB lock | another Python process holds `data/kap.duckdb` (a panel, a notebook, an eval); the alert names the holder. Close it; the next night fills the gap. |
| collector FAILED, network | the Mac woke without network; the next night fills the gap. |
| morning FAILED, `ModuleNotFoundError` | kap-deploy venv is missing a package: see "After every merge". Then rebuild the day by hand (below). |
| morning list with `run_errors>0` | Ollama was not running; start it and rebuild the day. |

Rebuild one day's morning list by hand (after 23:50):
```
cd ~/projects/kap-deploy && .venv/bin/python scripts/morning_job.py --date YYYY-MM-DD
```

## After every merge to main (update kap-deploy)
```
cd ~/projects/kap-deploy && git pull -q && .venv/bin/pip install -q -r requirements.txt
.venv/bin/python scripts/deploy_check.py
```
`-> OK` is required. `-> FIX` lists the package or import to fix. Dry runs of the nightly path always use this Python, not the kap-explore one.

## One-off pulls (each is that day's only pull; job paused; 18:00-23:30)
Pause / resume the nightly job:
```
launchctl bootout gui/$(id -u)/com.feyza.kap-daily                                   # pause
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.feyza.kap-daily.plist    # resume (next morning)
launchctl list com.feyza.kap-daily                                                    # paused = "Could not find service"
```

### Prod archive refresh (approved by Matriks, once)
```
cd ~/projects/kap-explore && git switch main && git pull -q
.venv/bin/python scripts/prod_refresh.py --plan        # months and request count, no network
.venv/bin/python scripts/prod_refresh.py --run --yes   # refuses unless the job is paused and the snapshot exists
.venv/bin/python scripts/prod_refresh.py --compare     # counts only
.venv/bin/python scripts/revenue_check.py              # gates of docs/revenue_ratio_rule.md, counts only
```
Paste the `--run` summary line, the `--compare` output and the `revenue_check` line. Resume the job next morning.

### Price refresh and sector labels (~12 Nov, same session)
```
.venv/bin/python scripts/price_collect.py --pull --yes && .venv/bin/python scripts/price_collect.py --load
.venv/bin/python scripts/sector_collect.py --pull --yes && .venv/bin/python scripts/sector_collect.py --load
```
Then (Claude's commands): rebuild clusters with k = number of sectors, `clusters.py --evaluate` once, fill the desk map in `panel.py`, rebuild the two demo reports.

## Daily use
```
cd ~/projects/kap-explore
.venv/bin/python scripts/panel.py --serve      # http://127.0.0.1:8765; Ctrl+C to stop (holds no DB lock while idle)
.venv/bin/python scripts/panel.py --stats      # review decisions per flag type
.venv/bin/python scripts/agent.py "Bugün neye bakmalıyım?"
```
Stop the panel before 23:40.

## Measurements
- Rule first (`docs/*_rule.md`, committed), then the run in Feyza's terminal, then the score. No scoring while a run is in progress; `INCOMPLETE` means wait.
- Paste only score lines (counts, ids, metrics). Files with amounts go to `/tmp` and are not pasted.
- Held-out sets unused so far: Set C questions + `data/rag_questions_neg.jsonl` for cited answers (kept for a stronger model).

## Backups
`~/kap-backups/`: gold sets, RAG questions. Refresh after every label or question change:
```
cp data/gold_set_c.jsonl data/rag_questions*.jsonl ~/kap-backups/
```
