# How the system would extend to other disclosure types

The prototype covers one KAP disclosure type on purpose (agreed scope; measured end to end). This page answers "does it scale to the others?": which parts are generic, which are per type, and what adding a type costs. Nothing here is built or measured.

## What is generic (reused as is)
| Part | Why it carries over |
|---|---|
| Collection, DuckDB, nightly job, pull guard, alerts | Same API pattern; one more table per type. |
| Pipeline shape: LLM extracts, code checks and flags, never fixes | The principle does not depend on the fields. |
| Injection defence | Layer 2 (the source sentence of a number) works for any extracted number; layer 1 needs a structured record from Matriks for that type, if one exists. |
| Search index, reranker, agent graph, guided form, panel, price chart | Documents are documents; a type filter is one more field. |
| Evaluation method | Rule before the run, dev / held-out split, silent errors with an upper bound, `score_silent.py` levels. |

## What is per type (new work every time)
1. **Schema:** which facts matter. Example: a dividend disclosure has gross / net amount per share, payment date and record date, not a contract value.
2. **Prompt:** a new extraction prompt for that schema (start from v3's structure: rules for revisions, totals vs. shares, equivalents).
3. **Code checks:** contradictions specific to the type (e.g. net larger than gross, payment date before record date).
4. **Gold data:** about 100 disclosures labeled blind for the dev set and another 100 for a held-out set, with a labeling guideline. This is the expensive part: for "Yeni İş İlişkisi" it took the most time.
5. **Importance logic:** what makes this type important to an analyst (for dividends: yield vs price, change vs last year).
6. **Rule and measurement:** pass / fail bars written before the held-out run.

## Rough cost per new type
Schema, prompt and checks: 1-2 days. Labeling 200 disclosures blind: about 6-8 hours of an analyst. Measurement and fixes: 1-2 days. So about a week per type for one person, most of it labeling and measuring, not code.

## Scale
About 15 s per disclosure on one Mac is enough for 1-2 a day; all KAP types are hundreds a day. Options, each to be measured: a GPU server (vLLM or Ollama, batched), a smaller model per type, or extracting only the types an analyst follows. Collection stays one pull per day per provider rule unless Matriks agrees otherwise.

## Order we would follow
Types with a number an analyst acts on and a Matriks record to cross-check first (e.g. capital increases, dividends), free-text-only types later.
