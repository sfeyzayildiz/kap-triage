# Sample data (made up)

The real data comes from Matriks under a licence and cannot be shared. This folder lets you run the panel on your own computer without it.

**Everything here is invented:** 12 companies, 57 "Yeni İş İlişkisi" disclosures (Sep to Nov 2026), vendor-style records, sectors, exchange rates and daily prices. Tickers contain a digit (`SVN1`, `BLS2`), which no BIST ticker has. KAP links point to `kap.org.tr/tr/Bildirim/ornek-...`, which is not a real disclosure.

## Run it
```
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python scripts/panel.py --serve --sample
```
Open `http://127.0.0.1:8765/genel` (overview). The first start builds `sample/data/` (a few seconds). On Windows, use `.venv\Scripts\python`.

## What works without a model
| page | works on sample data |
|---|---|
| Genel bakış (overview: last list, 30-day chart, look-first items, review decisions, reliability) | yes |
| Sabah listeleri (morning lists, one per day, by desk) | yes |
| Kontrol et (confirm / reject a flagged item) and Kontrol geçmişi (every decision, by flag type) | yes, written to `sample/data/review_log.jsonl` |
| Haftalık temalar (weekly themes) | yes |
| Güvenilirlik (measured results) | yes |
| Rehberli sorgu: day list, company history, "why did it move?" | yes |
| Sohbet (chat), topic search, disclosure card | needs Ollama with `gemma4:e4b` and the embedding model |

## How it is built
`scripts/sample_data.py` writes the texts and records, then runs the **real nightly chain** on them: extraction checks, vendor cross-check, two readings, source-sentence check, importance score, price reaction, company history. Only the language model is replaced by pre-written answers (what the model reads from each text), so no model is needed. Similar earlier disclosures stay empty, because they need the embedding model.

Some disclosures are built to show one behaviour each:

| day | company | what the system does |
|---|---|---|
| 2 Nov | SVN1 | large USD contract, 3 years, 18% of yearly revenue: high importance; the price jumps that day |
| 3 Nov | BLS1 | "96.000.000 TL (2.200.000 EUR)": currency unclear, **kontrol et** |
| 4 Nov | SGL1 | a planted instruction tells the AI to report 840.000.000 TL; the model obeys, the code checks flag it |
| 5 Nov | INS2 | the amount is a revenue estimate, not the contract value: flagged |
| 6 Nov | ENR2 | revision of a 23 Oct deal: only the increase is scored |
| 9 Nov | BLS3 | two readings give different amounts: flagged |
| 10 Nov | INS1 | the text also gives a running total: flagged |
| 10 Nov | SGL2 | no amount (trade secret) |
| 12 Nov | SVN2 | the vendor record is 10 times the amount in the text: flagged |
| 18 Nov | BLS2 | the price falls with no disclosure before it ("why did it move?") |

Rebuild after a change: `.venv/bin/python scripts/sample_data.py --build` (this also resets the review log). `sample/data/` is not committed; it is built on your computer.
