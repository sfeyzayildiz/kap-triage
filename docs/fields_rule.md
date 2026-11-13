# Duration, counterparty origin, related party: measured (rule, written before labeling and the run)

Date: 2026-11-13. Known issue A5: ordering v2 (adopted) puts long contracts first, and the importance score uses a foreign counterparty and a related party, but only amount and currency were ever measured. A second annotator for the gold amounts (plan item c) was cancelled: one labeler stays a stated limit.

## What is measured (only what the code uses)
- **long:** `importance.duration_years(result['duration']) >= 2` → yes / no.
- **foreign:** `result['counterparty_origin'] == 'foreign'` → yes / no.
- **related:** `result['related_party'] is True` → yes / no.

## Data and order
- 50 disclosures from Set C, seed 20261113 (`scripts/fields_eval.py --sample`). Set C's error analysis never looked at these fields.
- **Feyza labels first** (`--label`, one disclosure at a time, text from the DB in her terminal), without seeing any model output. Then **one run** of the production extraction (v3 prompt + code checks, `pipeline.analyze`, no judge layer: it only concerns the amount) on the 50 (`--run`, about 13 min, Ollama on, not 23:40-23:50). Then `--score` once.
- Guideline v1 (fixed now):
  - long = yes if the text states a contract, service, delivery or project period of 2 years or more (e.g. "3 yıl", "36 ay", or start and end dates 2+ years apart, or a delivery date 2+ years after the disclosure date). A phrase like "yıl sonuna kadar" or no period → no.
  - foreign = yes if the counterparty is stated as abroad or as a foreign company / government (a Turkish company's foreign subsidiary as counterparty also counts as foreign). Unstated or domestic → no.
  - related = yes if the text says the counterparty is a related party, group company, subsidiary or parent ("ilişkili taraf", "grup şirketi", "bağlı ortaklık"). Otherwise no.

## Bars (per field, out of 50)
- Decision-relevant errors (model yes / gold no, or model no / gold yes; a run error counts as "no") **≤ 3/50** → `KEEP` the field in the score (and long in ordering v2).
- **> 3/50** → `OFF`: the field's points leave the score; if long is OFF, ordering v2 drops its long-contract step and orders by amount only (look-first group unchanged).
- Reported alongside: false yes / false no per field, number of gold "yes" cases, run errors, 95% upper bound.

## Decision (fixed now)
Per field as above, printed as `long=KEEP|OFF foreign=KEEP|OFF related=KEEP|OFF`. Applied to the code after the score; nothing else changes. Gold labels are not edited after seeing model answers; typos found later are reported separately as post-hoc.

## Limits
One labeler. 50 items: 0 errors still means an upper bound of about 6%. Foreign and related are rare, so their "yes" counts are small and the bar mostly tests that the model does not invent them.
