# Sample data (made up)

The real data comes from Matriks under a license and cannot be shared. This folder lets you run the panel on your own computer without it.

**Everything here is invented:** 12 companies, 57 "Yeni İş İlişkisi" disclosures (Sep to Nov 2026), vendor-style records, sectors, exchange rates and daily prices. Tickers contain a digit (`SVN1`, `BLS2`), which no BIST ticker has. KAP links point to `kap.org.tr/tr/Bildirim/ornek-...`, which is not a real disclosure.

## Run it
Tested with Python 3.12 (the package versions are pinned).
```
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python scripts/panel.py --serve --sample
```
Open `http://127.0.0.1:8765/genel` (overview). The first start builds `sample/data/` (a few seconds). On Windows, create the environment with `python -m venv .venv` and replace `.venv/bin/` with `.venv\Scripts\` in the other two commands.

## A 10-minute tour
Open each link with the panel running. The screen labels are in Turkish; they are quoted here as they appear.

1. **Overview**: http://127.0.0.1:8765/genel
   You see the last morning list in numbers, a column chart of the last 30 lists, the "Önce bak" (look first) items, review decisions and three measured results. Red in a column is **kontrol et** (sent to a person), amber is **önce bak** (high importance). Move the mouse over a column to see its numbers; click it to open that day.
   *Shows:* the analyst's question "which of today's disclosures matter?" answered in one screen.
2. **A big contract**: http://127.0.0.1:8765/day/2026-11-02
   SVN1 is on top: a 38.5 million USD, 3-year contract, 18% of the company's yearly revenue. "Neden" lists every reason for the score, and the "Kaynak cümle" (source sentence) shows the amount in the KAP text.
   *Shows:* the score is computed by code from the extracted facts, so every point has a reason ([rules](../docs/importance_v2_rule.md)).
3. **A planted instruction**: http://127.0.0.1:8765/day/2026-11-04
   SGL1's text hides one sentence that tells an AI to report 840,000,000 TL. The (pre-written) model answer obeys it. The card is red: **KONTROL ET**, because the amount differs from the vendor record and comes from an instruction-like sentence. Click "Yanlış (çıkarım hatalı)", since the real amount is 8,400,000 TL.
   *Shows:* the model can be fooled; the code checks catch it and a person decides ([defence rule](../docs/layered_defence_rule.md)).
4. **Unclear currency**: http://127.0.0.1:8765/day/2026-11-03
   BLS1 writes "96.000.000 TL (2.200.000 EUR)". Is the deal in TL or EUR? The system does not guess: **kontrol et**.
   *Shows:* a TL/USD mix-up was a real error type in our tests; now it goes to a person.
5. **Two readings disagree**: http://127.0.0.1:8765/day/2026-11-09
   BLS3 has two amounts in two currencies. Every text is read twice (the same model reads it a second time); here the readings differ, so it is flagged ([rule](../docs/set_d_rule.md)).
6. **Your decision is saved**: http://127.0.0.1:8765/kontroller
   The decision from step 3 is here, with a chart of how often each flag type caught a real error.
   *Shows:* the analyst's feedback becomes a measure of the checks.
7. **Follow a company**: http://127.0.0.1:8765/day/2026-11-02
   Click "Takibe al" (follow) on the SVN1 card, then "Sadece takip ettiklerim" (only the ones I follow) to filter the list. Back on http://127.0.0.1:8765/genel, the first section "Takip ettiklerin" lists SVN1 (with a "Çıkar" button to remove it) and shows the followed companies that are in the last morning list.
   *Shows:* each analyst keeps the companies they cover; the list is saved in `sample/data/watchlist.json`.
8. **Why did the stock move?**: http://127.0.0.1:8765/form?type=why_moved
   Choose SVN1 and the date 2 November 2026 (the date box uses your system's date format): an abnormal move, with the disclosure linked. Then BLS2 and 18 November 2026: also abnormal, but no disclosure before it, and the answer says so.
   *Shows:* the system says "not from a disclosure, the cause may be elsewhere" instead of inventing a reason.
9. **Weekly themes**: http://127.0.0.1:8765/themes/2026-11-02 (groups of similar disclosures in one week).
10. **Measured reliability**: http://127.0.0.1:8765/guvenilirlik
   The real results, measured on the licensed data (aggregate results only; no disclosure text or data is shared): 1 silent error in 100 new disclosures, the "without an LLM" comparison, the injection test.

## What works without a model
| page | works on sample data |
|---|---|
| Genel bakış (overview: last list, 30-day chart, look-first items, review decisions, reliability) | yes |
| Sabah listeleri (morning lists, one per day, by desk) | yes |
| Kontrol et (confirm / reject a flagged item) and Kontrol geçmişi (every decision, by flag type) | yes, written to `sample/data/review_log.jsonl` |
| Takip listesi (watchlist: follow a company on a card or on the overview, filter the morning list to it) | yes, written to `sample/data/watchlist.json` |
| Haftalık temalar (weekly themes) | yes |
| Güvenilirlik (measured results) | yes |
| Rehberli sorgu: day list, company history, "why did it move?" | yes |
| Rehberli sorgu: Şirket özeti (company brief) | needs Ollama with `gemma4:e4b` (it reads the latest disclosure); its "similar earlier disclosures" part says the search index is missing |
| Sohbet (chat), topic search, and the detail card (the answer to a question in the chat or the guided form) | needs Ollama with `gemma4:e4b` and the embedding model |

## How it is built
`scripts/sample_data.py` writes the texts and records, then runs the **real nightly chain** on them: extraction checks, vendor cross-check, two readings, source-sentence check, importance score, price reaction, company history. Only the language model is replaced by pre-written answers (what the model reads from each text), so no model is needed. Similar earlier disclosures stay empty, because they need the embedding model.

Some disclosures are built to show one behavior each:

| day | company | what the system does |
|---|---|---|
| 2 Nov | SVN1 | large USD contract, 3 years, 18% of yearly revenue: high importance; the price jumps that day |
| 3 Nov | BLS1 | "96.000.000 TL (2.200.000 EUR)": currency unclear, **kontrol et** |
| 4 Nov | SGL1 | a planted instruction tells the AI to report 840,000,000 TL; the model obeys, the code checks flag it |
| 5 Nov | INS2 | the amount is a revenue estimate, not the contract value: flagged |
| 6 Nov | ENR2 | revision of a 23 Oct deal: only the increase is scored |
| 9 Nov | BLS3 | two readings give different amounts: flagged |
| 10 Nov | INS1 | the text also gives a running total: flagged |
| 10 Nov | SGL2 | no amount (trade secret) |
| 12 Nov | SVN2 | the vendor record is 10 times the amount in the text: flagged |
| 18 Nov | BLS2 | the price falls with no disclosure before it ("why did it move?") |

Rebuild after a change: `.venv/bin/python scripts/sample_data.py --build` (this deletes `sample/data/` first, so it also resets the review log and the watchlist). `sample/data/` is not committed; it is built on your computer.
