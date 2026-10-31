# RAG embedding model choice: decision rule (written before measurement)

Date: 2026-10-30. Committed before any model is run on the questions.

## Setup (fixed)
- Documents: `scripts/build_docs.py`, one per disclosure, header + normalized text. Same for every model.
- Questions: `data/rag_questions.jsonl`, 66 (59 answerable, 7 negative). No question is added, removed or edited after the first run.
- Model-specific query/passage prefixes are used only if the model card requires them.
- Retrieval: cosine similarity over the full archive, no filters.

## Candidates (fixed before the first run)
- `bge-m3` (Ollama): multilingual baseline, 8192 tokens, MIT.
- `qwen3-embedding:0.6b` (Ollama): instruction-aware, Apache-2.0.
- `ytu-ce-cosmos/turkish-e5-large` (sentence-transformers): Turkish retrieval fine-tune of multilingual-e5-large-instruct, 512 tokens, MIT. Truncated docs are reported.

Larger qwen3 variants are out of scope this round.

## Metrics
- Primary: recall@5 on the 59 answerable questions (gold news_id in top 5).
- Secondary: recall@1.
- Reported separately: misses at @1 where the top hit is the same company but a different disclosure ("wrong same-company").
- Negatives: top-1 similarity is recorded; not used for the choice (answer/abstain is the generator's job).

## Decision
1. Pick the model with the highest recall@5.
2. If the gap to the next model is 3 questions or fewer (about 5 points), it is a tie: pick the higher recall@1.
3. Still tied: pick the smaller / faster model.
4. If the chosen model has recall@5 below 0.85, add BM25 hybrid as the next step instead of tuning on these questions.

## Honest limit
The same 66 questions are used for selection, so the winner's score is optimistic. A held-out question set is needed for an unbiased number.