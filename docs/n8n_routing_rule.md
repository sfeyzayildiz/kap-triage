# Desk routing with n8n: rule, written before code and the workflow

Date: 2026-11-13. Instructor's "one step further": route the morning list to the right departments. The panel already groups a day by sector desk; nothing is *delivered* to a desk. Course day 8 is n8n. This step adds a delivery layer and measures that it neither loses nor misroutes nor leaks anything.

## Design (approved by Feyza 2026-11-13)
- **The decision stays in code, n8n only carries it.** Desk = the Matriks sector of the company (`panel.desk_of`, unchanged; 27 sectors, no grouping; no sector → "Atanmamış"). n8n does not decide a desk, a priority or a text.
- **Panel endpoint** `GET /api/desks/<day>` (read-only JSON, no LLM): per desk a mailbox address, a subject line and the items in morning priority order with company, `look_first`, `needs_review`, reason codes, `kap_url`, `news_id`. **No amounts, no ratios, no disclosure text** (least data: the desk opens the card in the panel). The message text is built in code; n8n sends it as is.
- **n8n** runs self-hosted as a service in `docker-compose.yml` (UI on `127.0.0.1:5678` only); telemetry, version checks, templates and personalization **off** by environment variables.
- **Delivery = local e-mail.** **Mailpit** (local SMTP server with a web inbox, `127.0.0.1:8025`) is a third service: one e-mail per desk to `<desk>@masa.local`. Nothing leaves the machine (Matriks licence). In a firm only the SMTP setting changes (corporate e-mail / Teams). Telegram, Slack and ntfy are not used: external servers, and not approved channels in most brokerage compliance setups.
- Workflow: Claude writes it (`n8n/desk_routing.json`), Feyza imports it with one command and runs it; then a guided tour of the editor. Nodes: Webhook (`?day=`) and Schedule (weekdays 07:30) → HTTP GET the endpoint → one item per desk → Send Email (SMTP = Mailpit).

## Measurement (code, after the workflow runs; Feyza runs it)
`scripts/desk_route_check.py --all`: clears Mailpit, triggers the workflow once per day with a saved morning list, then compares the e-mails (Mailpit's local API) with `panel.by_desk` computed by code.
- **L** lost items (a `news_id` of the day in no e-mail): **0**.
- **D** duplicated items (in more than one e-mail, or twice in one) or more than one e-mail per desk and day: **0**.
- **W** items in the wrong desk's e-mail: **0**.
- **X** leakage: an e-mail contains a number followed by TL / TRY / USD / EUR / dolar / avro / milyon / milyar or a number with "%": **0**.
- **T** median seconds per day (trigger to all e-mails of the day in Mailpit): bar ≤ 10 s.
- Days: all saved morning lists at the time of the run (count reported). stdout: counts and day ids only.

## Decision (fixed now)
All bars met on all days → `ADOPT_N8N` (workflow in the repo, schedule on, README / architecture updated). Otherwise `N8N_OFF`: the panel's desk view stays the only routing; the workflow stays in the repo as a record. Fixing a broken workflow before the measured run is allowed (it is integration, not tuning); after the measured run nothing changes.

## Limits
This measures the integration (nothing lost, duplicated, misrouted or leaked), not whether the sector desk is the right recipient: that needs analysts from a real desk. Desk = sector (27): a firm would group sectors into its own desks (`panel.DESKS`, a config change). Mailpit stands in for a real mail server.
