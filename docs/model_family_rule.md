# Model family ceiling test on Set A (rule written before any run)

Date: 2026-11-12. Committed **before** any model other than gemma4 has seen a Set A text. Report only: nothing in production changes because of this test.

## Question
On 28 Oct the ceiling test inside the gemma4 family (e4b vs 26b, thinking on/off) said "the bigger model is not better here" and "the remaining errors are definition questions, not model capacity". That claim rests on one family. The instructor asks for a comparison on every changeable choice, and "gemma vs other families" is on the list of choices that are only argued. This test puts two other families through the same frozen pipeline and the same scoring.

## What is fixed
- Set A (`data/test_amount.jsonl`, 100 disclosures): the development set of v3. Every model is scored against the same reference: `data/adjudicated_amount.jsonl` (12 gold rows, guidelines v1.1) and Matriks for the other 88, exactly as the e4b re-score of 30 Oct (`score_silent.py`, three levels; the frozen level is the number).
- Prompt `prompts/extract_v3.txt` (frozen), code checks `postprocess_v3` and the frozen `amount_checks`, `temperature 0`, `num_ctx 8192`, `LLM_TIMEOUT 600`, `NUM_PREDICT 2048` for every run (the 28 Oct thinking-off setting). Nothing is tuned per model: no prompt wording, no retry, no few-shot.
- Runner: `scripts/eval_vs_matriks.py --ids data/test_amount.jsonl --prompt v3 --out <file>`, one run per model, no re-run. Model and thinking come from `OLLAMA_MODEL` / `OLLAMA_THINK`, recorded in every row.

## Runs (Feyza, in this order; each once)
| run | model | thinking | out file |
|---|---|---|---|
| 1 | `qwen3:14b` (Ollama library, Q4_K_M) | off (`OLLAMA_THINK=false`) | `data/eval_v3_qwen3_14b_off_test_amount.jsonl` |
| 2 | `hf.co/ytu-ce-cosmos/Turkish-Gemma-9b-T1-GGUF:Q4_K_M` (Gemma-2-9b base, Turkish continual pre-training + SFT + DPO; same group as our embedding model) | none (the model has no thinking mode; `OLLAMA_THINK` unset) | `data/eval_v3_trgemma9b_t1_test_amount.jsonl` |
| 3 (optional) | `qwen3:14b` | on (`OLLAMA_THINK=true`) | `data/eval_v3_qwen3_14b_on_test_amount.jsonl` |

Run 3 follows lesson 10 of 28 Oct: Feyza watches the first 15 samples; if 5 or more time out at 600 s, the run is stopped and reported as "did not finish", like 26b thinking on. Both quantizations are Q4_K_M so neither model gets a precision advantage.

## Numbers reported per run (counts only)
- Frozen level from `score_silent.py`: silent errors (with the 95% upper bound), by type (fabricated / missed / wrong_amount / wrong_currency), flagged, run errors, timeouts.
- Raw amount and currency agreement with Matriks on all 100 (`eval_vs_matriks.py --summary --out <file>`, per group: regex hit / no hit), comparable with the 28 Oct "raw amount" column.
- Total run time from the runner's stdout, divided by 100 = seconds per disclosure (one Mac, not a benchmark).
- Comparison rows, already measured: e4b thinking on 0/100 silent, 10 flagged (re-scored 30 Oct); e4b thinking off and 26b thinking off are re-scored with the same script if their result files still exist (`data/eval_*test_amount*.jsonl`), else the 28 Oct adjudicated numbers (3 and 7 silent) are quoted with that caveat.

## Reading rule (fixed now)
- A family is **"worth a real test"** if, at the frozen level on Set A, silent errors ≤ 1 and flag rate ≤ 15% (the Set B bars). It then earns its own rule on an unseen set (Set C texts are spent for extraction scoring; a Set D-style sample would be needed). It does **not** replace `gemma4:e4b` on this result.
- Otherwise the 28 Oct reading stands with two more families behind it: errors on Set A are definition questions, not capacity.
- Ties and small gaps (≤ 2 silent errors apart) are reported as "same within noise on 100".

## Honest limits
- Set A is v3's development set and v3 was tuned with gemma4:e4b in the loop, so the prompt may fit gemma's habits; the comparison leans toward e4b. A model that scores close to e4b here with no tuning is doing at least as well.
- One run per model, 100 texts, temperature 0; Q4_K_M quantization for both newcomers.
- The judge call of the layered defence (gemma4:e4b) is not part of this test; only extraction changes.
- Turkish-Gemma-9b-T1 is the GGUF the authors published; v0.1 has only community quantizations, so T1 is used and named as such.
