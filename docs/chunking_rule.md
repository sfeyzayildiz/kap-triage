# Chunking ablation: one document per disclosure vs. course-style chunks (rule written before the run)

Date: 2026-11-11. Committed before any chunked index exists. Report only.

## Why
The course RAG lab chunks documents (420 characters, 80 overlap). We index one document per disclosure and justify it by length (median 52 words, 8 of ~1280 cut at 512 tokens), which is a reason, not a measurement. This ablation measures it with the same embedding model and the same questions.

## Method (fixed)
- `scripts/build_chunks.py`: for every disclosure, the same normalized text as `build_docs.py`, split into chunks of **420 characters with 80 characters overlap** (the lab's numbers, applied to characters; a chunk never starts inside a word when a space is available in the last 40 characters), each chunk prefixed with the same header line (`SYMBOL | date | kind | headline`) so a chunk still says which company and date it belongs to. Written to `data/rag_docs_chunks.jsonl` with `news_id` and `chunk` index. Counts printed: documents, chunks, chunks per document (median, max).
- Retrieval: `eval_retrieval.py --docs chunks` on **dev** (66 / 59), `--method embed` (embedding only, like the model-choice run) and `--method rerank` (the live pipeline). Chunks are ranked by cosine; a disclosure's rank is the rank of its best chunk (first occurrence in the ranking, duplicates dropped). The rerank reads the question with the best chunk's text. Query prefix, model and cache logic unchanged; chunk vectors get their own cache file.
- Compared with the one-document numbers already recorded on dev: embed recall@5 0.864 / recall@1 0.729; rerank recall@1 43/59, recall@3 52/59, recall@5 55/59.

## Decision
None. One document per disclosure stays whatever the result; a switch would need its own rule and a held-out set. The table answers "why no chunking?" with a number, and if chunks were clearly better that would be reported as an open point for the final.

## Honest limits
Dev only (optimistic set). One chunk size. Set C questions are not reused.

## Amendment 1 (before any chunk file or run)
The self-test showed that aligning only the chunk *end* to a space lets the next chunk (end − 80) start inside a word. The start is now also moved forward to the next space when one exists within 40 characters. Chunk size and overlap unchanged.
