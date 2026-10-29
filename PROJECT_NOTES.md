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
## 2026-10-28: Thinking mode and ceiling test

### Setup
- Prompt v3 (`ece690d`), Set A, same gold as above (guidelines v1.1).
- New settings: `OLLAMA_THINK` (unset keeps the Ollama default, which is on for gemma4) and `NUM_PREDICT` (2048 for thinking-off runs). Every eval row now records `think`, `num_predict` and `git_commit`.

### Results (Set A, adjudicated)
| run | raw amount | adj. amount | flagged | silent errors |
|---|---|---|---|---|
| e4b, thinking on | 89/100 | 95/97 | 10 | 0 |
| e4b, thinking off | 86/100 | 90/97 | 8 | 3 |
| 26b, thinking off | 84/100 | 89/97 | 4 | 7 |
| 26b, thinking on | stopped: 24 of 87 timed out at 600 s | | | |

### Findings
1. **Thinking helps e4b:** +5 adjudicated and 3 fewer silent errors. With thinking off, 4 samples broke (6522576, 5672342, 5713200, 6324169) and 1 was fixed (5927197). Thinking off is about 10x faster (~3 s vs ~20 s per sample).
2. **The bigger model is not better here.** With thinking off, 26b scores like e4b but flags half as often and makes the most silent errors: it is confidently wrong. With thinking on, it fails to finish on 28% of samples, mostly the hard ones (6 of the 12 adjudicated cases).
3. **Remaining e4b errors are definition questions** (multi-currency deals), not model capacity. A stronger family (e.g. Qwen) can be tried later; not a priority.
4. **Decision:** keep `gemma4:e4b` with thinking on. At 1–2 disclosures a day, speed does not matter; accuracy and zero silent errors do.

### Lessons
9. A bigger model can be worse in practice: fewer review flags and more silent errors. Compare flag rate and silent errors, not only accuracy.
10. Check the first 10–15 samples of a long run before letting it finish. The 26b thinking run took about 5 hours to show what was visible in 15 minutes.
11. Every LLM call needs both a timeout and a max-token limit (`NUM_PREDICT`); thinking can run away on hard inputs.


## 2026-10-29: Server access to Matriks

- From the rented server ([server-ip]), connections to `<MATRIKS_API_HOST>` and `analistdocs.matriksdata.com` on port 443 time out (10 s). The same server reaches google.com (HTTP 200).
- From the home connection (Mac), the same hosts answer. Unauthenticated `/dumrul/` returns HTTP 503, which is the normal reply without a token.
- Conclusion: a network rule on the Matriks side blocks this IP or its range. This is not the application-level IP restriction Matriks said does not exist. Reported on 28 Oct; Matriks forwarded it to their system team.
- Until it is fixed, collection runs on the Mac (launchd).
- Check (no token, not a data pull): `curl -sS -o /dev/null -w '%{http_code}\n' --max-time 10 https://<MATRIKS_API_HOST>/dumrul/`. 503 = reachable, timeout = blocked.

### Lesson
- Before trusting a network test, check which machine the prompt belongs to. The first "server" test was run on the Mac by mistake and looked like a success.


## 2026-10-29: Extraction v4 (mixed-currency headline): rejected

### Goal
Resolve mixed-currency deals without a human: the headline is the TL grand total written in the text (guidelines v1.2, R6). The model copies the figure into `amount_try_stated`; code picks the headline (`postprocess_v4`).

### Decision rule (set before the final run)
Adopt v4 only if adjudicated accuracy is at least 95/97 (v3) and there are 0 silent errors.

### Results (Set A, gold v1.2, gemma4:e4b, thinking on)
| run | adjudicated | flagged (of 100) | silent |
|---|---|---|---|
| v3 (rescored on gold v1.2) | 95/97 | 10 | 0 |
| v4, first run | 94/97 | 14 | 1 (5702054) |
| v4b (TL check in code, narrower prompt) | 95/97 | 20 | 1 (6324169) |

Decision: **v3 stays.** v4 stays in the repo as a documented experiment (`prompts/extract_v4.txt`, `postprocess_v4`).

### Findings
- v4 fixed its target cases (6362247, 6179778: correct TL total).
- Prompt changes moved the contract-currency choice on unrelated texts written as "X TL (Y EUR)" without conversion wording: 5702054 in run 1, 6324169 in run 2. Both became silent errors.
- Run-to-run variation: the same text got `mixed_currency` in one run and `multi_currency_items` in another. Code that treats both codes the same kept the headline stable.
- The model put a USD equivalent into the TL field (5453484) and one TL part into the TL total (5418861). `check_try_stated` now flags both.
- The flag rate doubled (10 to 20), which works against the goal of less manual review.
- 5713200: the "₺" sign was lost in the source text (shown as "?"), see "Lost currency symbol".
- Set A was used twice to design v4, so the v4 numbers are optimistic (leakage). Set B is the honest test.

### Kept from this work
- Guidelines v1.2 (R6) and gold v1.2. The old gold is backed up as `data/adjudicated_amount_v1.1.jsonl`.
- The eval scores `headline_amount` when present; new columns `llm_amount_raw` and `headline_source`.
- DZD added to the known currencies. This also changes `unknown_currency_code` for v3.

### Lessons
- A prompt change has side effects on cases it was not written for. Measure the whole set, not only the target cases.
- Write the decision rule before the run, then follow it.
- Prefer flag-only code checks over prompt changes: they are deterministic, unit-tested, and cannot break other cases.
- Do not relabel gold after seeing a model error. 5702054 keeps its Matriks label.

### Next
- Code-only check, no prompt change: "X TL (Y EUR)" without conversion wording gets `currency_unclear`. Measure it on Set B, not Set A.

## 2026-10-29: Set B (honest test set)
- Script: `scripts/sample_set_b.py`, seed 20261029. Source: apitest archive (1273 disclosures with text).
- Excluded by news_id: dev (21 hits for 15 samples, some texts repeat in updates), eval_v1 (100), Set A (100), earlier label set `test_label.jsonl` (45, generated 27 Oct, may have been seen). Total 266, no overlap.
- Pool: 827 matched, 180 unmatched. Set B: 80 matched + 20 unmatched, shuffled together; 13 updates, 55 symbols.
- Unmatched cases test whether the model invents an amount when Matriks has none.
- Frozen file: `data/test_set_b.jsonl` (not in git), file sha1 `FILE_SHA1`. Each row has `text_sha1`; after a prod refresh, relabel only rows whose text hash changed.
- Do not re-run `sample_test_sets.py`: the archive has grown, so it would overwrite Set A with a different sample. Overwrite guard to be added.

### Decision rule (set before labeling and before the run)
- System under test: v3 prompt + code checks frozen before the Set B run. Code checks added after that are reported separately.
- Pass: 0-1 silent errors in 100 and flag rate at most 15%.
- No prompt change is made based on Set B. If it fails, errors are analyzed and only code-only checks are considered; any later numbers on Set B are reported as optimistic (leakage).

## 2026-10-29: Set B labeling
- Tool: `scripts/label_set_b.py`. Blind labeling: shows only the disclosure text (the same `aciklama` the model gets), never Matriks values or model output. Saves after each case; `--redo NEWS_ID` relabels one case.
- Labels follow guidelines v1.2 and use the Set A gold format (`amount: null` means no amount in the text). Output: `data/gold_set_b.jsonl`; RAG questions: `data/rag_questions.jsonl`.
- The first 5 cases were a calibration round labeled with Claude's guidance (3 entry errors found and fixed with `--redo`). The remaining 95 are labeled independently.
- Tool hardened after calibration: `save?` accepts only Enter or r; a RAG question already used for another case is rejected.
- Input limit found: the model sees only `aciklama`, not `form_json`. When the amount is only in the KAP form (e.g. 6108271), gold is `null` and Matriks may still have an amount. Next step candidate: give `form_json` to the model too.
- Optional: a second annotator labels 20 cases independently to measure inter-annotator agreement.
**Labeling completed (29 Oct 2026).**
- 100/100 cases labeled blind (first 5 as calibration round with Claude, remaining 95 independently; ambiguous cases marked `discussed` in `note`).
- Gold summary: 19 cases with no amount in text (`amount: null`), 10 cases `needs_review: true`.
- RAG questions: 66 (7 negative, `answerable: false`), across 39+ companies.
- Rule change during labeling: max 1 question per company relaxed to max 2 when the disclosure is a clearly different deal with a distinguishing detail (tests "right disclosure of the same company"). YEOTK and LINK have 3 questions each; kept because each covers a different deal.
- Data quality finding: some disclosure texts have split Turkish characters from PDF extraction (e.g. `sayg ı yla`); RAG preprocessing should normalize these.

### RAG question set guidelines
- The answer is in this disclosure's text only.
- The question points to one disclosure: company + a distinguishing detail (country, counterparty, product).
- Paraphrase like an analyst would; do not copy project codes or exact phrases. Use the common company name.
- Short, checkable answer (a name, amount, date, duration).
- Mix angles: counterparty, currency income, related party, revision, duration, delivery date. Skip the case if no good question comes in about 30 seconds.
- Multi-disclosure questions (e.g. largest foreign deal this year) are collected separately; their answers will come from SQL over extracted fields.

### Demo scenario (draft)
1. Alert: ntfy message for a real recent disclosure.
2. Follow-up question: has the company won similar deals abroad before? Answer with KAP links (RAG).
3. Big picture: largest foreign deals this year, from SQL over extracted fields.
4. Red flag: a related-party deal is flagged.
5. Honesty: an unclear text gets `needs_review`.
- Evaluation numbers go on one slide, as the answer to "why trust this?"
- Every question type shown in the demo must also be in the test set.
- Later: stock price reaction after disclosures (event study), needs price data and a license check.

## 2026-10-29: Blind check of the first 20 Set B labels
- Script: `scripts/check_first20.py` (money regex vs gold label; Matriks values not shown; output kept outside the repo).
- Done before any model run on Set B, so corrections are allowed.
- Corrections (3 cases, all `rule`/`note`; no `amount` or `currency` changed):
  - 5755329: R1 -> R2 (single currency, "+ KDV"). Entry error.
  - 6064088: R1 -> R2, note fixed (VAT-inclusive; TL in parentheses is a conversion). Rule clarification.
  - 5499831: note completed only (was cut off).
- RAG question fix: 6064088 counterparty name typo.
- Guidelines v1.3: R2 scope and "one rule per case" clarified. Gap: guidelines mention `amount_try_stated` and `vat_included`, but the gold schema does not have these fields.
- Gold/RAG files are gitignored; dated backups in ~/kap-backups/.
- To do: check all 100 labels for consistency with v1.3 (VAT mentioned but rule is not R2).

## 2026-10-29: R2 consistency check across all 100 Set B labels
- Script: `scripts/check_vat_rule.py` (flags VAT in text with rule != R2, and R2 with no VAT in text; output kept outside the repo).
- Remaining flags are deliberate: R1 (X TL (Y USD, rate) pattern), R3, R5 cases where the deciding rule is not VAT (guidelines v1.3).
- Corrections:
  - 6071306: R1 -> R2, note set to VAT-inclusive (same pattern as 6064088). Rule clarification.
  - 5705618: note standardized to the X TL (Y USD, rate) pattern. During the redo an entry error appeared (amount 100x, needs_review false); caught by the re-check and fixed.
- Total corrections before the Set B run: 5 cases (1 entry error, 2 rule clarifications, 2 note fixes), plus 1 RAG question typo. No amount changed in the final gold.
- Lesson: after every `--redo`, re-print the edited rows to verify.

## 2026-10-29: Decision on the `currency_unclear` code check (before the Set B run)
- Context: the "X TL (Y USD, rate)" pattern was noticed while labeling Set B texts (model outputs on Set B not seen). Adding the check now would be designed with test-set inputs in view (mild leakage).
- Decision: run the model on Set B once and report two numbers from the same run:
  1. Frozen system (v3 prompt + code checks frozen before this note). The pass/fail decision rule applies to this number only.
  2. Frozen system + `currency_unclear` check. Reported as a supplementary result, labeled "designed after seeing Set B texts, before seeing model outputs".
- Check definition (fixed now; not to be changed after seeing Set B results):
  - Fires when the text has a TL amount (TL, TRY, ₺ or the broken `?`) immediately followed by a parenthesis that contains a foreign-currency amount (USD, $, EUR, €, GBP, £), and the parenthesis does not contain an explicit equivalence word (`karşılığı`, `karşılık gelen`, `eşdeğer`).
  - A rate mention alone (`kur`, `kuru`, `güncel kur`, `TCMB`) does not resolve the ambiguity.
  - Action: set `needs_review=true` and add flag `currency_unclear`. The extracted amount and currency are not changed.
- Development and testing of the check: Set A and non-Set B archive only.
- The check code is committed before the Set B run, even though its result is reported separately.

**Implementation (30 Oct 2026):** `scripts/currency_check.py` (`find_unclear`, `currency_unclear`; 14-case self-test). Applied post-hoc in scoring, not inside `llm_extract.py`, so one Set B run yields both numbers.

**Archive check (Set B excluded):** `scripts/check_currency_unclear.py` → 1173 checked, 17 flagged (1.4%). All 17 inspected manually: each is a TL amount followed by a foreign-currency amount in parentheses with no equivalence word (several with only an exchange rate, e.g. `Kur: 41,30`). 0 false positives. Recall not measured (missed patterns not searched).

### Set B scoring rules (fixed 30 Oct 2026, before the Set B run)
- Script: `scripts/score_silent.py`. Same `amount_ok` / `norm_cur` as `score_adjudicated.py`.
- Flagged = `needs_review_reasons` non-empty or run error (second number: also `currency_unclear`). Run errors are visible failures and count toward the flag rate.
- Silent error = not flagged and (amount, currency) differs from gold. Types: fabricated (gold null, model amount), missed (gold amount, model null), wrong_amount, wrong_currency. Both null = correct.
- Gold `needs_review: true` rows are **included** (changed from Set A, where they were excluded): on an ambiguous case the expected behaviour is to flag, so an unflagged different answer is a silent error. Set A is re-scored with the same rule for comparison.
- Report a one-sided 95% upper bound for the silent error rate (0/100 → ~3%).
- Decision unchanged: PASS if silent errors <= 1 and flag rate <= 15%.
- Set A re-scored with these rules (`eval_v3final_test_amount.jsonl`, 12 gold rows + 88 Matriks): frozen 0/100 silent (95% upper bound 3.0%), 10/100 flagged; +currency_unclear 0/100 silent, 11/100 flagged. All 3 gold needs_review rows were flagged, so the stricter rule does not change Set A.
- Run fix (30 Oct 2026): `IDS_SQL` in `eval_vs_matriks.py` used an inner join with `new_business`, so the 20 unmatched Set B ids were dropped (80/100 loaded). Changed to LEFT JOIN; selection only, extraction unchanged. The first attempt was stopped at the start and its partial output deleted before any result was inspected.
### Set B result (30 Oct 2026, commit 44426af, v3, gemma4:e4b, thinking default on)
- 100/100 run, 0 run errors.
- Frozen system: **4/100 silent errors** (fabricated=1, wrong_amount=3), 95% upper bound 8.9%; flagged 8/100. **Decision: FAIL** (limit <= 1 silent).
- + currency_unclear (designed after seeing Set B texts, before model outputs): 3/100 silent (fabricated=1, wrong_amount=2), upper bound 7.6%; flagged 9/100. Still FAIL.
- Gold needs_review rows: 10; flagged 6 (frozen) / 7 (+currency_unclear).
- Interpretation: Set A's 0/100 was optimistic (v3 was developed on Set A). Per the decision rule, no prompt changes; only code checks may be added, and any later Set B number is reported as optimistic (leaked).
- Silent error ids: 5491869 (fabricated), 5628896, 5763995, 5820056 (wrong_amount). 5628896 is caught by currency_unclear.

### Set B error analysis (30 Oct 2026, one case at a time on the KAP page)
- 5491869 (fabricated): model took a budgeted single-year revenue (EUR, for 2027) of a 2025–2032 project as the contract amount; no total value in text. Gold null is correct. Candidate code check: projection/revenue wording near the chosen amount → `amount_is_projection` flag.
- 5628896 (wrong_amount): TL (USD) currency ambiguity; caught by currency_unclear.
- 5763995 (wrong_amount): text gives an additional order and the cumulative total; gold takes the total (R5), model took the increment unflagged. Guideline gap: is an additional order R5? (open for guideline v1.4, gold unchanged). Candidate code check: cumulative wording (`ek olarak`, `ilave`, `toplamda`) + multiple amounts → `cumulative_total` flag.
- 5820056: **gold typo** (a digit dropped when typing the amount); model is correct. Found after seeing model output, so the decision number keeps the frozen gold. Corrected copy: `data/gold_set_b_corrected.jsonl` (backup in `~/kap-backups`).
- Gold-corrected numbers (post-hoc, not the decision): frozen 3/100 silent, + currency_unclear 2/100. Still FAIL; the decision does not depend on the typo.
- Pattern: in all model errors the text has more than one plausible number and the model picks one without flagging.
- Lesson for future labeling: check automatically that each gold amount appears in the text, before any model run.
### Post-hoc checks: amount_is_projection, cumulative_total (rule fixed 30 Oct 2026, before measuring)
- Designed after the Set B error analysis (5491869, 5763995). Code only; prompt unchanged; the amount is never changed, only flagged.
- Adopted if, on Set A (development set), all checks together keep 0 silent errors and flag rate <= 15%.
- Any Set B number using these checks is reported as optimistic (leaked), never as the decision.
- Result (30 Oct 2026): Set A 0/100 silent but flag rate 16/100 (5 extra flags from the new checks) → **not adopted** (limit 15%). Set B (optimistic): 1/100 silent (only the gold typo), 15/100 flagged. Next: find which check over-flags on Set A and narrow it (Set A is the development set).
- Narrowing on Set A (development set), 30 Oct 2026:
  - `amount_is_projection`: dropped `yıllık`/`annual` ('3 yıllık sözleşme' means 3-year, not annual). Removed 2 unneeded flags.
  - `cumulative_total`: compare only amounts in the chosen currency (TL conversions of a USD amount were treated as larger totals). Removed 3 unneeded flags.
- Result after narrowing: Set A 0/100 silent, 11/100 flagged (new checks add 0 flags) → **adopted**. Set B (optimistic, leaked): 1/100 silent (only the gold typo 5820056), 12/100 flagged.
- Caveat: the new checks never fire on Set A, so Set A only shows they do not over-flag. Evidence that they catch errors comes only from Set B (leaked). A fresh held-out set (Set C) is needed for an honest number.