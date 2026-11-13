# n8n desk e-mails: setup and run

Rule: `docs/n8n_routing_rule.md`. Everything runs on this computer: panel (8765), n8n (5678), Mailpit (8025).

## Setup (once)
```
cd ~/projects/kap-explore
docker compose up --build -d          # panel rebuilt with /api/desks; n8n and Mailpit pulled (~500 MB once)
```
1. Open http://127.0.0.1:5678 and create the local owner account (stays in the `n8n-data` volume; nothing is sent out).
2. Import the SMTP credential and the workflow:
   ```
   docker compose exec n8n n8n import:credentials --input=/import/credentials_mailpit.json
   docker compose exec n8n n8n import:workflow --input=/import/desk_routing.json
   ```
3. Reload the n8n page → Workflows → "KAP masa yönlendirme" → switch **Active** on (top right).
4. Open http://127.0.0.1:8025 (Mailpit inbox).

## Workflow
`Webhook (?day=) / Schedule (weekdays 07:30)` → `Hangi gün?` → `Panelden masa listesi` (GET `http://panel:8765/api/desks/<day>`) → `Masa başına ayır` → `Masaya e-posta` (SMTP `mailpit:1025`) → `Özet`.
The desk, the order and the text come from `scripts/desk_mail.py`; n8n only sends.

## Run
```
.venv/bin/python scripts/desk_route_check.py --day 2026-11-12   # smoke test, one day
.venv/bin/python scripts/desk_route_check.py --all              # the measured run, once
```
Not between 23:40 and 23:50 (the panel reads the DB).

## In a firm
Change the SMTP credential to the corporate mail server (or replace the e-mail node with Teams); group sectors into the firm's desks with `panel.DESKS`. No other change.
