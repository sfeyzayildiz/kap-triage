# n8n desk e-mails: setup and run

Rule: `docs/n8n_routing_rule.md`. Everything runs on this computer: panel (8765), n8n (5678), Mailpit (8025).

## Setup (once)
```
cd kap-triage                          # the cloned repository
docker compose up --build -d          # panel with /api/v1/desks; n8n and Mailpit pulled (~500 MB once)
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
`Webhook (?day=) / Schedule (weekdays 07:30)` → `Hangi gün?` → `Panelden masa listesi` (GET `http://panel:8765/api/v1/desks/<day>`) → `Masa başına ayır` → `Masaya e-posta` (SMTP `mailpit:1025`) → `Özet`.
The desk, the order and the text come from `kap_triage/analysis/desks.py`; n8n only sends.

## Run
```
curl 'http://127.0.0.1:5678/webhook/desk-routing?day=2026-11-12'   # one day, by hand (the workflow must be Active)
```
The measured run over all saved days (`docs/n8n_routing_rule.md`) used a check script that stays in the development repository.
Not between 23:40 and 23:50 (the panel reads the DB).

## In a firm
Change the SMTP credential to the corporate mail server (or replace the e-mail node with Teams); group sectors into the firm's desks with `DESKS` in `kap_triage/web/panel.py`. No other change.
