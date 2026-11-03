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

## 2026-11-03: Postmortem, nightly run of 2 Nov failed (no network)
- `LastExitStatus` 256; no rows added (last disclosure still 2026-10-30). Log (error lines only, shown by Feyza): `NameResolutionError`, failed to resolve `ntfy.sh`. The Mac had no network at run time, most likely because launchd ran the job right after wake, before Wi-Fi reconnected.
- Second fault: `notify()` raised inside the `except` block, so no FAILED alert reached Feyza and the alert error hid the original one.
- Fix (`fix/daily-network-wait`): `wait_for_network()` resolves the API host up to 10 times, 60 s apart, before any request, so waiting never causes a second pull. `notify()` now catches request errors and logs only the error type. `--self-test` (2 checks) is run by Feyza, since Claude does not run this script.
- No data lost: the 3-day lookback picks up 2 Nov on the next successful run.

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
- 2026-10-31 test: Mac reaches <MATRIKS_API_HOST>:443 with and without VPN (VPN is not a factor). Server [server-ip] (TR, IPv4) times out on TCP 443 to <MATRIKS_API_HOST> ([api-ip]) but reaches www.kap.org.tr:443. Consistent with a network-level block on Matriks' side for the server IP. Collection stays on the Mac.

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
### Gold amount presence check (2026-10-30)
- `scripts/check_gold_amounts.py`: checks each gold amount appears in `aciklama`; stdout = counts + ids, details in `/tmp`. Exit 1 if any problem.
- Set B frozen gold: 1 problem (5820056, known typo). Corrected gold: 0. Set A adjudicated: 0 (R3/R4 counted as computed).
- Run before new labeling and after every label change.

### Known limitation: amount_checks currency pattern (2026-10-30)
- `MONEY_RE` in `scripts/amount_checks.py` does not match "ABD Doları" / "Amerikan Doları" (e.g. "553 milyon ABD Doları").
- In Set B, 10 of 81 gold amounts are written only in this form, so `amount_is_projection` and `cumulative_total` may silently skip about 1 in 8 amount-bearing disclosures.
- Not fixed in place: these checks were accepted on Set A and are frozen. A fix goes into a new version and must be measured on Set C.
- `check_gold_amounts.py` normalizes these words to USD before matching, so the presence check is not affected.
### RAG text normalization (2026-10-30)
- Profile (`scripts/text_artifacts.py`, 1273 rows): nbsp 438 rows, `?` next to digit (broken ₺) 24, split Turkish letters 12, multi-space 4. Texts are short (words median 52, p95 163, max 358), so one document per disclosure, no chunking.
- `scripts/normalize.py` (embedding input only; v3 extraction keeps raw `aciklama`): nbsp → space, `İ STANBUL` → `İSTANBUL`, `?` next to digit → ₺, collapse spaces.
- 7 heavy rows (>=5 split hits, every Turkish letter split off): spaces around Turkish letters are removed. Known limitation: real word boundaries next to a Turkish letter are lost (`adet ş arj` → `adetşarj`).
- Left as is: 3 rows with a single split letter in different directions (5476493, 5980983, 6290203) and 1 non-digit `?` (6425402).

## 2026-10-30: Scope decision
- Scope: only "Yeni İş İlişkisi" disclosures (agreed with the BTK instructor).
- Target user: brokerage equity analyst.
- Positioning: morning triage agent ("is this disclosure important, why, and is it reliable?").
- Reason: each new disclosure type needs its own extraction schema and labeled test set; depth gives measured reliability, RAG over the full history, revision/cancellation tracking and the daily triage agent.

## 2026-10-31: Revenue ratios already in `new_business`
- The importance score does not need a separate financials source for most disclosures: `new_business` already has `rt` (deal value / shifted revenue), `shf_ret`, `cum_rt`, `mar_val_rt` and `per` (definitions from `scripts/schema.sql`; `rt` verified below, `cum_rt` and `mar_val_rt` not verified).
- Coverage (counts only, 1273 disclosures, apitest data): 1067 have a `new_business` record; 904 of them have `rt > 0` (71% of all disclosures), 1047 have `mar_val_rt > 0` (82%). Disclosures without a record have no ratio.
- In `new_business` overall (1582 rows, 129 symbols): `rt > 0` 1296, `shf_ret > 0` 1312, `mar_val_rt > 0` 1562.
- Verified (counts only): `rt` equals TRY amount / `shf_ret` within 1% on 1242 of 1296 rows with `rt > 0`, within 5% on 1286; it is a ratio, not a percent. TRY amount = `amount` for TRY rows, `amount * tcmb_ex_rt` otherwise.
- Non-positive `rt` is mostly negative, not zero: `shf_ret < 0` on 267 rows, `rt < 0` on 265, `rt = 0` on 19. Why revenue is negative is not known (question for Matriks); the score must not read these as small deals.
- `cum_rt < rt` on 226 rows, which the definition does not explain on its face; not used until checked.
- No sign of record lag: `new_business.date` equals the disclosure date on all 1067 matched rows; match rate is 8/9 (last 3 days), 8/8 (4-7), 37/41 (8-30), 76/84 (31-90), 938/1131 (older). Same-day availability cannot be measured because re-fetches reset `fetched_at`.
- All 515 `new_business` rows without a disclosure are older than the first disclosure, so that archive simply starts earlier.

## 2026-10-31: Prod API probe (`scripts/prod_probe.py`, one request, run by Feyza; nightly job paused so it was the day's only pull)
- HTTP 200 with the current token at `https://<MATRIKS_API_HOST>/dumrul`.
- Last 30 days of `new_business` (ending yesterday): 49 rows on both sides, 49 URLs in common, none only on one side. No completeness gap in this window.
- `rt` differs by more than 1% on 47 of 49 rows. Prod: 45 positive, 2 negative, `shf_ret` negative on 2. Local apitest, same window: 44 positive, 0 negative, `shf_ret` negative on 0; its `rt` matches amount / `shf_ret` on all 44.
- Open: size and cause of the difference, and which side is correct. The probe printed no direction and the prod rows were not saved. Prod `shf_ret`, `amount` and `tcmb_ex_rt` were not compared. Different revenue values are one hypothesis, not a finding.
- Consequence: `rt` and `shf_ret` are not safe for the importance score until this is explained. The apitest coverage numbers above do not carry over to prod.
- Disclosure texts (`v2/news`) were not compared, so Sets A/B and the RAG docs are still apitest-only.
- Decision: a second counts-only probe (`feat/prod-api`, not run yet) measures the direction and cause of the difference. It runs when Feyza is back, 3-4 days away, as the only pull of a night with the launchd job paused. The job was paused only on 31 Oct and re-enabled after 23:50 that night; the 3-day lookback covers the skipped night.

## 2026-10-31: Retrieval evaluation setup
- Installed: `bge-m3`, `qwen3-embedding:0.6b` (Ollama), `sentence-transformers==6.2.0`, torch 2.15.0. MPS available. `turkish-e5-large` not downloaded yet (about 2.4 GB, estimated from 0.6B F32 parameters).
- `scripts/eval_retrieval.py`: follows `docs/rag_model_choice.md`. It stops if the question counts change (66/59). Ollama calls use `truncate=False`, so an over-long text fails instead of being cut silently. `--timing N` measures speed only, with no scoring.
- Prefixes from the model cards, none on documents: `bge-m3` none; `qwen3` `Instruct: <card example task>\nQuery:<q>` (card advises English instructions); `turkish-e5-large` `Instruct: <card Turkish-search task>\nQuery: <q>`.
- Speed on the first 20 docs: `bge-m3` 0.11 s/doc (about 2.5 min projected), `qwen3` 0.31 s/doc (about 7 min projected).

### Result (2026-10-31, commit 5ee4cd0, rule in `docs/rag_model_choice.md`)
| model | recall@5 | recall@1 | wrong same-company | truncated docs | negatives top-1 min/median/max |
|---|---|---|---|---|---|
| `bge-m3` | 53/59 = 0.898 | 40/59 = 0.678 | 19 | 0 | 0.560 / 0.678 / 0.785 |
| `ytu-ce-cosmos/turkish-e5-large` | 51/59 = 0.864 | 43/59 = 0.729 | 16 | 8 | 0.545 / 0.647 / 0.742 |
| `qwen3-embedding:0.6b` | 50/59 = 0.847 | 39/59 = 0.661 | 19 | 0 | 0.644 / 0.694 / 0.821 |

**Decision: `ytu-ce-cosmos/turkish-e5-large`.** `bge-m3` has the highest recall@5, but the gap is 2 questions (e5) and 3 questions (qwen3), so rule 2 makes it a tie and the higher recall@1 decides. Recall@5 is 0.864, above 0.85, so the BM25 hybrid step is not triggered.

Findings:
- The gaps are small (2-4 questions of 59), and the winner comes from the tie rule, not a clear lead. The same 66 questions were used for selection, so 0.864 is optimistic; a held-out question set is needed.
- Nearly all recall@1 misses are the right company but the wrong disclosure: 16 of 16 for e5, 19 of 19 for `bge-m3`, 19 of 20 for qwen3. Finding the company is not the weak point; separating that company's disclosures is.
- e5 reads at most 512 tokens, so 8 of 1273 docs are cut. Their tails are not searchable. Chunking was not tested.
- The texts are apitest data; prod texts have not been compared.

## 2026-11-01: Combined pipeline
- `scripts/pipeline.py`: prompt v3 and `postprocess_v3`, then `currency_unclear`, `amount_is_projection`, `cumulative_total`. These are the same functions and inputs as level 2 of `score_silent.py`. `amount_checks.py` and the prompt are unchanged.
- Code only adds flags. It never changes the amount or currency.
- Any failure stays in the output as `run_error` with `needs_review`, so a disclosure cannot disappear from the morning list.
- Not an evaluation: the combined system still has no honest number. Set B with these checks is leaked (1/100 silent, 12/100 flagged); Set C is needed.

## 2026-11-01: Set C plan
- Rule, frozen system and run commands: `docs/set_c_plan.md`, committed before sampling. PASS: at most 1 silent error in 100 and a flag rate of at most 15% at level 2.
- `scripts/sample_set_c.py`, seed 20261101: excludes all earlier sets by news_id (366 ids) and any disclosure with the same normalized text (6 dropped). Pool: 747 matched, 154 unmatched. Set C: 100 rows, 80 matched + 20 unmatched, 12 updates, 59 symbols.
- Labeling: `python scripts/label_set_b.py --set-c`, guidelines v1.3, gold in `data/gold_set_c.jsonl`, RAG questions in `data/rag_questions_c.jsonl`. Stop with `q`, it resumes.
- The open guideline question (is an additional order R5?) stays open: guidelines v1.3 are used unchanged and no rule is changed while labeling.
- No model runs on Set C until all 100 are labeled.
- Labeling guide for Feyza: `docs/set_c_labeling_guide.xlsx` (fields, R1-R6, watch-outs, day tracker, RAG question type targets). No real data; examples are invented. Type targets are a suggestion. Formulas not recalculated here (no LibreOffice).

## 2026-11-01: Matriks data access
- Email thread (Oct 26-28): Feyza named company sector information and fundamental analysis data as possible supporting services; Matriks replied that the services can be used. Daily prices were not named, so they are not covered explicitly. Keep the thread for the license line in the presentation.
- Fundamental analysis data, if available, is a second revenue source and could help with the `rt` / `shf_ret` difference.
- The documentation is public at `analistdocs.matriksdata.com` (read 2026-11-01; no API call). Base URL in the docs is apitest. What it offers:
  - Daily prices: `GET v1/tick/bar.gz`, `symbol`, `period=1day`, `start`, `end`; fields date, time, open, high, low, close, volume, totalQuantity, weightedAverage. One symbol per request; `count` max 1000.
  - Income statement: `GET v1/fundamentals/INC`, `symbols`, `periods` (YYYYMM, months 03/06/09/12), optional `currency`, `unadjusted`. Revenue item code not shown; whether values are quarterly or year-to-date is not stated.
  - Item keys: `GET v1/fundamental-key` and its `/info` path; revenue key not shown on the page.
  - Sector: `GET v4/meta/symbols.gz` (`seI`, `seC`) and `v4/meta/sectors.gz`.
  - `v1/profit-table` is profit, not revenue. `v1/company-cards` has no sector, market cap or revenue field.
- `new-business-api` field definitions now documented: `rt` = deal value in TRY at that day's central bank rate / shifted revenue of the related balance sheet; `shfRet` = that shifted revenue; `cumRt` = all deals of the period in TRY / shifted revenue; `marValRt` = deal amount / market value; `tcmbExRt` = previous day's closing central bank rate for `cur`; `per` = related balance sheet period. Our `rt` check agrees.
- Not documented: what "shifted" means, and whether it can be negative. The docs do not explain negative `shfRet` or the prod difference, and they say nothing about how a pull is counted. `v1/historic-ratio` also returns `shiftedReturn` ("Kaydırılmış Hasılat") and `shiftedNetProceeds`.
- Pattern in local data (counts only): negative `shf_ret` appears on 267 rows, all in periods ending 03/06/09, none in any period ending 12. 2024 and 2025 quarters have 27-64 negatives each; 202603 and 202606 have 3 each. 45 of 129 symbols are affected; 37 of them also have positive rows.
- Hypothesis, not confirmed: shifted revenue is a trailing 12-month figure built by subtraction (previous full year + current year-to-date - previous year-to-date). A December period needs no subtraction, which would explain why it is never negative. Testing it needs `INC` figures, which means one pull.
- `cum_rt < rt` is mostly explained: 222 of the 226 rows have negative `shf_ret`.
- Within one symbol and period, `shf_ret` is the same on 297 of 318 multi-row groups, so it behaves like a balance-sheet value.
- Fallback for the importance score: rows with `shf_ret <= 0` can use the same company's latest earlier December value. It exists for 206 of the 270 such rows. Coverage of matched disclosures rises from 920 to 1044 of 1067 (apitest values; not valid until the prod difference is explained).
- Claude does not guess endpoints beyond these pages and does not call the API. The rule of one pull per day still applies; daily bars need one request per symbol, so ask Matriks before a price pull.
- Her Oct 28 question about refreshing the archive from prod once: the reply is not in what was shared.
- No email has been sent about prices or field definitions yet.
- Project scope stays "Yeni İş İlişkisi" unless Feyza decides otherwise; prices are supporting data for the stock-move module.
- `rt` uses the Matriks amount, which was wrong in some Set A cases. The score should divide our extracted amount by `shf_ret` instead of trusting `rt`.
- Daily prices: still unknown, no price endpoint in the repo. Feyza asks Matriks; do not guess endpoints.

## 2026-11-02: Daily price bars approved
- Feyza asked Matriks (Matriks yetkilisi) whether she may use `v1/tick/bar.gz` daily bars and pull about 130 symbols at most 1 request/sec in one go under the one-pull-per-day rule. Reply on 2026-11-02: "Kullanabilirsiniz." Keep the thread for the license line.
- The real count is 148 disclosure symbols plus `XU100` (149 requests), not 130 (129 is the `new_business` count). Same pattern (one session, 1 request/sec), so treated as covered; stated here so it is not hidden.
- Docs (`/tarihsel-tick-veriler/bar`, read 2026-11-02): params `symbol`, `period=1day`, `start`, `end` (YYYY-MM-DD); response is a JSON list with date, time (ms epoch), open, high, low, close, volume, totalQuantity, weightedAverage. `count` max 1000. Only `divide=false` exists, so **prices are unadjusted**: splits and bonus issues look like crashes. Index support is not documented; `XU100` is tried as one extra symbol.
- `scripts/price_collect.py`: `--plan` (no network), `--pull --yes` (one request per symbol, raw JSON to `data/raw_bars/`, manifest with status per symbol, resumes without re-pulling ok symbols), `--load` (raw files to table `daily_bars`, no network). Range: first disclosure minus 60 days (2024-09-01) to yesterday, about 540 trading days, under the 1000 cap. Refuses 23:30-23:59. Stdout: counts and dates only. 9 self-test checks.
- Pull is Feyza's to run, in the daytime; the nightly new-business job stays on.

### Pull result (2026-11-02, 11:46-11:52, run by Feyza, the day's only price pull)
- 149 requests: 148 ok, 1 `http_503` after 5 tries (EFORC). EFORC is not re-pulled today; the manifest lets a later pull fetch only it.
- `XU100` works: 533 bars, so index-relative returns are possible.
- `daily_bars`: 148 symbols, 73,606 rows, 2024-09-02 to 2026-10-30. No null fields, no bar with close outside high/low. 17 symbols have fewer than 500 bars (later listings; minimum 43).
- 1263 of 1275 disclosures fall inside their symbol's bar history.
- 5 day-to-day moves above 30% (5 symbols). BIST daily price limits are about ±10% for most shares, so these are very likely splits or bonus issues in unadjusted prices; the move module must exclude or flag them, not explain them.
- Speed: about 1.3 s per request (3.2 minutes total).

### Decision: no daily price update (Feyza, 2026-11-02)
- Prices are not pulled every day, so there is never a second pull on the same day. One refresh pull is planned around 12 Nov, before the demo on 14 Nov (it also retries EFORC). Until then the morning list shows "henüz tepki günü yok" for disclosures after 2026-10-30.

## 2026-11-02: Importance score v1
- Rules in `docs/importance_score.md`, written before any measurement: size against the company's own earlier deals (median TRY value, at least 3 deals; absolute TRY bands otherwise), foreign currency +1, foreign counterparty +1, duration of at least 2 years +1, related party -2. Levels: >= 4 high, 2-3 medium, else low. Revisions score only the increase.
- `scripts/importance.py`: reads a pipeline file, writes `data/triage_<label>.jsonl`, prints counts only. 20 self-test checks.
- Revenue and market-value ratios are off (`USE_REVENUE=False`) until the prod/apitest `rt` difference is explained.
- `needs_review` does not change the score; it is shown next to it, and flagged items are always listed.
- Available context (counts only): 86 of 125 companies have at least 3 earlier deals by 2026-10-01; central bank rates exist for USD (459 days) and EUR (224), rare currencies on a few days only, so those fall back to `no_rate`.
- First real run: pipeline output for 2026-10-28 (2 rows): 1 medium, 1 low, 0 flagged.
- Weights are judgment, not fitted. No measured accuracy for the score.

## 2026-11-02: Price moves module
- `scripts/price_moves.py`: abnormal return = stock return - XU100 return (close to close, market-adjusted). Reaction day t0 = first trading day on or after the disclosure date, the next one if published at or after 18:00. Sigma from the 60 trading days before (at least 30), split days left out. A day with |stock return| > 22% is a possible split or bonus issue (BIST limit about 10%): flagged, never explained. 10 self-test checks.
- `--reactions` (all disclosures, `data/reactions.jsonl`): ok 1239, short_history 21, no_symbol_bars 12, no_bar 3; possible_split 3.
- `--scan DATE` (`data/moves_<date>.jsonl`): |z| >= 3, plus the symbol's disclosures from 4 days before to the day's close. 2026-10-30: 147 symbols, 3 abnormal moves, 2 with a disclosure.
- Descriptive count over 493 trading days (2024-11-01 to 2026-10-30): 1378 abnormal moves, 92 (6.7%) with a new-business disclosure in the 4 days before, 11 split days skipped. Most moves have another cause, so module B must say "no new-business disclosure, cause may be elsewhere" in most cases. Not used to tune anything.
- 1378 of about 72,000 stock-days is about 1.9%, far above the 0.27% a normal distribution gives for |z| >= 3: daily returns have fat tails, so z >= 3 is a screening threshold, not a significance test.
- Mean reactions were not computed. Any test of whether disclosures (or the importance score) move prices needs its own decision rule, committed before measuring.

## 2026-11-02: Morning list (one command)
- `scripts/morning.py --date D`: pipeline (v3 + code checks) -> importance score -> price reaction -> company history (last 12 months: count, updates/corrections, last date) -> `data/morning_D.md` (Turkish, KAP link per item) and `data/morning_D.jsonl`. `--from-pipeline FILE` skips the LLM. Stdout: counts only. 7 self-test checks.
- Order: flagged or high first, then by score. Flagged items always show "KONTROL ET" with the reasons in Turkish. The footer says the score is a rule-based ranking, not a prediction.
- First end-to-end run with the LLM: 2026-10-30, 2 disclosures, 0 flagged, 0 look-first, about 1 minute.
- Prices end on 2026-10-30, so newer disclosures show "henüz tepki günü yok" until prices are updated. A daily price update would be a second daily pull; not done without asking.
- History is SQL only for now; similar past disclosures by embedding search (RAG) come next.

## 2026-11-02: Search index in the morning list
- `scripts/rag_index.py`: one `turkish-e5-large` vector per disclosure (same doc text as `build_docs.py`, no prefix on documents, card prefix on queries) in `data/rag_index.npz`, with news_id, KAP link, symbol, date and text sha1. Updates are incremental: only new or changed texts are embedded. 8 self-test checks.
- Full build: 1275 docs in 33 s on MPS; a rerun embedded 0.
- `similar_earlier`: the same company's earlier disclosures closest to this one (document-to-document cosine). The morning list shows the top 2 with date, similarity and KAP link, to help find the original of a revision or a repeated order.
- Not measured: the retrieval evaluation (recall@5 0.864) was question-to-document; document-to-document similarity has no measured quality.
- `morning.py --from-pipeline` now stops if the file's dates differ from `--date`.

## 2026-11-02: Triage agent (LangGraph)
- `scripts/agent.py`, `langgraph==1.0.2`. Graph: route (LLM, `gemma4:e4b`, structured output: intent, symbol, date, topic) -> validate (code) -> one tool (code) -> END.
- Tools: `morning` (day's ranked list; reuses `data/morning_D.jsonl` only if that day's disclosure count is unchanged), `company` (last 12 months of a symbol, with Matriks amounts labeled as such), `why_moved` (abnormal return vs XU100 on the day, z, split check, disclosures in the 4 days before, or "no new-business disclosure, cause may be elsewhere"), `search` (embedding search, top 5, with the measured recall stated), `unknown` (help).
- Design: the LLM only reads the question. Numbers and links come from code, so the answer cannot contain invented figures. Code checks the route: a ticker must exist in our data; if the model took it from a company name, the answer says so; dates after the last price day fall back with a note.
- LangSmith tracing is forced off in code; the agent makes no network calls besides local Ollama.
- `morning.py` split into `extract_day`, `enrich`, `save`, `load_saved` for reuse.
- Smoke test (routes only, 9 questions incl. repeats): all went to the expected tool; one unrelated question went to help. Not an evaluation: no fixed question set, no decision rule. A router test set would need questions written by Feyza.
- 13 self-test checks. Reason: a run with the 10-28 pipeline file and `--date 2026-10-30` overwrote the 10-30 report; both reports were rebuilt from the right data.