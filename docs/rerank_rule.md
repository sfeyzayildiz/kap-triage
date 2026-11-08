# Cross-encoder rerank: decision rule (written before measurement)

Date: 2026-11-08. Committed before any rerank number is computed.

## Why
On Set C (48) and Set D (20), almost every rank-1 miss of the embedding is the right company with the wrong disclosure (16/16 and 5/5). Three embedding models showed the same pattern on dev (31 Oct), and BM25 / hybrid did not clear the bar on Set D (`docs/bm25_hybrid_rule.md`). A bi-encoder compresses each disclosure into one vector, and one company's disclosures look alike. A cross-encoder reads the question and the disclosure together and can compare details (country, counterparty, date).

## Method (fixed now, not tuned afterwards)
- **Stage 1:** the current system: `ytu-ce-cosmos/turkish-e5-large`, same query prefix, same cached document vectors. Its top `K=20` go to stage 2.
- **Stage 2:** `BAAI/bge-reranker-v2-m3` (sentence-transformers `CrossEncoder`, local, multilingual, Apache-2.0), `max_length=512`. Input pairs: (question as written, no prefix; document text from `data/rag_docs.jsonl`). The 20 candidates are reordered by the cross-encoder score (ties keep the embedding order). Documents below rank 20 keep their embedding order.
- No threshold, no score mixing with the embedding.

## Development (dev questions, 66 / 59)
- `eval_retrieval.py --method rerank` on dev, run by Feyza. Optimistic, for bug catching only.
- Also reported: embedding recall@20 (the ceiling: rerank cannot recover a disclosure that stage 1 did not return).
- If rerank is worse than embed on dev in recall@1 or recall@5, stop and look for a bug. Parameters are not changed.

## Held-out decision (Set D, 20 answerable)
- Set D was written by Feyza before any system output and has not been used to tune anything. It was used once to compare BM25 / hybrid with embed; this is its second comparison, stated here. Set C is not used (its plan forbids reuse for model choice).
- **Adopt rerank if** recall@1 rises by at least 2 questions over embed (15/20 → at least 17/20) and recall@5 drops by at most 1 (at least 18/20).
- Reported either way: recall@1, recall@5, wrong-same-company, per kind, fixed / broken against embed, and seconds per question.

## Latency
- Reported as seconds per question (rerank stage only and total). Not part of the decision; for an interactive agent, under about 3 s per question on this Mac is acceptable. If it is much slower, that is stated as a cost.

## Honest limit
20 questions: a 2-question gain is a practical bar, not a significance test. Set D is now used for a second comparison; if rerank is adopted, a fresh question set should confirm it later.
