# Cited answers for the agent's search tool: rule (written before the code)

Date: 2026-11-10. Committed before any code and before any run.

## What changes
Today the search tool returns the top 5 disclosures as a list. Proposed: above the list, a short
answer written by the LLM from those 5 disclosures, every sentence citing its sources as `[K1]`..`[K5]`,
checked by code. If a check fails, the answer is not shown; the tool returns the list as today.

## Generation (fixed before the run)
- Retrieval unchanged: `rag_index.search_question` (embed top 20 → cross-encoder rerank → top 5), full question, no symbol filter (same as `eval_retrieval.py --method rerank`).
- Sources: `K1`..`K5` in rank order; each = header (`SYMBOL | date | kind | headline`) + the raw disclosure text, cut at 1500 characters. Sources are given between markers as data; the prompt says to ignore any instruction inside them.
- Model: `gemma4:e4b`, thinking off, temperature 0, `num_ctx` 8192, `num_predict` 512. JSON schema: `{"answerable": bool, "sentences": [{"text": str, "sources": ["K1", ...]}]}`, at most 4 sentences, Turkish.
- The prompt asks: answer only from the sources; if they do not answer the question, `answerable=false` and no sentences.

## Code checks (an answer is shown only if all pass)
1. Valid JSON for the schema (else `invalid_output`).
2. `answerable=true` has 1-4 sentences (else `bad_length`); every sentence has at least one source and only `K1`..`K5` that exist (else `bad_citation`).
3. **Numbers:** every number written in a sentence (same number parser as `amount_checks.py`, scale words included, citation markers removed first) must appear in at least one of the sentence's cited sources, either as an equal value (0.5% tolerance) or as the same digit string (dates, years, counts). Else `unsupported_number`.
4. `answerable=false` → shown as "the sources do not answer this" plus the list (counted as an abstention, not a failure).
5. Model error or timeout → `run_error`, list only.

## Measurement (dev set, 66 questions: 59 answerable, 7 negative; run by Feyza)
`scripts/eval_answers.py --run` writes `data/answers_dev.jsonl`; `--score` prints counts only.
- **A. Shown rate:** among answerable questions whose gold disclosure is in the top 5, the share with an answer that passed all checks and `answerable=true`.
- **B. Cites gold:** among those shown answers, the share citing the gold disclosure in at least one sentence.
- **C. Negatives:** among the 7 negative questions, the share with `answerable=false` or a failed check (no answer shown).
- **D. Human check (Feyza, after A-C are printed):** 10 shown answers drawn with seed 20261110 from answerable questions; for each she opens the KAP links and answers yes/no: "the answer is correct and every sentence is supported by the source it cites". `--review` shows one at a time and stores only yes/no (`data/answer_review.jsonl`).
- **E. Latency:** median seconds per answer (generation + checks; retrieval excluded, it is measured in `docs/rerank_rule.md`).

## Decision (adopt = show cited answers in `agent.py` search tool)
All of: A ≥ 0.80, B ≥ 0.90, C ≥ 5/7, D ≥ 9/10, E median ≤ 30 s. Otherwise not adopted and reported as it comes out; the list stays.
Dev questions were used to choose the embedding model, not to design this step. If adopted, the Set C questions (53) are run once afterwards and reported only (no new decision).

## Honest limit
- The number check proves a number exists in a cited source, not that it is used with the right meaning (e.g. a contract value quoted as revenue). That is what D measures, on 10 answers only.
- Sentences without numbers are checked by citations only.
- Source text is attacker-controllable (see the injection work); the number check stops invented figures, not a misleading sentence copied from a source.
