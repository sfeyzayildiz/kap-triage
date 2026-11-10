# Cited answers v3: dev choice and held-out decision (rule written before both runs)

Date: 2026-11-10. Committed before the v3 dev run and before any held-out run.

## Background
- v1 (`docs/cited_answer_rule.md`) on dev: not adopted (negatives 4/7, 0 abstentions).
- v2 on dev (iteration only, no decision): a gate call made negatives 6/7 but refused 15 answerable questions (A 34/54); for 10 of the refused ones v1 had answered with the gold citation. All 6 invalid outputs stopped at `num_predict` (1024) while a normal answer is ~100 tokens: repetition loops.

## v3 changes
- Writer: same prompt, JSON schema with limits (≤ 4 sentences, ≤ 400 characters each, sources only `K1`..`K5`, 1-5 per sentence), `num_predict` 1024. The code checks of v1 stay as they are.
- Three gates are recorded per question, the writer always runs; a **variant** = one gate, optionally with a quote check:
  - `g1`: the v2 gate (yes/no, thinking on).
  - `g2`: evidence-first gate, thinking off: copy the sentence that answers the question (≤ 300 chars) or leave empty, then `answers` true/false.
  - `g3`: the same, thinking on.
  - `q` suffix: the gate's yes counts only if its quote passes a code check (≥ 4 words of ≥ 3 letters, ≥ 80% of them found in the sources).
  - `none`: no gate.
  - Gate says no → abstain; gate output invalid → `gate_error` (no answer shown).

## Dev choice (66 dev questions; iteration, not a decision)
Among `none, g1, g2, g2q, g3, g3q`: keep those with negatives not answered ≥ 6/7; pick the highest A (shown share among answerable with gold in top 5); ties → lower median seconds. If none reaches 6/7: highest C, then A, then seconds. The choice is written into `CHOSEN` in `scripts/eval_answers.py` and committed before the held-out run.

## Held-out decision (once)
- Set: the 53 Set C questions (48 answerable, 5 negative; not used for any answer run) + Feyza's 10 new negatives (`data/rag_questions_neg.jsonl`, written 2026-11-10 with `write_negatives.py`, top-5 checked by her) = 63 questions, 15 negative.
- Bars (same as v1 except C as a share): **A ≥ 0.80, B ≥ 0.90, C ≥ 0.80 (≥ 12 of 15), D ≥ 9/10 (Feyza's yes/no on 10 shown answers, seed 20261110), E median ≤ 30 s** (writer + chosen gate; retrieval excluded).
- All pass → show cited answers in the agent's search tool (chosen variant); otherwise not adopted, the list stays, reported as it comes out. No v4 on these 63 questions.

## Honest limits
- The new negatives are "none of the top 5 answers it", not "nothing in the corpus answers it".
- Dev is used twice for iteration (v2, v3); its numbers are reported only as dev numbers.
- D checks 10 answers; meaning errors in the other answers are not measured.
