# Cited answers v4: a larger local model (rule written before code and before any run)

Date: 2026-11-11. Committed before the v4 code, before any v4 output and before any held-out run.

## Background
- v1-v3 used `gemma4:e4b` (`docs/cited_answer_rule.md`, `docs/cited_answer_v3_rule.md`). When an answer was shown it cited the gold disclosure (v1 44/45), but the model did not know when to stay silent: without a gate negatives 4/7; with a strict gate it refused about a quarter of answerable questions (v3 `g1`: A 37/54). 12-18% of writer outputs looped until `num_predict`.
- The v3 held-out run was **not** done (decision before any held-out output), so the 63 held-out questions are still unused.
- Hypothesis: both problems are model capacity. `gemma4:26b` is installed locally (Mac with 32 GB). It has not been used for answers before.

## v4 (only the model changes)
- Model: `gemma4:26b` for the writer and the gates. Prompts, schema (`AnswerV3`: ≤ 4 sentences, ≤ 400 characters, sources `K1`..`K5`), sources (rerank top 5, 1500 characters each), code checks (citations, numbers) unchanged from v3. Temperature 0, `num_ctx` 8192, writer `num_predict` 1024.
- **Thinking off everywhere.** Reason, written before the run: on 2026-10-28 `gemma4:26b` with thinking on timed out at 600 s on 24 of 87 extraction calls; that is unusable for a 30 s latency bar.
- Gates recorded per question (the writer always runs); a variant = one gate:
  - `none`: no gate.
  - `g1n`: the yes/no gate of v2/v3 (`GATE_PROMPT`), thinking off, `num_predict` 256.
  - `g2`: the evidence-first gate of v3 (`EVIDENCE_PROMPT`), thinking off, `num_predict` 256.
  - `g2q`: `g2`, and its yes counts only if the quote passes the v3 code check (≥ 4 words of ≥ 3 letters, ≥ 80% found in the sources).
  - Gate says no → abstain; invalid gate output → `gate_error` (no answer shown).

## Dev choice (66 dev questions; iteration, already used by v1-v3, so not a decision)
Same as v3: among `none, g1n, g2, g2q` keep those with negatives not answered ≥ 6/7; pick the highest A; ties → lower median seconds. If none reaches 6/7: highest C, then A, then seconds. Written into `CHOSEN['v4']` in `scripts/eval_answers.py` and committed before the held-out run.

**Gate to the held-out run (new, written now):** the held-out set is run only if the chosen variant has on dev **A ≥ 0.80 and C ≥ 6/7**. Otherwise v4 is not adopted, the held-out set stays unused, and the dev numbers are reported as dev numbers.

## Held-out decision (once)
- Set: 53 Set C questions (48 answerable, 5 negative) + Feyza's 10 negatives (`data/rag_questions_neg.jsonl`) = 63 questions, 15 negative. None used by any answer run.
- Bars (same as v3): **A ≥ 0.80, B ≥ 0.90, C ≥ 0.80 (≥ 12 of 15), D ≥ 9/10** (Feyza's yes/no on 10 shown answers, seed 20261110), **E median ≤ 30 s** (writer + chosen gate; retrieval excluded).
- All pass → cited answers shown in the agent's search tool (chosen variant, `gemma4:26b`), with its own PR. Otherwise not adopted; the list stays; reported as it comes out. No v5 on these 63 questions.

## Honest limits
- Dev has been used for iteration four times now (v1-v4); only held-out numbers count.
- The negatives are "none of the top 5 answers it", not "nothing in the corpus answers it".
- D checks 10 answers; meaning errors in the other answers are not measured.
- A larger model also means more memory and slower answers; E measures the speed on this Mac only.
