# MCP v2: transport parity without the LLM's own variation (rule, written before code and run)

Date: 2026-11-14. v1 (`docs/mcp_rule.md`) → `MCP_OFF`: M1 11/12, the one difference was inside the LLM card section of `company_brief` (two processes, two extractions, different output at temperature 0); M2 0.011 s. v1 stays as recorded. v2 asks the question MCP is responsible for: does the transport carry the tools' output unchanged? The LLM's variation is measured separately (`docs/repeatability_rule.md`).

## Measurement (new fixed inputs, Feyza runs it once: `scripts/mcp_client.py --parity-v2`)
- **M1a, tools without an LLM step: 10 calls, exact text, bar 10/10.**
  - `morning_list`: 2026-11-12, 2026-08-17 (saved lists; a complete saved list is not rebuilt)
  - `company_history`: KONTR; SARAE with "bu yıl"; ASELS with "geçen ay"
  - `search_disclosures`: "doğalgaz"; "yazılım lisans sözleşmesi"; "elektrik" with symbol KONTR
  - `why_moved`: KONTR 2026-09-17; ASELS 2026-10-15
- **M1b, `company_brief` (has an LLM step): KONTR and ASELS.** The answer is split at its `## ` headings. Header plus sections 2-4 (price reaction, 12 months, similar; code only) must be identical: **bar 2/2**. Section 1 (LLM card) is reported as same / different, no bar.
- **M2:** median extra seconds of MCP over the direct call on the warm (second) pass of the 12 calls: **≤ 0.5 s**.

## Decision (fixed now)
M1a 10/10, M1b 2/2 and M2 ≤ 0.5 s → `ADOPT_MCP_V2`: server, client and agent adopted. Otherwise `MCP_V2_OFF`. Nothing changes after the run.
