# Documentation index

Every measured part of the project has a rule file (`*_rule.md`) that was committed **before** its measurement, and a result recorded in [`PROJECT_NOTES.md`](PROJECT_NOTES.md) (the development log, every decision in order) and [`results.md`](results.md). Read the rule first, then the result. The rule files, the results and `PROJECT_NOTES.md` are a record of what was measured, so they keep the version 1 file names (`scripts/...`); [`v1_to_v2_map.md`](v1_to_v2_map.md) says where each file is now. The measurement scripts are kept out of this repository.

## Start here
| file | what it is |
|---|---|
| [timeline.md](timeline.md) | Day-by-day development log, generated from the git history by a development script. |
| [v1_to_v2_map.md](v1_to_v2_map.md) | Where each version 1 file (`scripts/`) is in the version 2 package (`kap_triage/`), and what was left out. |
| [for_reviewers.md](for_reviewers.md) | A 10-minute review path for a grader or company reviewer, and what is not claimed. |
| [results.md](results.md) | Every measured result on one page, adopted and not adopted. |
| [architecture.md](architecture.md) | How the system is built: nightly path, agent, panel, MCP, n8n (diagrams). |
| [system_card.md](system_card.md) | Purpose, data, measured performance and limits on one page. |
| [known_issues.md](known_issues.md) | Where we were wrong, and what we did about it. |
| [metrics_faq.md](metrics_faq.md) | Short answers to metric questions (Hit@3, silent errors, bounds). |

## Operating the system
| file | what it is |
|---|---|
| [runbook.md](runbook.md) | Nightly job, pulls, pauses, recovery, daily use. |
| [docker.md](docker.md) | Running with Docker (Ollama on the host, `data/` mounted). |
| [n8n_guide.md](n8n_guide.md) | Desk e-mail workflow: import and run. |
| [latency.md](latency.md) | What latency is measured and how it is reported. |

## For readers outside the project
| file | what it is |
|---|---|
| [extending.md](extending.md) | How the system would extend to other disclosure types. |
| [public_release.md](public_release.md) | How the version 1 public copy was built from the private repository (history kept, internal parts removed) and checked. |

## Labeling guidelines and test-set plans
| file | what it is |
|---|---|
| [annotation_guidelines.md](annotation_guidelines.md) | How the gold contract amount is labeled (rules R1-R6). |
| [set_c_plan.md](set_c_plan.md) | Set C, the held-out test of the combined system. |
| [set_c_labeling_guide.xlsx](set_c_labeling_guide.xlsx) | Labeling sheet guide for Set C. |
| [capital_increase_guidelines.md](capital_increase_guidelines.md) | Labeling guideline for the capital-increase pilot. |
| [fdv_guidelines.md](fdv_guidelines.md) | Labeling guideline for the stake acquisition / sale pilot. |

## Decision rules, by part of the system
Each file states the measurement, the bar and what happens on pass or fail. The outcome is in `results.md`.

**Extraction and code checks**
- [set_d_rule.md](set_d_rule.md): two-run disagreement flag and `amount_checks_v2` (both adopted).
- [repeatability_rule.md](repeatability_rule.md): does temperature 0 give the same answer twice?
- [drift_rule.md](drift_rule.md): does extraction still agree with Matriks after Set C?
- [model_family_rule.md](model_family_rule.md): other model families on Set A.
- [regex_baseline_rule.md](regex_baseline_rule.md): "could it be done without an LLM?"
- [fields_rule.md](fields_rule.md): duration, counterparty origin, related party.
- [card_quantities_rule.md](card_quantities_rule.md): operational quantities on the card (not adopted).

**Security (prompt injection)**
- [prompt_injection_rule.md](prompt_injection_rule.md): the attack test.
- [injection_defence_rule.md](injection_defence_rule.md): text-pattern defence (not adopted).
- [matriks_crosscheck_rule.md](matriks_crosscheck_rule.md): Matriks cross-check alone (not adopted).
- [layered_defence_rule.md](layered_defence_rule.md): cross-check + source-sentence judge (adopted).
- [source_sentence_rule.md](source_sentence_rule.md): is the source sentence shown on the card the amount's real source? 32/32 on the saved lists (`SOURCE_OK`).

**Importance and the morning list**
- [importance_score.md](importance_score.md): importance score v1.
- [importance_check_rule.md](importance_check_rule.md): score vs. the author's blind choice (Feyza labeled; not an external analyst).
- [importance_v2_rule.md](importance_v2_rule.md): ordering v2 (adopted).
- [revenue_ratio_rule.md](revenue_ratio_rule.md): gates for the revenue ratio.
- [tcmb_rule.md](tcmb_rule.md): Matriks' FX rate vs. official TCMB rates.
- [forward_test_rule.md](forward_test_rule.md): sealed forward test of "look first".

**Search (RAG)**
- [rag_model_choice.md](rag_model_choice.md): embedding model choice.
- [rerank_rule.md](rerank_rule.md), [rerank_depth_rule.md](rerank_depth_rule.md): cross-encoder rerank and its depth.
- [bm25_hybrid_rule.md](bm25_hybrid_rule.md): BM25 / hybrid (not adopted).
- [chunking_rule.md](chunking_rule.md): one document per disclosure vs. chunks.
- [cited_answer_rule.md](cited_answer_rule.md), [cited_answer_v3_rule.md](cited_answer_v3_rule.md), [cited_answer_v4_rule.md](cited_answer_v4_rule.md): LLM-written cited answers (not adopted).
- [clustering_rule.md](clustering_rule.md): weekly theme clusters.

**Agent and tools**
- [route_rule.md](route_rule.md), [router_v2_rule.md](router_v2_rule.md): question routing.
- [detail_card_rule.md](detail_card_rule.md), [brief_rule.md](brief_rule.md): detail card and company brief.
- [relative_periods_rule.md](relative_periods_rule.md): "geçen hafta", "son 3 ay".
- [scope_guard_rule.md](scope_guard_rule.md), [scope_guard_v2_rule.md](scope_guard_v2_rule.md), [scope_guard_v3_rule.md](scope_guard_v3_rule.md): scope guard (all three not adopted).
- [mcp_rule.md](mcp_rule.md), [mcp_v2_rule.md](mcp_v2_rule.md): own MCP server.
- [smtp_mcp_rule.md](smtp_mcp_rule.md): third-party e-mail MCP server with human approval.
- [n8n_routing_rule.md](n8n_routing_rule.md): desk e-mails through n8n.

**Capital-increase pilot (second disclosure type, not adopted)**
- [capital_increase_pilot.md](capital_increase_pilot.md): design.
- [capital_increase_rule.md](capital_increase_rule.md): measurement rule.

**Stake acquisition / sale pilot (third disclosure type, not adopted)**
- [fdv_pilot_rule.md](fdv_pilot_rule.md): design and measurement rule; C 2/30 silent (bar 1), 6/30 flagged (`PILOT_NOT_ADOPTED`, `LLM_ADDS`).

**Data-vendor auditor (Matriks record vs. KAP text, not adopted)**
- [vendor_audit_rule.md](vendor_audit_rule.md): M1 (existing blind gold) and M2 (new blind pool); strict precision 6/14 is below the 50% bar, so it stays a report tool (`AUDITOR_OFF`).

**Showing the system without licensed data**
- [demo_mode_rule.md](demo_mode_rule.md): panel display flag that hides Matriks-licensed values; leaks 0, adopted in round 1 (version 1 only; version 2 shows made-up sample data instead).
- [kap_kart_rule.md](kap_kart_rule.md): stand-alone card from pasted KAP text (version 1: `kap_kart/`; version 2: `/kart` in the panel, `kap_triage/web/kart.py`); copies hash-checked, leaks 0 in round 3, trap examples 12/12, adopted (Matriks agreed to publishing the code, 19 Nov).
