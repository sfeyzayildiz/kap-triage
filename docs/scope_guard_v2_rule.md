# Scope guard v2: the router may say "out of scope" (rule, written before code and questions)

Date: 2026-11-12. v1 (`docs/scope_guard_rule.md`, a fixed word list) blocked 7/10 out-of-scope questions (bar 9) with 0/10 and 1/185 false blocks → off. Lesson: a fixed list misses wordings it did not foresee. v1's 20 questions are dev now; nothing below is tuned on them (their texts were never seen by the code author).

## Change
- The LLM router gets a sixth intent `out_of_scope`, described in the prompt as: questions whose answer is not in new-business disclosures — other disclosure types (dividend, capital increase, buyback, general assembly, IPO), valuation or investment advice (target price, buy / sell / hold), financial statements and results (balance sheet, profit, EBITDA), macro and the general market (rates, FX outlook, index forecast). Everything else unchanged (same model, temperature, schema otherwise).
- v2 decision = v1 word list **or** router `out_of_scope`. Out of scope → the existing scope line + help text (no search, no card).
- Switch `SCOPE_V2` (True for the measurement). `SCOPE_SWITCH` (v1 alone) stays False.

## Measurement (Feyza runs it; questions written after this commit, without reading the prompt text)
- New questions (`scripts/scope_eval.py --write --version 2`, `data/scope_questions_v2.jsonl`): **10 out-of-scope** (any of the four groups above, her own wording, a company name or ticker in at least 7) and **10 in-scope** analyst questions. Not reused from v1 or the red team.
- `--run --version 2` once: every new question and every earlier in-scope question (the same 185 sets as v1: route without gold `unknown`, v2, card, brief, RAG dev / C / negatives) goes through the v2 decision; rows stored with the decision only.
- **A** out-of-scope blocked ≥ **9/10**. **F_new** in-scope blocked ≤ **1/10**. **F_old** earlier in-scope blocked ≤ **3/185** (one more than v1's bar: the router now runs on every question, so some noise is expected; fixed before any result). **R** of the 16 route questions with a non-`unknown` gold intent, those whose route the LLM got right in the 10 Nov run and that v2 now blocks: ≤ **1**.
- Median routing time on the new questions ≤ 6 s (router 3.2 s measured on 10 Nov).

## Decision (fixed now)
All bars met → `ADOPT_SCOPE_V2` (`SCOPE_V2=True` stays). Otherwise `SCOPE_V2=False`, code kept as a record. The prompt wording is not changed after seeing a result.

## Limits
Questions written by one person who knows the four groups; the router is the same small model as extraction; macro questions without a company were not part of v1's test.
