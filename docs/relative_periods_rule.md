# Relative periods ("geçen hafta", "bu ay", "son 3 ay"): rule, written before code and questions

Date: 2026-11-13. Red team (12 Nov) failure 5: "geçen hafta" is not parsed, so search ignored the period (`known_issues.md` B2). Today only single days work ("bugün", "dün", "28 Ekim", ISO dates).

## Design
- **Code, not the LLM.** A fixed parser `period(question, today)` returns `(start, end)` or `None`. The router prompt is not changed (scope v2 showed the small model over-reacts to new prompt lines). A parsed period overrides the router's `date`.
- A written single day ("28 Ekim", "dün", ISO) wins over a period: then no period.
- Switch `PERIODS` (True for the measurement only).

## What the parser understands (fixed now; Turkish letters or ASCII, any case)
| phrase | period (`today` = the system date) |
|---|---|
| bu hafta | Monday of this week .. today (weeks start on Monday) |
| geçen hafta / geçtiğimiz hafta | previous Monday .. previous Sunday |
| bu ay | 1st of this month .. today |
| geçen ay / geçtiğimiz ay | the whole previous calendar month |
| bu çeyrek | first day of this calendar quarter .. today |
| geçen çeyrek / geçtiğimiz çeyrek | the whole previous calendar quarter |
| bu yıl / bu sene | 1 January .. today |
| geçen yıl / geçen sene / geçtiğimiz yıl | the whole previous calendar year |
| son N gün / hafta / ay / yıl (sene) | today minus N units .. today (same day number, clipped to month end) |
| son gün / hafta / ay / yıl, "son bir ..." | as N = 1 |

N is digits or a word from bir .. on iki. Not parsed (stated limit): "önceki hafta" (ambiguous), "birkaç", "son günlerde", "yakın zamanda", "ayın başında", named weeks, fiscal periods.

## What the tools do with a period
- **company:** the disclosures in the period (instead of the last 12 months); header names the period.
- **search / detail:** the search is restricted to the period; if nothing is found there, it says so and searches all dates (same as the single-day filter today).
- **morning:** a period list: every disclosure in the period by date (company, Matriks amount, new/update, KAP link), at most 30 lines. Importance ordering stays single-day only (it needs extraction; a week would take minutes). Said in one line.
- **why_moved, brief:** the period is not used; a note says so (why_moved explains one day; brief has its own window).
- An end after the last collected day is clipped to it, with the existing note.
- The guided form is unchanged (one day).

## Measurement (Feyza; questions written after this commit, without reading the parser code)
`scripts/period_eval.py --write`: a fixed reference day **2026-11-13** (Friday) is used as `today` for every question.
- **10 period questions** in her own wording (at least 6 different phrases from the table, at least 6 with a company or a topic), each with the expected start and end typed by her from the table above.
- **5 no-period questions** that use words like "son", "geçen", "hafta", "ay" in another sense (not a time window for the search), expected `None`.
- `--score` once: code only, no LLM, seconds.

Bars:
- **P** exact (start and end) on period questions: **≥ 9/10**.
- **N** false period on the 5 no-period questions: **≤ 1/5**.
- **O** earlier questions (the 185 in-scope sets + the 20 scope v2 questions) where the parser fires: listed by index. Feyza reads only those (her own questions) and marks each "asks this period: yes / no" in `--judge`; wrong fires **≤ 2**.

## Decision (fixed now)
All bars met → `ADOPT_PERIODS` (`PERIODS=True`). Otherwise `PERIODS=False`, code kept as a record. The phrase table is not changed after seeing a result; a missed phrase becomes a stated limit or a v2 with new questions.

## Limits
One person writes the questions and knows the table; the parser is a fixed list, so wordings outside it are missed by design (stated in the help text). The tools' "only inside the period" behavior is checked by self-tests, not by the measurement.
