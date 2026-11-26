# Security

Scope: a local prototype that runs on one analyst's computer. It is not a hosted service and has no user accounts.

## What is protected, and how
- **Licensed data stays on the machine.** Matriks data lives in `data/`, is never committed (checked over the full git history, [`docs/public_release.md`](docs/public_release.md)) and is never sent to an outside service: the models run locally (Ollama, sentence-transformers). The nightly phone alert sends counts and, when available, a seal hash prefix on success. Failure alerts use fixed text and may include the list date. Exception messages, subprocess error output and vendor error details stay in the local `data/daily.log`.
- **Disclosure text is untrusted input.** A hidden instruction in a KAP text can fool the model, so the extracted amount is cross-checked against the vendor's record and a separate one-sentence judge checks where the amount comes from. Code only flags ("KONTROL ET"), it never changes a value. Measured: hidden-instruction attacks 9/18 → 0/18 ([rule](docs/layered_defence_rule.md)).
- **The panel is local only** (`kap_triage/web/app.py`): it binds to `127.0.0.1`; every request needs a local `Host` header (against DNS rebinding); a POST from another site's page is refused (`Origin`; a POST with no `Origin` header is accepted, see `docs/known_issues.md` D8); the Content-Security-Policy is `default-src 'none'` (no scripts, no outside resources); form bodies have a size limit; pages that read the database answer 503 during the nightly collection.
- **E-mail needs a person.** Desk e-mails carry no amounts. Sending through the third-party MCP e-mail server waits for a person's approval (a LangGraph `interrupt()`), and the server refuses addresses outside `@masa.local` (7/7, [rule](docs/smtp_mcp_rule.md)).
- **Secrets.** The Matriks token is read from `.env` (git-ignored) only when a request is made; [`.env.example`](.env.example) lists every setting.

## Known limits
- No accounts or roles: anyone who can use the computer can use the panel.
- Dependencies are pinned, but they were not checked with a vulnerability scanner. One high `npm audit` finding in the pinned e-mail server was accepted after reading its source code ([rule](docs/smtp_mcp_rule.md)).
- More: [`docs/known_issues.md`](docs/known_issues.md) and [`docs/system_card.md`](docs/system_card.md).

## Reporting a problem
Please report a vulnerability privately through GitHub: the repository's **Security** tab → **Report a vulnerability**. Do not open a public issue for it.
