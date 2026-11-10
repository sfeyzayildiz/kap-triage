# Router v2: company names, two companies, dates in search, detail card (rule written before code, name table and questions)

Date: 2026-11-10. Committed **before** the code, before the name table is filled and before any question is written.

## Problem (Feyza's exploration in the chat page, 2026-11-10; exploration only, those questions are not reused)
1. A full company name (no ticker) ends in the help text: the router does not guess tickers from names and we have no name table.
2. A detail question about one disclosure gets the company's 12-month list (`company` does not read the question). The detail card (docs/detail_card_rule.md) failed mainly on (1): 0/10 questions wrote a ticker.
3. A search with a date ignores the date.
4. A counterparty's ticker in the question is taken as the company asked about.

## Changes (all code; the LLM router, its prompt and the extraction are unchanged)
1. **Name table** `data/company_names.txt`, one line per disclosure symbol: `SYMBOL: name1; name2` (plain text, edited in VS Code; a CSV would clash with Turkish Excel's `;` separator). Empty after the colon = no name. Filled by Feyza from public sources (or from a Matriks name field if the 11 Nov metadata has one). Its sha1 is recorded in PROJECT_NOTES **before** she writes the questions and checked by the script; it is not edited after that.
2. **Mentions** (`names.mentions`): tickers written in the question (as today) plus name matches. Matching: Turkish lower case, ASCII fold, punctuation to spaces; a name matches when its words appear in order as whole words, the last word may carry a suffix (prefix match) if it has at least 4 letters. Ordered by position in the question, one entry per symbol.
3. **Ticker choice in `validate`**: one mention → that symbol (no "inferred" note: the name was matched by code). Two or more → the **first** mentioned, with the note "Soruda birden fazla şirket geçiyor (A, B); A için cevap verildi." None → as today.
4. **Date in search**: `search` with a validated date searches only disclosures published that day; if none, it searches all and says so.
   Amendment 1 (smoke test before the name table and the questions: the LLM router returned no date for a question with "9 Kasım"): in v2, when the router gives no date, the date written in the question is read by code (`route_eval.word_date`: "9 Kasım", ISO dates, "dün", "bugün"), for every intent.
5. **Detail card on** (`DETAIL_SWITCH=True`), unchanged from docs/detail_card_rule.md.

## Questions (Feyza)
- 20 new questions with `scripts/write_questions.py --out data/v2_questions.jsonl --target 20`, written **after** this rule, the code and the frozen name table. Each is about the disclosure shown. Mix, roughly evenly: company name only, ticker, a date, a detail (duration, counterparty, amount...), a topic without a company. Natural analyst wording. Disclosures with an earlier Set B, C, D or card question are skipped. Claude does not propose questions.

## Measurement (run by Feyza, once): `scripts/v2_eval.py`
- Every question runs through **v1** (today's main: switch off, no names, no date filter) and **v2**, same LLM route call reused for both (the router is unchanged), full answer text stored in `data/`.
- **H (primary)**: the intended disclosure's KAP link is among the first 5 KAP links of the answer. v1 and v2, of 20.
- **Fixed / broken**: questions where H changes between v1 and v2.
- **C (card)**: among v2 answers that are cards, Feyza's y/n in `--review`: "does the card show the right answer to the question?".
- **R (regression, no LLM)**: on the 20 routing questions with their stored routes, correctly routed questions whose intent or ticker v2's code would change.
- **D**: median v2 seconds per question.

## Decision
- **Adopt v2** (names, two-company note, date filter) if H_v2 − H_v1 ≥ 3, broken ≤ 1, R ≤ 1 and D ≤ 45 s.
- **Card**: on only if v2 is adopted and C ≥ 70% of the card answers (at least 3 card answers); otherwise `DETAIL_SWITCH=False` and the rest of v2 stays.
- If v2 is not adopted: main stays as it is; the four problems are presented as measured limits.

## Honest limits
- 20 questions, one author, who also reviews the cards and knows the design.
- The name table is hand-made for the companies in our data; a new listing needs a new row.
- "First mentioned company" is a simple rule; a question naming the counterparty first gets the counterparty, with the note.
- The date filter uses the publish date; "around 9 Nov" is not supported.
