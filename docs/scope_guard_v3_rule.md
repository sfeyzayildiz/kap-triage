# Scope guard v3: a separate yes/no judge on the content paths (rule, written before code and questions)

Date: 2026-11-19. Problem B1 (`docs/known_issues.md`): an out-of-scope question that names a company ("ASELS temettüsü ne kadar?") gets a real but unrelated disclosure card or list. Biggest demo risk: the instructor can ask exactly this.

## What we learned from v1 and v2
- v1, fixed word list before the router: blocked 7/10, false blocks 0/10 + 1/185 → off. It misses wordings it did not foresee.
- v2, the router got a sixth intent `out_of_scope`: blocked 10/10 but **29/185** earlier in-scope questions (bar 3) → off. Adding a class to the router's prompt changed its behaviour on every question, and the router is also deciding five other things at once.
- The 40 questions of v1 and v2 and the 16 red-team questions are dev. Claude has never read them; nothing below is tuned on them.

## Change
1. **Router unchanged** (`ROUTER_PROMPT`, five intents, as in production). v1's word list runs first, as in v1 (deterministic, 1/185 false blocks).
2. **A separate judge** (`agent.scope_judge`), called only when the final route would show disclosure content: intent `company`, `detail`, `search` or `brief` (after `route_question`, so after the detail and brief switches). Not called for `morning`, `why_moved`, `unknown` (in scope by construction or already help text).
3. Judge settings: same model and settings as the source-sentence judge, which had 3/200 false alarms (`gemma4:e4b`, temperature 0, thinking off, `num_ctx` 2048, `num_predict` 64, pydantic schema `{"label": "in_scope" | "out_of_scope"}`). Prompt fixed in this commit (`SCOPE_JUDGE_PROMPT` below), one version, no dev iteration. It lists the four groups of v2 and says to answer `in_scope` when unsure.
4. Blocked (word list, or judge `out_of_scope`) → intent `out_of_scope` → the existing scope line + help text: no search, no card. A judge error (no valid label) does **not** block (fails open) and is counted.
5. Switch `SCOPE_V3` (True for the measurement); `SCOPE_SWITCH` and `SCOPE_V2` stay False.

```
SCOPE_JUDGE_PROMPT
You check one question an equity analyst typed into an assistant. The assistant can only answer from
Turkish "Yeni İş İlişkisi" (new business relationship) disclosures: orders, contracts and tenders a
company announced, with their amount, currency, counterparty, duration, subject and date, and the
stock's price move around them.
Answer "out_of_scope" only if the question asks for something these disclosures do not contain:
- other disclosure types: dividend, capital increase, share buyback, general assembly, public offering;
- valuation or advice: target price, buy / sell / hold, valuation ratios such as P/E or P/B;
- financial statements or results: balance sheet, profit, revenue, EBITDA, quarterly results;
- macro or the general market: interest rates, FX outlook, index forecast.
Otherwise answer "in_scope". If you are unsure, answer "in_scope".
Question: {question}
```

## Measurement (Feyza runs it; questions written after this commit, without reading the prompt above)
- **20 new questions** (`scripts/scope_eval.py --write --version 3` → `data/scope_questions_v3.jsonl`): 10 out-of-scope (the four groups, her own wording, a company name or ticker in at least 7) and 10 in-scope analyst questions. Not reused from v1, v2 or the red team.
- `--run --version 3` once: the 20 new questions and the **same 185 earlier in-scope questions** as v1 and v2 (plus the 4 route questions with gold `unknown`, reported only) go through the full v3 decision (word list → router → `route_question` → judge on the content paths). Stored per row: blocked, final intent, judge called, judge label or error, seconds. No question text in the output.
- Bars (v2's bars, so the three versions sit on one ruler):
  - **A** out-of-scope questions that get **no disclosure content** (blocked, or final intent `unknown`): ≥ **9/10**. *Blocked only* is also printed, as v1 and v2 counted it. The change of definition is made here, before any v3 result: what hurts the analyst is a card or list for a question that was not asked; help text does not.
  - **F_new** new in-scope questions blocked: ≤ **1/10**.
  - **F_old** earlier in-scope questions blocked: ≤ **3/185**.
  - **R** route questions (gold not `unknown`) that the LLM routed right on 10 Nov and v3 now blocks: ≤ **1**.
  - **D** median seconds per new question (router + judge): ≤ **6.0**.
  - Judge errors: reported (fail open, so they can only lower A).
- `--score --version 3` once, after the run; counts and indices of misses only, never question text.

## Decision (fixed now)
All five bars met → `ADOPT_SCOPE_V3` (`SCOPE_V3=True` stays; chat only, the guided form is unchanged). Otherwise `SCOPE_V3=False`, code kept as a record, B1 stays an accepted limit. The prompt and the list of content intents are not changed after seeing a result; another version needs new questions and its own rule. Not the nightly path: no kap-deploy pull is needed for the measurement; if adopted, the Docker panel needs a rebuild.

## Approval and code (19 Nov)
Approved by Feyza 19 Nov (before code and questions). Code: `agent.scope_v3` / `call_scope_judge` / `SCOPE_JUDGE_PROMPT` (self-test checks it equals the block above) / `SCOPE_V3=True`; the guard runs only in graphs with the real router (or a judge given in `ctx`), so self-tests never call Ollama. `scope_eval.py --write/--run/--score --version 3`; `--run` refuses uncommitted `agent.py` / `scope_eval.py` and the 23:35-00:10 window; `--write` also refuses v1/v2 questions. agent 95 checks, scope_eval 11; suite 78 ok / 1 skip.

## Result (Feyza, 19 Nov, one run on ed164b5)
- **A** no disclosure content 10/10 (bar 9); blocked only 6/10 (4 went to help text). **F_new** 1/10 (bar 1). **F_old 28/185 (bar 3)**. **R** 1/14 (bar 1). **D** median 3.2 s (bar 6.0). Judge calls 179, errors 0; word-list blocks 7; gold-unknown route questions blocked 1/4 (not an error).
- **Decision: SCOPE_V3_OFF** (F_old missed its bar), `SCOPE_V3=False`, code kept as a record, prompt unchanged.
- Reading: the false blocks fall on every earlier set (route 2, v2 1, brief 8 of 10, RAG dev 8, RAG C 6, RAG neg 3; indices only, texts not inspected). Moving the judge out of the router and onto the content paths did not change the over-blocking (v2 29/185, v3 28/185): the small model as a scope judge is the limit, not where it sits. The brief set's 8/10 is a post-hoc observation, not a basis for a v4. B1 stays an accepted limit; the guided form avoids it.

## Limits
One person writes the questions and knows the four groups; the judge is the same small model as extraction; 10 out-of-scope questions give a wide bound (9/10 → 95% lower bound about 55%).
