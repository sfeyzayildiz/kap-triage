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

**Desk e-mails (07:30, weekdays):** the n8n workflow "KAP masa yönlendirme" sends the latest morning list to each sector desk (Mailpit inbox `http://127.0.0.1:8025`). Needs Docker running with the three services (`docker compose up -d`). If no e-mails came: n8n → Executions shows the failed node; `scripts/desk_route_check.py --day YYYY-MM-DD` re-sends one day and prints counts. Setup: `docs/n8n_guide.md`.

**On-demand desk e-mail with approval (smtp-mcp, `docs/smtp_mcp_rule.md`):** once `cd mcp/smtp && npm ci --ignore-scripts` (Node ≥ 24; pinned `@ni-c/smtp-mcp` 0.2.0), Docker up (Mailpit SMTP on 127.0.0.1:1025). `scripts/mail_mcp.py --send --day YYYY-MM-DD` lists the desks; add `--desk NAME` to send: the server's approval text appears, only `e` sends; recipients outside `@masa.local` are refused by the server. Health check without data: `scripts/mail_mcp.py --check` (`decision: ADOPT_SMTP_MCP`). Upgrading the package needs a new review (`npm audit` notes in the rule, Amendment 1).

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
**Code guard (`scripts/pull_guard.py`, since 12 Nov):** every pull script writes `data/last_pull.txt` before its first request, and refuses when a pull already happened that day (the price pull may resume itself; sectors may follow prices). The nightly job sends `KAP collector SKIPPED` instead of pulling. Pausing the job is still the clean way; the guard is the net under it. Override only knowingly: delete the marker. `python scripts/pull_guard.py` shows the last pull.

Pause / resume the nightly job:
```
launchctl bootout gui/$(id -u)/com.feyza.kap-daily                                   # pause
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.feyza.kap-daily.plist    # resume (next morning, ALONE: never inside a block of other commands)
launchctl list com.feyza.kap-daily                                                    # paused = "Could not find service"
```

### Prod archive refresh (approved by Matriks, once)
```
cd ~/projects/kap-explore && git switch main && git pull -q
PYTHONPATH=scripts .venv/bin/python experiments/prod_refresh.py --plan        # months and request count, no network
PYTHONPATH=scripts .venv/bin/python experiments/prod_refresh.py --run --yes   # refuses unless the job is paused and the snapshot exists
PYTHONPATH=scripts .venv/bin/python experiments/prod_refresh.py --compare     # counts only
PYTHONPATH=scripts .venv/bin/python experiments/revenue_check.py              # gates of docs/revenue_ratio_rule.md, counts only
```
Paste the `--run` summary line, the `--compare` output and the `revenue_check` line. Resume the job next morning.

### Price refresh and sector labels (~12 Nov, same session)
```
.venv/bin/python scripts/price_collect.py --pull --yes && .venv/bin/python scripts/price_collect.py --load
.venv/bin/python scripts/sector_collect.py --pull --yes && .venv/bin/python scripts/sector_collect.py --load
```
Then (Claude's commands): rebuild clusters with k = number of sectors, `clusters.py --evaluate` once, fill the desk map in `panel.py`, rebuild the two demo reports.

### Capital-increase pilot day (Wed 18 Nov 2026, daytime; rule `docs/capital_increase_rule.md`, Note 1b)
The nightly job stays **loaded** (Note 1): `pull_guard` makes it skip that night, and the 18 Nov alert says `KAP collector SKIPPED`, which is expected. Nothing to resume the next morning. Never 23:30-23:59. Ollama must be running from step 4 on. About 3 hours for Feyza in all, most of it labeling; steps marked **Claude** happen in the chat in between.

```
cd ~/projects/kap-explore && git switch main && git pull -q
PYTHONPATH=scripts .venv/bin/python experiments/capital_collect.py --plan          # 1. no network: months, request estimate, pulled_today=no
PYTHONPATH=scripts .venv/bin/python experiments/capital_collect.py --pull --yes    # 2. the day's only pull (a few minutes)
PYTHONPATH=scripts .venv/bin/python experiments/capital_collect.py --load          # 3. no network: raw files -> capital tables
PYTHONPATH=scripts .venv/bin/python experiments/capital_profile.py --tokens 10     # 4. counts only (Ollama on)
```
Paste the full output of 1-4 (counts and dates only). Do not paste `/tmp/capital_form_keys.txt` unless Claude asks.
- `STOP: fewer than 38 symbols` in step 2: stop there and tell Claude (the pilot stops before labeling).
- `v1/capital-increase: HTTP ...` in step 2: the news part is fine. Retry only that request the same day:
  `MATRIKS_CI_API=https://<MATRIKS_API_HOST>/dumrul PYTHONPATH=scripts .venv/bin/python experiments/capital_collect.py --pull --yes`
- Any other stop in step 2: run the same command again the same day; it resumes from the manifest.

**Claude:** writes Note 4 (long-text threshold from step 4) and commits it **before** anything is labeled.

```
git pull -q
PYTHONPATH=scripts .venv/bin/python experiments/sample_capital.py --dry-run        # 5. counts
PYTHONPATH=scripts .venv/bin/python experiments/sample_capital.py                  # 6. writes the 8 dev + 30 held-out ids
cp data/capital_dev.jsonl data/capital_test.jsonl ~/kap-backups/
PYTHONPATH=scripts .venv/bin/python experiments/label_capital.py                   # 7. the 8 dev texts (~15 min); q stops, re-run resumes
```
Report where a guideline rule did not fit, as rule numbers and tags only (never text). **Claude:** guideline v0.2 if needed; then redo the touched dev labels with `--guidelines v0.2 --redo NEWS_ID`.

```
PYTHONPATH=scripts .venv/bin/python experiments/capital_extract.py --split dev     # 8. F, L, C on the 8 dev texts (~5 min)
PYTHONPATH=scripts .venv/bin/python experiments/capital_extract.py --score-dev     # 9. ids and counts
```
Paste 8-9. **Claude:** may change the prompt or the form reader (at most 3 versions each; the script refuses a 4th), you re-run 8-9.

```
PYTHONPATH=scripts .venv/bin/python experiments/label_capital.py --split test --guidelines v0.1   # 10. the 30 held-out texts (~1 h); use v0.2 if it was written
cp data/gold_capital_*.jsonl ~/kap-backups/
```
**Claude:** freeze commit (check list and long-text threshold frozen, chosen versions named). Then:

```
git pull -q
PYTHONPATH=scripts .venv/bin/python experiments/capital_extract.py --split test    # 11. once (~15-20 min); refuses before the freeze
PYTHONPATH=scripts .venv/bin/python experiments/capital_score.py --score           # 12. once; ids and counts
```
Paste 11 (last three lines) and 12. No scoring while 11 is running.

### Submission day (Tue 24 Nov 2026; submission closes at 23:59, link to the instructor by 15:00 as agreed; nothing after it)
Rule: `docs/forward_test_rule.md`, Notes 7-8. The nightly job stays loaded; it sends `SKIPPED` that night (one pull per day).
```
cd ~/projects/kap-explore && git switch main && git pull -q
.venv/bin/python scripts/pull_guard.py                                    # last pull must not be today
.venv/bin/python scripts/price_collect.py --pull --yes                    # ~10:00; that day's only pull; after a failure it may be re-run the same day (resume)
.venv/bin/python scripts/price_collect.py --load                          # counts and last bar date: must reach 2026-11-23
.venv/bin/python scripts/forward_score.py --score                         # once; INCOMPLETE = bars to 23 Nov missing
.venv/bin/python scripts/two_run_count.py --start 2026-11-15 --end 2026-11-23   # report only (known_issues A12)
```
Paste the `--load` summary, the score lines and the last `two_run_count` line. **14:00 cutoff:** if the bars or the score are not there by then, stop trying; the submission says "forward test not scored" with the failed step (Note 8).
Then, by about 15:00: Claude records the result (results, notes, metrics_faq), re-runs `scripts/make_timeline.py`, merges; rebuilds the public copy and shows its check counts (`docs/public_release.md`); Feyza runs the kap-kart leak scan on the copy (`docs/kap_kart_rule.md`, Note 1); Feyza says "aç" and the repository name; Claude creates the public repository and pushes. 15:00-23:59 is spare time.

## Daily use
```
cd ~/projects/kap-explore
.venv/bin/python scripts/panel.py --serve      # http://127.0.0.1:8765 = chat, /days = morning lists; Ctrl+C to stop (holds no DB lock while idle)
.venv/bin/python scripts/panel.py --serve --demo --port 8766   # demo mode for video/talk: Matriks values hidden (8766: works while the Docker panel holds 8765)
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
