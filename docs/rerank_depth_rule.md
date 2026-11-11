# Rerank depth ablation: K = 10 / 20 / 50 (rule written before the run)

Date: 2026-11-11. Committed before any number for K ≠ 20 exists. Report only.

## Why
`docs/rerank_rule.md` fixed K = 20 candidates for the cross-encoder before measuring and adopted rerank on Set D. K itself was never compared. An ablation answers "why 20?" with numbers and shows the cost side (seconds per question).

## Method (fixed)
- Same pipeline as the live system: `turkish-e5-large` top K → `bge-reranker-v2-m3` → top 5. Only K changes: **10, 20, 50**. Same cached document vectors, same questions, same code path (`eval_retrieval.py --method rerank --rerank-k K`).
- Set: **dev only** (66 questions, 59 answerable). Set C and Set D are not reused (their plans forbid it; D was already used twice).
- Reported per K: recall@1, recall@3, recall@5, embedding recall@K (the ceiling), rerank seconds per question. K = 20 is re-run so all three come from the same session (the earlier dev number for K = 20 stays in the notes as a check).

## Decision
None. K stays 20 whatever the table shows: dev questions were used to pick the embedding model and the rerank was adopted on Set D with K = 20. A change of K would need its own rule and a new question set.

## Honest limits
Dev numbers are optimistic (used for model choice). 59 questions: differences of 1-2 are noise.
