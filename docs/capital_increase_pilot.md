# Capital-increase pilot: design (nothing pulled, coded or measured)

Date: 2026-11-16. Design only. No API call was made, no data was read, no prompt or code was written. The measurement rule is `docs/capital_increase_rule.md`, the labeling guideline is `docs/capital_increase_guidelines.md`.

## Why this pilot
`docs/extending.md` claims the method carries over to other disclosure types and that a type costs about a week. That claim has never been tested. The pilot tests it on one type, "sermaye artırımı", at small scale: about 30 blind-labeled disclosures, rule first, one run. The talk gets one honest line either way ("second type in N days, this is what transferred and this is what did not").

It also meets the instructor's question "could it be solved without an LLM?" head on. Unlike "Yeni İş İlişkisi" (free text), a capital-increase disclosure is mostly a structured KAP form. A code-only form reader is therefore a serious competitor here, and the rule measures it next to the LLM instead of assuming the answer.

## 1. Where the data is in Matriks

### What the repo has
`scripts/collector.py` knows two sources, both for "Yeni İş İlişkisi" only:
- `GET v1/new-business-api` (`start`, `end`) → table `new_business`.
- `GET v2/news/search` with `query='source:KAP tag:NewBusiness after:… before:…'`, then `GET v2/news/search/page` (`qid`, `page`, `pageSize`) → table `disclosures`.

There is no capital-increase endpoint, tag or table anywhere in the repo. The only mentions are the out-of-scope word list of the chat agent (`agent.SCOPE_PHRASES`) and the "possible split / bonus issue" warning of the price module.

### What the public Matriks docs say
Read on 2026-11-16 at `analistdocs.matriksdata.com` (documentation pages only; not verified by a call; field meanings are the docs' own short labels).

| Need | Source | Notes |
|---|---|---|
| Disclosure text | `GET v2/news/search`, `query='source:KAP tag:CapitalIncrease after:… before:…'` | Same service and paging as today. The docs list the tag keys: `NewBusiness`, `Circuit`, `Dividends`, `StockTrading`, `ShareBuyBack`, `FinancialReports`, `Earnings`, `CapitalIncrease`, `TaxTables`, `BalanceSheet`, `FUND`, `CryptoCurrency`. `count` max 2000. |
| Structured record | `GET v1/capital-increase` (`symbols` max 20 or omitted for all, `start`, `end`, `year`, `type=CPI` for capital increases only, `DIV` for dividends only) | Fields below. Zero-valued fields are left out of the response. Without `start`/`end` it returns everything: always send both and `type=CPI`. |
| Realized splits | `GET v1/dividends` ("Gerçekleşen Bölünmeler": `symbol`, `date`, `bonus_issue`, `rights_issue`, `capital_reduction`, `dividend`, `rate`) | Not needed for the pilot. |

`v1/capital-increase` fields with `type=CPI`:

| Field | Docs label | Our column |
|---|---|---|
| `s` | Sembol | `sym` |
| `c` | İlgili Gündeki Sermaye | `capital` |
| `sD`, `eD` | Bedelli/Bedelsiz Sermaye Artırımı Başlangıç / Bitiş Tarihi | `start_date`, `end_date` |
| `rA` | Bedelli Sermaye Artırımı Tutarı (× 1000) | `rights_amount` |
| `rP` | Bedelli Sermaye Artırımı Oranı | `rights_rate` |
| `rO` | Diğer Bedelli Sermaye Artırımı Tutarı (× 1000) | `rights_other_amount` |
| `bIA`, `bIAP` | İç Kaynaklardan Bedelsiz Tutarı (× 1000) / Oranı | `bonus_internal_amount`, `bonus_internal_rate` |
| `bA`, `bP` | Bedelsiz Sermaye Artırımı Tutarı (× 1000) / Oranı | `bonus_amount`, `bonus_rate` |

### Three differences from `new-business-api` that shape the design
1. **No KAP link in the structured record.** `new_business.url` joins one record to one disclosure. A capital-increase record has only a symbol and the exercise dates, so the join is fuzzy (symbol + rate + date). The injection-defence layer 1 and the Matriks cross-check, which rely on the exact join, do not carry over as they are.
2. **One event, many disclosures.** A capital increase is announced, applied for, approved, dated, completed and registered in separate disclosures, most of them updates that repeat the earlier content. The Matriks record describes the event (apparently once its dates exist); the news feed delivers every step.
3. **Not documented:** whether rates are percentages, what `rO` covers (probably rights-restricted issues), whether `bA`/`bP` mean dividend-sourced bonus shares or the total, and when a record first appears (at the decision or only once dates are set). These go to the Matriks feedback document as questions; the pilot treats the record as report-only.

Unknown until the first pull (to be answered by a counts-only profile, never by reading texts in a Claude session): how many disclosures the tag returns per month, whether the tag also covers capital decreases and ceiling changes, whether Matriks' `content` keeps the KAP form tables, and how long the texts are.

## 2. Schema proposal

Principle unchanged: the reader extracts what is written, code derives and checks, code flags and never fixes.

### Extracted fields
| Field | Type | Meaning |
|---|---|---|
| `subject` | `self` / `other` / `none` | Whose capital: the disclosing company, another company (subsidiary, affiliate), or no capital increase at all |
| `rights` | bool | Bedelli with pre-emptive rights (rüçhan hakkı kullandırılarak) |
| `rights_rate_pct` | number / null | Rate as written, percent of current capital |
| `rights_amount_try` | number / null | Nominal amount |
| `rights_price_try` | number / null | Exercise price as written |
| `rights_price_nominal_try` | number / null | Nominal value the price refers to (1 TL, 1 Kr = 0.01), if written |
| `bonus` | bool | Bedelsiz |
| `bonus_internal_rate_pct`, `bonus_internal_amount_try` | number / null | From internal resources (iç kaynaklar) |
| `bonus_dividend_rate_pct`, `bonus_dividend_amount_try` | number / null | From profit (kâr payından bedelsiz) |
| `restricted` | bool | Rights restricted (rüçhan hakkı kısıtlanarak) |
| `restricted_kind` | `private_placement` / `public_offering` / null | Tahsisli or public sale |
| `restricted_amount_try` | number / null | Nominal amount |
| `restricted_to` | string / null | Named buyer of a tahsisli issue (proper name only) |
| `capital_before_try`, `capital_after_try` | number / null | Mevcut / ulaşılacak sermaye |
| `registered_ceiling_try` | number / null | Kayıtlı sermaye tavanı; extracted only so that code can check nothing else equals it |
| `stage` | enum | `decision`, `application`, `approval`, `exercise`, `completed`, `cancelled`, `other` |
| `milestone dates` | date / null each | Board decision, SPK application, SPK approval, rights start / end, bonus start, registration |
| `use_of_proceeds` | string / null | Shown with its source sentence; not scored in the pilot |
| `needs_review`, `review_reasons` | bool, list | Set by code checks and by reader disagreement |

Derived in code, shown as "hesaplandı", never scored as an extraction: total bonus rate (internal + dividend), cash raised (rights nominal × price ÷ price nominal), increase as a share of current capital when no rate is written, and the event key that groups the steps of one increase (symbol + component rates).

Gold labels cover a subset (see the guideline): `subject`, the three component flags, the rights rate and price, the two bonus rates, the restricted amount, `stage`.

### Storage (separate from the live system)
- New tables `capital_disclosures` (same columns as `disclosures`, plus `tables_json` and `text`) and `capital_matriks`, created from a new `scripts/capital_schema.sql`.
- **Never insert these rows into `disclosures`.** Every live part (morning list, search index, drift check, sealed forward test, corpus counts) assumes that table holds only "Yeni İş İlişkisi".
- `scripts/schema.sql` is not edited: the nightly collector executes it on every run.

## 3. Traps of this type

Each line names the "Yeni İş İlişkisi" error it resembles (Set A / Set B error analysis).

| # | Trap | Looks like |
|---|---|---|
| T1 | **Registered capital ceiling** (kayıtlı sermaye tavanı) read as the new capital or as the increase | One-year revenue estimate read as contract value: a large nearby number that is not the fact |
| T2 | **Old steps repeated in an update** read as a new increase; the same event counted five times in a week | Revision mistaken for a new order |
| T3 | **Total instead of components**: "sermaye 100'den 400'e" with 200 bedelli and 100 bedelsiz; one rate applied to the wrong component | Total vs. company share (R4), sums (R3) |
| T4 | **Share groups**: the form repeats the same rate per group (A, B, C). Amounts add up, rates do not | R3 reversed: summing what must not be summed |
| T5 | **Nominal vs. cash**: 100 M TL nominal at 5 TL per share raises 500 M TL. Matriks amounts are in thousands | TL / USD confusion: right digits, wrong unit |
| T6 | **Price per what?** Nominal value is not always 1 TL (1 Kr shares); "nominal değerden" with no number; price left to be set later | Unit price × volume: a number that must not be computed |
| T7 | **Tahsisli vs. rüçhanlı**: both are "bedelli", the effect on existing holders is the opposite | Group-internal deal shown as a normal order |
| T8 | **Whose capital?** The company reports its subsidiary's increase | Wrong subject / counterparty confusion |
| T9 | **Cancelled, rejected or withdrawn** increase shown as live | Cancellation shown as a new order |
| T10 | **Simultaneous decrease and increase** (eş anlı): net effect unclear | Mixed-currency deal: no single headline number |
| T11 | **Number format**: "% 1.900" is 1900 percent, "%33,33333"; rates above 100 are normal | "milyon / milyar" and separator errors |
| T12 | **Rate written as a ratio in words** ("her 1 paya 2 pay") or not written at all | Amount implied, not stated |
| T13 | **Planned vs. realized**: unused rights sold later or cancelled, so the completed amount differs from the decision | Additional order vs. cumulative total |
| T14 | **Bonus from profit** is also a dividend decision; two bonus sources in one form | Two facts in one disclosure |
| T15 | **Several dates in one text**; the wrong one taken as the exercise date | Delivery date vs. signing date |
| T16 | **Form and free text disagree** (a correction written only in the note) | Headline vs. body contradiction |
| T17 | **Long forms** cut silently at `num_ctx 8192` | 8 docs cut at 512 tokens in the index |
| T18 | **Text is external input**: an instruction or a planted number inside the note | Prompt injection (layered defence) |
| T19 | **`parse_form` drops table rows**: it keeps only two-cell rows, and the rights / bonus figures of the KAP form sit in multi-column tables. The "Açıklama" key may not exist in this form, so `aciklama` would be empty | New to this type; a code trap, found by reading `scripts/parse_form.py` |

### Candidate code checks
The final list is fixed on the dev records and frozen before the held-out run; none is added afterwards.
- `arith_mismatch`: before + components ≠ after, when all are written.
- `rate_mismatch`: written rate ≠ amount ÷ current capital.
- `ceiling_as_value`: an extracted amount equals the written ceiling.
- `rate_not_anchored`: an extracted rate or price is not in the text next to "%" / "TL" (same idea as injection layer 2; also gives the source sentence).
- `no_component`: subject is `self`, stage is not `other`, and no component was found.
- `simultaneous_decrease`: decrease wording present.
- `group_rates_differ`: share groups carry different rates.
- `long_text`: text longer than the context allows.
- `reader_disagree`: form reader and LLM give different primary keys (see the rule).

## 4. Pilot architecture

```
tag:CapitalIncrease news ─► data/raw_capital/*.json ─► capital_disclosures
v1/capital-increase (CPI) ─► data/raw_capital/*.json ─► capital_matriks        (report only)

capital_disclosures ─┬─► F: form reader (code, no LLM) ─┐
                     └─► L: LLM cap_v1 (gemma4:e4b)   ─┤
                                                       ├─► code checks ─► C: combined
                                                       │      (disagree → needs_review)
                                                       └─► source sentence per number
```
- The pull writes raw files only and never touches the DB; loading is a separate step with no network (same pattern as `price_collect.py`).
- Model settings as in the live system: `gemma4:e4b`, thinking on, temperature 0, `num_ctx 8192`.
- Two readers of different kinds (code and LLM) give the disagreement flag that Set D tested with two runs of the same model.
- Nothing is wired into the morning list, the agent, the panel or the nightly job by this pilot.

Importance for an analyst (not built, not measured here): cash raised against market value, dilution, rights restricted in favour of a related party, and for bonus issues the ex-date, which would explain the "possible split / bonus issue" days the price module can only flag today.

## 5. Decisions (options as proposed; the first option was the recommendation)

**Decided by Feyza on 2026-11-16:** D1 (c) moved to Saturday 21 Nov in the daytime, D2 (a), D3 (a), D4 (a) with a fallback start of 2026-05-01 if fewer than 38 symbols, D5 (a). Exact wording: Note 1 of `docs/capital_increase_rule.md`.

**D1. When to pull.** The nightly job skips its run on a day that already has a pull, and a skipped night means no sealed morning list for that day (forward test, 15-25 Nov).
- (a) Same session as the nightly collector: Feyza starts the pilot pull by hand right after the `KAP collector OK` alert (about 23:46). The script claims `after=('collector',)` as sectors do after prices, writes raw files only, refuses to start after 23:56 and never sends a request after 23:58. The sealed test is untouched. Cost: Feyza must be at the terminal at 23:46; if the window is missed, nothing is lost and the next night works.
- (b) On 26 Nov in the price-pull session (`after=('prices',)`). Zero risk to the sealed test, but labeling and the run fall on 26-27 Nov, next to the rehearsals.
- (c) Sunday 22 Nov in the daytime with the job paused. Loses one sealed day, most likely an empty one.
- (d) A weekday in the daytime with the job paused. Loses one sealed day with real items; a stated deviation in a pre-registered test.

**D2. How many labels.**
- (a) 8 dev + 30 held-out (38 texts).
- (b) 10 dev + 20 held-out (30 texts; 0/20 only bounds the rate below 13.9%).
- (c) 30 held-out, no dev (a parsing bug would spoil the only run).

**D3. Gold fields.**
- (a) Core: subject, three component flags, rights rate, rights price, two bonus rates, restricted amount, stage. About 1.5-2 minutes per text.
- (b) Extended: core plus capital before / after and the exercise start date. About 3 minutes per text; scores more of what is extracted.

**D4. Pull window.**
- (a) 2026-08-01 to the pull day. Volume per month is unknown; a month that reaches the 2000 search cap stops the script instead of being cut silently.
- (b) Full archive from 2024. More requests, no use for a 30-record pilot.

**D5. Matriks structured record.**
- (a) One extra request in the same session (`start=2024-09-01`, `end` = pull day, `type=CPI`), report-only: coverage against the labeled records and the price-bridge count.
- (b) Skip; text only.

## 6. Handoff (what the implementer writes, in order)
Nothing below exists yet. New files only; no edit to `collector.py`, `daily_collect.py`, `morning*.py`, `pipeline.py`, `importance.py`, `schema.sql` before 26 Nov.
1. `scripts/capital_collect.py`: `--plan` (no network), `--pull --yes` (raw files, manifest, `pull_guard.claim('capital')`, refuses 23:30-23:59, counts symbols in the raw files and extends the window to 2026-05-01 in the same session if fewer than 38), `--load` (no network), `--profile` (counts only: disclosures per month, symbols, updates, text length percentiles, share of texts with multi-column tables; form keys only if they occur in at least 5 disclosures, written to `/tmp`).
2. `scripts/capital_schema.sql`, a table-aware form parser, `scripts/sample_capital.py` (seed 20261116), `scripts/label_capital.py` (blind, dev first).
3. **Drafted on 16 Nov, before the pull (version 1 of 3 each):** form reader `scripts/capital_form.py` (`read_form`, `form_text`; tables in both orientations, share groups, TOPLAM line; self-tested on synthetic forms) and the prompt `prompts/extract_ci_v1.txt`. Still to write after the labels: the pydantic schema for the prompt's fields and `scripts/capital_extract.py` (its own LLM call; `llm_extract.py` is on the nightly path and stays untouched), code checks, `scripts/capital_score.py` (reuses `score_silent.upper_95`). Self-tests for each, added to `scripts/run_self_tests.py`.
4. Freeze commit, held-out run by Feyza, one scoring, result into `PROJECT_NOTES.md`, `docs/results.md`, `docs/metrics_faq.md`, `docs/extending.md`.
