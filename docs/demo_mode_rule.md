# Demo mode: rule (written before code, 18 Nov 2026)

## Why
The demo video and the 5-minute company talk show the panel on screen. The Matriks licence lets us show KAP text and what we extract from it, but not Matriks structured data. Demo mode is a **display flag**: it replaces licensed values with "Matriks verisi, lisans gereği gizli" on every panel page. It does not change what the nightly job computes or stores, and it is off by default.

## Scope (Feyza, 18 Nov)
- All panel pages: day list (`/day/...`), start page and chat (`/chat`), guided form and its answers (`/form`: brief, why-moved, search), themes (`/themes`, `/themes/...`), reliability (`/guvenilirlik`).
- Not in scope: the n8n JSON (`/api/desks/...`). It is read by the 07:30 workflow, not shown on screen; changing it would send desk e-mails to wrong mailboxes. It already carries no amounts and no text (`docs/n8n_routing_rule.md`).
- Desks: shown as "Masa 1", "Masa 2", ... A sector always gets the same number (stable order), and the real sector name never appears.

## What is hidden (licensed, from Matriks)
| field | where it appears today |
|---|---|
| Revenue ratio (`size_vs_revenue`, "tutar / şirketin yıllık geliri") | card reasons, brief |
| Matriks FX rate and anything converted with it (TL equivalent, "kur yok") | card reasons, brief |
| Sector names | desk headings, themes page ("sektörler: ...") |
| Prices and price reactions (chart, "Fiyat: ...", "XU100'e göre", why-moved answers) | card, brief, chat, form |
| Matriks `new_business` amounts and the cross-check value | wherever shown |

## What stays visible
- The KAP link, headline, publication time, company code and name (public on kap.org.tr).
- The amount and currency **extracted from the KAP text** and the source sentence with the amount marked.
- Flags (`needs_review` codes) and the reviewer's confirm/reject buttons.
- The importance level and the list order. They are computed by our code; no Matriks value can be read back from "high/low" or from the order. Reasons that show a Matriks number (ratio, rate, price) are replaced by the placeholder; reasons from the text (duration, currency) stay.

## How it is measured
1. **Synthetic test (self-test, CI):** fixtures carry unique marker values for every hidden field (a ratio, a rate, a sector name, a price move, a Matriks amount). Every page above is rendered in demo mode; the count of markers in the output must be **0**. The same pages rendered with demo mode off must contain the markers (proves the test can see them), and must be byte-identical to today's output (demo mode changes nothing when off).
2. **Real-data check (Feyza runs, counts only):** `scripts/demo_leak_check.py` renders every page for every available day in demo mode and counts occurrences of the real sector names (from `symbol_sectors`), the phrases "yıllık geliri", "XU100", "kur" in reason lines, and price chart figures. Prints counts only, never the values.
3. **Visual check (Feyza):** she opens the panel in demo mode and looks at one day, the chat, one brief and the themes page.

## Amendment 1 (18 Nov, with the code, before any measurement; nothing has been run on real data)
Found while writing the code; needs Feyza's approval before the leak check runs.
1. **Numeric score hidden.** The score ("skor 7") sums points from the revenue ratio and the history/TL size, so it is a "score part using" Matriks values. Demo mode shows the level ("yüksek") and keeps the order, without the number. Hidden reason codes: `size_vs_revenue`, `size_vs_history` (Matriks amounts and FX rate), `size_absolute` (TL size via the Matriks rate), `no_rate`. Visible: currency, duration, revision, no amount.
2. **Sector names are measured by difference, not by a plain count.** A plain count of real sector names would also hit company names and KAP text (e.g. a company called "... Enerji" when a sector is "Enerji") and fail for the wrong reason. Instead each demo page is rendered twice: with the real sector table and with an order-preserving neutral one (NOTR001, NOTR002, ...: same desk numbers). Count = demo pages that differ (a page that differs depends on a sector name). Also counted: the phrase "sektörler:".
3. **Phrases are counted as our own templates**, not single words, for the same reason: "tutar / şirketin yıllık geliri", "şirketin önceki işlerinin medyanının", "TL karşılığına göre büyüklük", "için kur yok, büyüklük hesaplanmadı", "XU100", "tepki günü", a "Fiyat:" line without the placeholder, "hisse +x", a z value, `<figure class="chart">`/`<svg>` (not on the reliability page: our own results), "skor N", "(Matriks kaydı)", "Matriks tutar kaydı", and an amount field in company/period/brief history lines.
4. **Chat and form pages without the LLM.** The leak check renders the deterministic answers for each saved day (morning list, the day's week as a period list, and per company of the day: last 12 months, why-moved, brief built from the saved list + the SQL history step, detail card) on the chat page and the guided form (with the real price chart passed in). Router answers go through the same tools and the same renderer, so the LLM adds no new line shape. Each page is also rendered with demo mode off; the counts there are printed as "seen with demo off" (proof the check can see what it counts).
5. **A page that fails to render** is reported as a render error; any render error makes the result INCOMPLETE, not a pass.
6. **Demo-off unchanged** (measurement 1) is checked as a hash of the seven fixture pages rendered by the code before demo mode (main 6bf5e9c): `98f6bf3fc8ea3057`.

## Decision
- **ADOPT_DEMO_MODE** if (1) synthetic leaks = 0 and demo-off output unchanged, (2) real-data count = 0 on every page and day, and (3) Feyza's visual check finds nothing.
- Any leak in (2) or (3): fix and re-run all three; the result is reported with the number of rounds. Demo mode is never used for the video until all three pass.
- Demo mode stays a display flag; it is not part of the nightly path and needs no kap-deploy change before the 26 Nov freeze.

## Result (19 Nov 2026)
**ADOPT_DEMO_MODE, round 1.** (1) synthetic: 52 checks, leaks 0, demo-off hash unchanged (`98f6bf3fc8ea3057`); (2) real data: `LEAKS=0 -> pass` (0 render errors); (3) Feyza's visual check: clean.
