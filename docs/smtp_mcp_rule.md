# smtp-mcp: a third-party MCP server for desk e-mail with human approval (rule, written before code and run)

Date: 2026-11-15. Plan item after MCP v2 (Feyza, 14 Nov): use a server from the official MCP registry, recipients limited to `*@masa.local`, every send confirmed by a human.

## What and why
- n8n already sends the scheduled desk e-mails (07:30, `docs/n8n_routing_rule.md`). This adds the **on-demand** path: the analyst sends one desk's list now, and a person approves the exact message before it leaves. It also shows the project consuming an MCP server it did not write, next to the one it serves (`mcp_server.py`).
- Server: `io.github.ni-c/smtp-mcp` from registry.modelcontextprotocol.io, npm `@ni-c/smtp-mcp` **0.2.0** (published 2026-09-07, MIT), pinned with a committed `package-lock.json` in `mcp/smtp/`, installed with `npm ci --ignore-scripts`.
- Review before use (Claude, 15 Nov, source read, scratchpad copy): no network call other than the SMTP connection, no child process, no `eval`, no install scripts; TLS mode `none` is accepted only for a loopback host; recipients (To, Cc, Bcc) checked against the allowlist before a connection opens; approval through MCP elicitation, bound to the recipients and content; no `from` or skip-confirmation parameter.
- Smoke test (Claude, approved by Feyza, no data, no SMTP connection): protocol 2025-11-25 with our `mcp==1.30.0` client; the elicitation reached our callback (one `confirm` box); a declined send was not sent; `x@gmail.com` refused before connecting.

## Set-up (fixed)
- Mailpit SMTP published on **127.0.0.1:1025** only (same as the inbox on 8025); `MP_SMTP_AUTH_ACCEPT_ANY` and `MP_SMTP_AUTH_ALLOW_INSECURE` on, because the server requires a user and password and the connection is loopback cleartext. n8n is unchanged.
- Server environment set by our client only: `SMTP_HOST=127.0.0.1`, `SMTP_PORT=1025`, `SMTP_TLS=none`, `SMTP_FROM=asistan@masa.local`, `SMTP_ALLOW_SEND=true`, `SMTP_ALLOWED_RECIPIENTS=@masa.local`, `SMTP_ALLOW_TOOLS=essential`, `ELICITATION=true`. Nothing else from the user's environment is passed (no token, no `.env`).
- Client `scripts/mail_mcp.py`. Message = `desk_mail.payload` for that day and desk (the n8n text: no amounts, no disclosure text; checked with `desk_mail.leaks`). `--send --day D --desk NAME` shows the server's approval text in the terminal and asks `e/h`; only `e` ticks the box.
- The LLM agent never gets these tools (`mcp_agent.py` and the router stay as they are). Reason: a client without elicitation falls back to a two-call token that a model could replay; only our human-facing client talks to this server.

## Measurement (Feyza runs `scripts/mail_mcp.py --check` once; Docker up with the new compose; automated answers in the callback)
Every check message carries one run tag in the subject; Mailpit is counted through its API by that tag, nothing else in the inbox is touched.
- **A allowlist, 5 cases, each must be refused with 0 messages:** To `x@gmail.com`; To `savunma@masa.local.evil.com`; To `savunma@masalocal.com`; To a valid desk with Cc `x@gmail.com`; To a valid desk with Bcc `x@gmail.com`.
- **B declined:** valid desk, callback declines → not sent, 0 messages.
- **C accepted:** valid desk, callback accepts → exactly 1 message; its To, From and Subject equal what was asked and its text equals the `desk_mail` text (line endings and trailing whitespace normalised).
- **D replay:** the same accepted request again → no second message.
- **E invented token:** a second session **without** elicitation calls `send_mail` with a made-up `confirm_token` → rejected, 0 messages.
- **F no leak:** the sent text passes `desk_mail.leaks` (no amount, ratio, currency figure).
- **G latency:** seconds from the call to the result for C, with the automated answer (human time excluded): ≤ 5 s.

## Decision (fixed now)
A 5/5, B, C, D, E, F all pass and G ≤ 5 s → `ADOPT_SMTP_MCP` (client, pinned server and compose change stay, docs updated). Otherwise `SMTP_MCP_OFF`: compose change reverted, code kept as a record. Nothing changes after the run.

## Amendment 1 (15 Nov, before any measurement): npm audit
`npm ci` reports 1 high / 1 moderate: the bundled `nodemailer` 9.1.1 has 12 advisories (fixed in ≥ 10.1.4; smtp-mcp 0.2.0 asks for `^9.1.0`, no newer smtp-mcp exists). Reading (Claude, source): 8 are address-parser bugs (quoted local part, comments, `;` groups, `>`, nested arrays); smtp-mcp refuses every recipient that is not a bare dot-atom `local@domain` **before** nodemailer sees it (`schema.js`: no quotes, comments, angle brackets, commas, line breaks), so they are unreachable here. The DNS/TLS `servername` one needs several transports with TLS (we have one, `none`, loopback); the DoS ones need a malicious SMTP server or DKIM (ours is local Mailpit, no DKIM). **Decision: keep 0.2.0 unmodified** (an override to nodemailer 10 would be a combination nobody tested) and add two measured cases built from the advisories to A, which must also be refused with 0 messages: **A6** To `"savunma@masa.local>"@gmail.com`, **A7** To `savunma@masa.local; x@gmail.com`. Bar A becomes 7/7. In a company: track upstream and upgrade after its own review.

## Limits (state them)
- Mailpit stands in for corporate e-mail; a real server would use STARTTLS and real credentials (`SMTP_TLS=starttls`).
- The automated callback tests the mechanism, not a person's attention; one manual `--send` by Feyza is a demo, not a measurement.
- A third-party package is trusted at one reviewed version; an upgrade needs a new review.
