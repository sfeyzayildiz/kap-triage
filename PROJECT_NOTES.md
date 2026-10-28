# Project Notes (Matriks Rules)
- Maximum 1 request per second (1 req/sec) to the API.
- Raw data must never be uploaded to GitHub.
- Matriks must be mentioned as the data source in the project presentation.
- API access is valid until the end of December.
- At most one pull per day (Matriks, 28 Oct). Use the prod API; apitest data may be incomplete.
- The token lives only in `.env` (`KAP_TOKEN`). Remove it before sharing any email thread.
- Never call `new-business-api` or `lastN` without parameters.

## KAP Manual Discovery Notes (New Business Relationships)
- **Amount and Currency:** Explicitly stated in the text (e.g., 621,000 USD and its TRY equivalent).
- **Counterparty:** Sometimes explicitly named, but often anonymized due to trade secrets (e.g., "a domestic defense industry company").
- **Duration/Delivery Date:** Specific delivery dates or target deadlines are explicitly provided in the text (e.g., 30.11.2026).
- **Data Location:** Primary data points are located directly in the "Explanations" (Açıklamalar) text area. PDF attachments are not required to extract the core information.

## KAP Manual Discovery Example (FORTE Disclosure)
- **Is the amount stated? In which currency?** Yes. The amount is explicitly stated as 621,000 USD (with its approximate TRY equivalent of 30,779,679 TRY).
- **Is the counterparty explicitly named?** No, the company name is concealed due to trade secrets. It is anonymously referred to as "a domestic defense industry company" (yurt içinde yerleşik bir savunma sanayi şirketi).
- **Is there a duration or delivery date?** Yes. A clear deadline is specified in the text, stating the delivery target is by 30.11.2026.
- **Is the information in the disclosure text or in a PDF attachment?** All required information is located directly in the "Explanations" (Açıklamalar) text field. There are no PDF attachments, meaning PDF parsing is not required to extract the data.

## Baseline failure modes (15 manual samples, 12/15 correct)
- id 1: multiple amounts in text, regex picks the first
- id 7: amount written with 'milyon'
- id 14: amount written with 'milyar'

## Extraction Rules
- **counterparty_name**: proper names only (full or partial, e.g. 'Turkcell Grup şirketleri'). Descriptions like 'bir banka' → null.

## Dev set results (15 manual samples, gemma4:e4b)
| field | regex | LLM |
|---|---|---|
| amount | 12/15 | 15/15 |
| currency | 12/15 | 15/15 |

Known LLM issue: hallucinated related_party (id 14)
Note: prompt tuned on these samples, numbers optimistic

## Collector design notes

- **Archive range:** Matriks KAP archive starts January 2024, so a full pull covers roughly 3 years of data.
- **Pagination:** The endpoint returns at least 100 records in a single call (no hard upper limit observed at 100). Full company pulls will still be chunked monthly, so that any hidden limit is respected and a failed request only needs retrying for that month.

## Data quality: disclosures without a Matriks record

205 of 1,269 disclosures have no matching `new_business` record. URL formats are identical, and the gap is spread evenly over time, so this is neither a join error nor a lag.

The cause is the amount: 87% of matched disclosures mention an amount in the text, versus only 14% of unmatched ones. Matriks appears to create a record only when an amount is disclosed. Some companies (e.g. HTTBT, EFORC, DOAS) never appear in `new_business` because they usually omit it.

These ~180 disclosures are where LLM extraction adds the most value: counterparty, subject, duration and origin are in the text, but no structured source covers them.

### Lost currency symbol

The Turkish lira sign (₺) never appears in the collected texts: in 18 disclosures it shows up as a literal `?` right after the amount. Turkish letters survive, so the text was most likely converted to cp1254 upstream, which has no ₺. `llm_extract.py` falls back to reading the currency next to the extracted amount and maps that `?` to TRY.

## Daily collection

- Daily collector (`scripts/daily_collect.py`) re-fetches the last 3 days and sends an ntfy alert (OK / FAILED).
- Planned to run on the rented server, but the server ([server-ip]) cannot reach any Matriks address: TCP timeouts on 443 and 80, while the server firewall allows outbound traffic and the Mac connects fine. Matriks (28 Oct): no IP restriction on their side; forwarded to their systems team. Work continues locally until then.
- Until then it runs on the Mac via launchd (`deploy/com.feyza.kap-daily.plist`), daily at 23:43; runs on wake if the Mac was asleep. Log: `data/daily.log`.
- launchd runs from a separate clone, `~/projects/kap-deploy`, always on `main` (no edits or branches there). Its `data/` and `.env` are symlinks to the dev folder, so there is one database. After every merge: `git -C ~/projects/kap-deploy pull`.
- The server clone and its read-only deploy key are ready if access is granted.

## 2026-10-28: Set A error analysis and adjudication

**Why:** Raw agreement with Matriks (v1 91/100, v2 92/100) mixes real LLM errors with definition differences and Matriks errors.

**Method:**
- Manually reviewed the 10 disclosures where v1 or v2 disagreed with Matriks on amount.
- Wrote annotation rules for the "correct" amount: `docs/annotation_guidelines.md` (v1.0, R1–R5).
- Gold labels for the 10 cases in `data/adjudicated_amount.jsonl` (not in git).
- `scripts/score_adjudicated.py` rescores existing results without rerunning the LLM.

**Results (Set A):**
| Prompt | Raw amount (vs Matriks) | Adjudicated amount | Adjudicated currency |
|---|---|---|---|
| v1 | 91/100 | 96/99 | 97/99 |
| v2 | 92/100 | 96/99 | 97/99 |

1 case excluded as `needs_review` (mixed-currency contract, known gap).

**Findings:**
- After adjudication, v1 and v2 are equal; the raw 1-point gap was noise.
- Matriks was wrong in 3 cases: 2 kept the pre-revision amount, 1 has a value not found in the text.
- All remaining LLM errors map to rules R1–R4 (equivalent currency, VAT, multiple orders, total vs company share).
- v1 found the EGP amount in one case but the currency came back empty. Check currency normalization.

**Caveat:** Rules were derived from Set A errors, so a prompt using them must also be evaluated on another set.

**Next:** `extract_v3` with R1–R5 in the prompt, evaluated on Set A and a second set.

## 2026-10-27/28: Postmortems

### Incident 1: Daily collector failed on DB lock
- **What happened:** At 23:43 the launchd collector failed with `Could not set lock`. ntfy sent FAILED.
- **Impact:** No data loss. Collector rerun manually, OK.
- **Root cause:** `eval_vs_matriks.py` kept a DuckDB connection open for ~50 min during the LLM loop. A `read_only=True` connection still holds a lock: many readers are allowed, but no writer while a reader is connected.
- **Fix:** Eval closes the connection right after loading its rows. `daily_collect.py` retries up to 3 times, 5 min apart, on lock errors only. Any other exception now also sends a FAILED alert (before, an exception in `counts()` would crash silently).
- **Lesson:** Keep DB connections short in long-running jobs. Retry only transient errors.

### Incident 2: Eval hung on a stuck Ollama model
- **What happened:** At sample 75 the model stayed in `Stopping...`. The eval waited forever because `call_llm` had no timeout.
- **Impact:** Eval stalled until noticed. Ollama restarted, eval resumed from where it stopped.
- **Root cause:** No timeout on the Ollama HTTP call.
- **Fix:** `ollama.Client(timeout=LLM_TIMEOUT)` (default 120 s, set via env). The eval stops after 3 errors in a row, and a resumed run retries failed rows instead of treating them as done.
- **Lesson:** Every network call needs a timeout. A resumable job must not mark failures as finished.

**Verified:** Timeout and error-streak stop tested with `LLM_TIMEOUT=0.01`. Lock retry tested by holding a write connection for 15 s while running the collector with `LOCK_WAIT=10`.

## 2026-10-28: Extraction v3 results

### Setup
- Model `gemma4:e4b`, `temperature:0`, `num_ctx:8192`, Ollama defaults (thinking on, see Findings 4).
- Prompt `prompts/extract_v3.txt` as of `ece690d`; code checks in `postprocess_v3`.
- Gold: `data/adjudicated_amount.jsonl` under guidelines v1.1 (12 rows, 3 `needs_review` excluded from scoring).
- This table supersedes the 96/99 table in "Set A error analysis" above: the gold has since grown from 10 to 12 rows.

### Dev set (15 samples)
amount 14/15, currency 14/15, event_type 14/15, counterparty_origin 11/15, related_party 14/15.
- Prompt fixes came from dev set errors, so these scores are optimistic.
- id 1 is still wrong (TL picked over EUR) but flagged by `try_stated_but_currency_try`.
- id 14 gold (`contract`) is disputed: the text says "Alınan sipariş".

### Set A (100 samples), all runs scored against the same gold
| run | raw amount | raw currency | adj. amount | adj. currency |
|---|---|---|---|---|
| v1 | 91/100 | 96/100 | 94/97 | 95/97 |
| v2 | 92/100 | 97/100 | 94/97 | 95/97 |
| v3 interim (before `ece690d`) | 90/100 | 94/100 | 95/97 | 95/97 |
| v3 final (`ece690d`) | 89/100 | 93/100 | 95/97 | 95/97 |

- Differences of 1 are within noise: v3 is not measurably more accurate than v1/v2.
- v3's gain is in review flags: both v3 final amount errors (5510831, 6179778) carry `multi_currency_items`, so there are **0 silent errors** (wrong and unflagged).
- Raw scores drop because v3 disagrees with Matriks where Matriks is wrong, or returns null with a flag.

### Findings
1. **Interim vs final run.** The first v3 Set A run started around 03:45, before the prompt fix `ece690d` (04:01). The prompt is loaded once at start, so that run measured an uncommitted prompt.
2. **Multi-currency deals** (5510831, 5927197, 6179778, 6362247). Matriks is inconsistent: sometimes it keeps one currency's part, sometimes the TL total stated in the text. Guidelines v1.1 R3: multi-currency orders get a null amount and a review flag.
   - Open for v4: use the TL total *written in the text* (`amount_try_stated`) as the headline amount, applied in code, flagged `mixed_currency`. The LLM must not add figures itself.   
   - `amount_try_stated` was filled in 2 of 4 cases, both correct: 6179778 (750,561,215 TL) and 6362247 (356,454,030.38 TL). The 6362247 figure is the grand total written in the text and equals the sum of its six item totals, so code can verify it.
3. **6179778 is an invitation to sign**, not a signed contract. This is an `event_type` question.
4. **Thinking mode.** Ollama runs gemma4 with thinking on by default (e4b and 26b). Short test on e4b: 307 vs 43 tokens, 6.2 s vs 0.6 s. All v1–v3 results used thinking on. gemma4:26b timed out at 120 s, so its run uses `LLM_TIMEOUT=600`.
5. **Run-context dependence.** 5510831 was correct 3/3 when run alone, but wrong inside the 100-sample run. Hypothesis: long thinking chains amplify small numerical differences (e.g. KV cache reuse). To be tested with thinking off.

### Lessons
1. In a small model, changing one part of the prompt shifts other fields (`counterparty_origin` moved). Re-measure all fields after every prompt change.
2. `temperature:0` is not fully deterministic on Ollama/Metal, and output can depend on the run context. Expect ±1–2 on ~100 samples; report ranges, not single numbers.
3. A general rule can override a field-specific rule ("boolean flags default to false" dropped `related_party` to 1/15).
4. Code checks catch what the prompt misses (id 1 flagged). A check needs a guard against false alarms (the foreign-currency mention test).
5. Tuning on the dev set makes dev scores optimistic. Measure on separate sets.
6. Decision ladder: code rules, prompt, bigger model (ceiling test), fine-tuning, human review. Set a "good enough" bar first.
7. Tie every reported metric to the commit and settings (model, prompt, thinking, timeout) that produced it.
8. Report two numbers: silent errors (wrong and unflagged) and review rate.

### Next
- Ceiling test: `gemma4:26b` on Set A (running).
- Thinking-off experiment on e4b (speed vs accuracy); `OLLAMA_THINK` setting and git commit in eval rows.
- v4: multi-currency rule (guidelines v1.2), then the second-set measurement.
