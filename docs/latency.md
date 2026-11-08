# Latency: what is measured and how it is reported

Written 2026-11-08, before any latency number was computed.

## Why
The course asks for latency next to accuracy. For a morning list the question is practical: is the list ready before the 10:00 open, also on a busy day?

## What is measured
1. **Extraction (LLM), per disclosure.** The `seconds` field of every row in `data/eval_set_c.jsonl` (Set C run, 100 disclosures, v3, `gemma4:e4b`, thinking on). It covers the LLM call plus `postprocess_v3`. No new LLM run. Rows with a run error are counted and reported separately, not dropped silently.
2. **Enrichment stages, per disclosure, no LLM.** From a saved morning list (`data/morning_<date>.jsonl`), the extraction fields are kept and each later stage is timed on its own, with the same functions `morning.py` uses:
   - index check (`rag_index.update`, once per run; embeds only new disclosures),
   - importance score (`importance.score_result`),
   - price reaction (`morning.reaction`),
   - company history (`morning.history`),
   - similar earlier disclosures (`rag_index.similar_earlier`).
   Each stage runs `REPEATS=5` times over the day's disclosures. The first repeat (cold: model and file loading) is reported apart from the median of the other four (warm). Nothing is written to `data/morning_*`.
3. **Code checks** (`currency_unclear`, `amount_is_projection`, `cumulative_total`) are regular expressions. They are timed together on the same day's texts in the same way.

## How it is reported
- Extraction: n, run errors, median, p90, max, total, all in seconds. Percentiles by nearest rank.
- Stages: median warm seconds per disclosure per stage, and the cold first run.
- A busy-day estimate, labelled **computed, not measured**: 8 disclosures (the busiest day in the archive) x p90 extraction + stages. A typical day uses 2 disclosures (the median).
- Conditions stated with the numbers: one Mac (Apple Silicon), Ollama local, other programs open, not a controlled benchmark.

## Not a pass/fail rule
There is no latency limit to pass. Collection runs at 23:43 and the list is needed by 10:00, so any number under an hour for a busy day is enough for this use. The numbers are reported as they come out.

## Not measured here
- Agent routing (one LLM call per question): needs a fixed question set written by Feyza.
- Collection time (Matriks API, 1 request/s): logged by the nightly job, not part of this.
