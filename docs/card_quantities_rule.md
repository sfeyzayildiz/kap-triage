# Card quantities: operational amounts found by code (rule written before code and review)

Date: 2026-11-10. Committed **before** the code and before any review.

## Problem (Feyza's chat use)
The card shows money amounts only. Operational quantities that tell an analyst the size of a deal ("20 adet araç", "505 MWm kapasite") are not shown. Adding a field to the extraction prompt would change the frozen v3 prompt (Set C PASS) and need a full re-evaluation, so this is code only.

## Design
- `scripts/quantities.py: find_quantities(text)`: a number (Turkish format, optional "bin / milyon / milyar") directly followed by a unit from a fixed list: `adet`, `MW`, `MWm`, `MWe`, `MWp`, `MWh`, `kW`, `kWh`, `kWp`, `GW`, `GWh`, `ton`, `km`, `m²`/`m2`, `m³`/`m3`, `metrekare`, `kilometre`, `megavat`. Money, dates and durations are not quantities here. Written as in the text, in text order, at most 6, duplicates removed.
- Card line: "Metinde geçen miktarlar (kodla bulundu): …". Nothing shown if none. The extraction, flags and amount are unchanged.

## Review (Feyza, once, in her terminal)
`python scripts/quantities.py --review`: 15 disclosures drawn with seed 20261110 from disclosures without any earlier question (Set B, C, D, card, v2). For each: the text and the found list; Feyza answers (a) is every listed item a real quantity of this deal? y/n, (b) how many quantities with these units did the code miss? (a number). `--score` prints counts only.

## Decision
- **Show on the card** if (a) is yes for at least **14 of 15** disclosures.
- Missed quantities are reported (recall), not a bar.
- Otherwise the line stays off (`SHOW_QUANTITIES=False`) and this is a stated limit.

## Honest limits
- 15 disclosures, one reviewer; units outside the list (e.g. "araç" without "adet", "litre") are not found by design.
- The quantity is shown as written; the code does not say what it counts.

## Amendment 1 (before any review)
A counts-only corpus check after the code was written: 158 of 1288 disclosures have at least one found quantity (239 items; adet 101, ton 34, MW 27, MWh 22, MWp 19, ...). A random draw of 15 would hold about 2 disclosures with a list, so (a) would be judged mostly on empty lists. The 15 are drawn instead (same seed, same exclusions) **from disclosures where the code finds at least one quantity**: this tests the lists the card would show. Missed quantities are still counted on these 15; recall on texts without any found quantity is not measured (stated limit). Bar unchanged: (a) yes on at least 14 of 15.
