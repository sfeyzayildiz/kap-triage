# MCP server for the agent's tools: rule, written before code (approved by Feyza 14 Nov)

Date: 2026-11-14. The instructor asked for MCP (course day 7). The agent's tools are plain Python functions; MCP (Model Context Protocol) exposes them through a standard interface, so any MCP client can list and call them.

## Design
- `scripts/mcp_server.py`: official Python SDK (`mcp==1.30.0`, FastMCP), **stdio transport only** (no network port; the client starts the server as a child process).
- **Read-only tools**, each a thin wrapper around the existing, measured tool code (same text output):
  `morning_list(day)`, `company_history(symbol, period?)`, `search_disclosures(query, symbol?)`, `why_moved(symbol, day)`, `company_brief(symbol)`. Periods use `periods.py` (adopted 13 Nov). No write tool (review decisions stay in the panel).
- **Local clients only.** Tool results contain licensed Matriks data (amounts). A cloud client (Claude Desktop, ChatGPT and similar) would send them out of the machine, so none is configured or documented as an option; README and the server's own description say so.
- Demo client for the presentation: the official **MCP Inspector** (local web UI on 127.0.0.1, started with `npx` and a pinned version; Node installed by Feyza on 14 Nov). It only lists and calls the tools; no model.
- Clients in the repo:
  1. `scripts/mcp_client.py`: lists the tools and calls one (demo and measurement).
  2. `scripts/mcp_agent.py`: a tool-calling agent: the local model (`gemma4:e4b`, Ollama) gets the MCP tool list and **chooses the tool itself** (course day 7 "tool calling"), then the tool runs through MCP. It is a comparison with our constrained router, not a replacement.

## Measurement (Feyza runs it; inputs fixed now)
- **M1 parity:** 12 fixed calls (below), each through MCP and directly. Same text: **12/12** required.
  - `morning_list`: 2026-09-17, 2026-04-22
  - `company_history`: SARAE; ASELS with period "son 3 ay"; KONTR with period "geçen yıl"
  - `search_disclosures`: "Irak projeleri"; "savunma ihracat sözleşmesi"; "enerji santrali" with symbol SARAE
  - `why_moved`: SARAE 2026-09-18; KONTR 2026-10-28
  - `company_brief`: SARAE; ASELS
- **M2 overhead:** median extra seconds of the MCP call over the direct call, measured on the second (warm) run of the same 12: **≤ 0.5 s**.
- **M3 (report only, no bar):** the 16 route questions with a non-`unknown` gold intent (`data/route_questions.jsonl`), once through `mcp_agent.py`: right tool chosen n/16, wrong tool, no tool call, median seconds; next to the LLM router's 10 Nov result on the same 16. These questions are dev data; the comparison shows the trade-off, it changes nothing in production.

## Decision (fixed now)
M1 = 12/12 and M2 ≤ 0.5 s → `ADOPT_MCP` (server, client and agent in the repo, architecture and README updated). Otherwise `MCP_OFF` (code kept as a record). A failed parity before the measured run is a bug and may be fixed (integration, not tuning); after the measured run nothing changes. M3 is reported as it comes out.

## Limits
stdio only (one local client at a time); no authentication, because nothing listens on the network. The tool-calling agent is measured on 16 dev questions only.
