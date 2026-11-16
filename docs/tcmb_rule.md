# tcmb-mcp: official TCMB rates to check Matriks' rate and to fill missing rates (rule, written before code and run)

Date: 2026-11-15. Feyza's choices (15 Nov): use the rate for **both** a check and gap filling; access through the **registry server**; wire the gap filling into the nightly list **after 26 Nov** (the sealed forward test, `docs/forward_test_rule.md`, runs 15-25 Nov on one unchanged system).

## Why
- The TL value of an FX amount (`importance.fx_rate`) takes the rate from Matriks' `tcmb_ex_rt` on **other** disclosures (same currency, latest on or before the day, at most 10 days back). Nobody has checked that rate against the central bank, and a currency without a recent Matriks record gets no TL value ("kur yok").
- Sizing before this rule (counts only): Matriks has 1045 FX records with a rate on 540 dates (USD 768, EUR 268, GBP 4, CNY 4, AED 1), 14 FX records without a rate. "kur yok" occurred **0** times on Set C (51 FX amounts), Set D run a (32) and the 43 saved morning items. So the gap filling is insurance for rare currencies; its benefit is not expected to be observable. The check is the main measurement.

## Server (external access approved by Feyza, 15 Nov)
- `io.github.mohammad-abbasi-sh/tcmb-mcp` from registry.modelcontextprotocol.io, PyPI `tcmb-mcp` **0.1.2** (MIT), stdio. Installed `--no-deps` (its two dependencies, `mcp<2` and `httpx`, are already in our venv), pinned in `requirements.txt`.
- Review (Claude, 15 Nov, wheel unpacked in the scratchpad, 4 files): one host only, `https://www.tcmb.gov.tr/kurlar` (`today.xml`, archive `YYYYMM/DDMMYYYY.xml`); no key; no child process, eval or telemetry; it sends a browser-like User-Agent; reads `https_proxy` if set; XML parsed with the standard library. A request carries only a date: no KAP or Matriks data leaves the machine.
- Use: tool `tcmb_get_rates_on(date)`. Our client `scripts/tcmb_check.py` caches each day's answer in `data/tcmb_cache/` (a day is fetched once, at most 1 request per second) and divides by `unit` (e.g. JPY per 100).

## Part 1: check (measured once, Feyza runs it; ~10-15 min the first time)
- **Unit:** each Matriks `new_business` record with a non-TRY currency and `tcmb_ex_rt > 0`.
- **Reference (primary, fixed now):** TCMB **forex buying** rate per one unit, from the bulletin dated the record's `date`; if that day has no bulletin (weekend, holiday), the latest bulletin before it (up to 7 days).
- **Match:** |Matriks / TCMB − 1| ≤ **0.5%**.
- **Reported, not decided:** the same with forex selling; with the bulletin of the previous business day; the median and p95 of the relative difference; mismatches by currency and year; records whose currency TCMB does not publish (counted, excluded).
- **Decision:** matched ≥ **95%** of the checked records → `MATRIKS_RATE_AGREES`; else `MATRIKS_RATE_DIFFERS`. Either way the counts go into the Matriks data-feedback doc; the mismatch ids go to `/tmp/tcmb_mismatches.txt` (ids only on stdout).

## Part 2: gap filling (wired on 26 Nov, only if Part 1 agrees)
- `importance.fx_rate` keeps the Matriks rate first; **only when it finds none**, it asks the TCMB forex buying rate of the disclosure date (same bulletin convention as Part 1). A failed TCMB call leaves "kur yok" as today (never blocks the list).
- Condition: `MATRIKS_RATE_AGREES` → `ADOPT_FILL`, wired on 26 Nov after the last seal; `MATRIKS_RATE_DIFFERS` → `FILL_OFF` (mixing two rate conventions would make TL values inconsistent).
- **Report only, from the Part 1 run, no LLM call:** on the Set C run 1 and Set D run a FX outputs, how many get a TCMB rate where Matriks gave none (expected 0); and the difference between the borrowed Matriks rate (`fx_rate`, up to 10 days old) and the TCMB rate of the disclosure date: median, max, and how many items would change importance level. This says whether borrowing a nearby record's rate is good enough; it changes nothing by itself.

## Note 1 (before the run, descriptive only)
- The installed wheel is the reviewed file itself (`pip install --no-deps <reviewed wheel>`), sha256 `9e14b700855a93385277398377499d2dd14c91b6725de86fe4b86cfa816cb50c`, equal to PyPI's published digest. **0.1.2 was uploaded on 2026-11-10** (five days before this rule): a young, single-author package with little outside use; trust rests on the full source review, not on adoption.
- `--plan`: 542 record days → 1061 days to look at (bulletin day, weekends, previous business day), ~18 min at 1 request per second the first time; a stopped run resumes from the cache. Smoke test (Claude, one date, 2026-11-13): 22 currencies, JPY per-unit handled, 3.8 s including server start; no Matriks value was compared.

## Limits
- TCMB indicative rates, not the contract's own rate; companies may convert at another rate. Matriks' exact convention (buying / selling, which bulletin) is not documented; Part 1 infers agreement, not intent.
- One reviewed version of a third-party package; an upgrade needs a new review.
