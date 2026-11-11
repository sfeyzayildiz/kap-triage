# Company brief: a multi-step LangGraph flow (rule written before code and questions)

Date: 2026-11-11. Committed **before** the code and before Feyza writes any question for it.

## Problem
Every agent tool today is one step: route → one tool → answer. An analyst who asks "ASELS'e bak" wants four things at once: the latest disclosure (what, how big, reliable?), the company's recent history, how the stock reacted, and whether something similar happened before. Today that is four questions. This flow runs the four steps in one graph; it is also the project's real multi-step LangGraph use (course day 7).

## Design (no free text from the model)
1. **Brief switch (code, after `agent.validate`)**: validated intent `company` with a ticker, and the question matches `BRIEF_RE` → intent `brief`. The LLM router and its prompt are unchanged (its 17/20 measurement stands). `BRIEF_RE` (case-insensitive, fixed here):
   `\b(bak|bakalım|bakalim|özet|ozet|özetle|ozetle|değerlendir|degerlendir|genel durum|ne durumda|durumu|brief)\b`
2. **Graph**: `route → latest → history → reaction → similar → compose → END`, each node a function that reads and writes the shared state; every step records its seconds in `state['steps']`.
   - `latest`: the company's most recent disclosure on or before the day (default: the last collected day); production extraction (`pipeline.analyze`: v3 + code checks + layered defence); importance score (`importance.score_result`, same code as the morning list).
   - `history`: last 12 months of the company (count, updates, Matriks amounts where present, KAP links; same query as the `company` tool).
   - `reaction`: price reaction of the latest disclosure vs. XU100 (`morning.reaction`, same as the morning list), plus the "unusual?" z-score when available.
   - `similar`: the company's earlier disclosures most similar to the latest one (`rag_index.similar_earlier`, k=3).
   - `compose`: the brief text from code: card of the latest disclosure (same `card_lines` as the detail card) + importance level and reasons in Turkish + `KONTROL ET` flags, price line, history list (≤ 8 links), similar list, and the standing notes (what is measured, what is not; read the KAP text). A step that fails writes one line ("… hesaplanamadı") and the others still show.
3. Shown in the chat page like any other tool. Nothing else changes.

## Questions (Feyza)
`scripts/brief_eval.py --write`: Feyza types 10 questions, each with the intended ticker (company name or ticker, in her own words, e.g. "Şa-Ra'ya bir bak", "KONTR genel durum"). Claude does not propose questions. Stored in `data/brief_questions.jsonl` after this rule and the code are committed.

## Measurement (run by Feyza, once)
`scripts/brief_eval.py --run`: every question through the LLM router, `validate`, the switch and the graph. Stored: intent, ticker, latest news_id, per-step seconds, which sections rendered with data, total seconds; the brief text goes to `data/` only. `--review`: Feyza reads each brief in her terminal with the KAP links open and answers y/n: "the brief is about the right company, its latest disclosure is the one shown, and the card and price line are correct for a first look". `--score`: counts only.
- **A** routed to `brief`: count of 10.
- **B** right ticker (validated ticker = intended): count of 10.
- **C** Feyza's yes: count of 10.
- **D** median total seconds; also median per step (report).
- **R** regression, no LLM call: on the 20 routing questions (`data/route_questions.jsonl` + stored routes), correctly routed questions the switch would change.

## Decision
- **Adopt** if A ≥ 8, B ≥ 9, C ≥ 7, D ≤ 60 s and R ≤ 1.
- If A, B and R pass but C or D fails: switch stays, the brief shows only the sections that were right (decided from the review notes, stated in PROJECT_NOTES) or is reported as a limit; no retuning on these 10 questions.
- If A or R fails: remove the switch (`BRIEF_SWITCH=False`); the agent stays as it is.

## Honest limits
- 10 questions, one author who also reviews. Field accuracy beyond amount and currency is still unmeasured; the importance score is a ruled ranking, not a prediction.
- The brief reuses measured parts (extraction, search index, price reaction code); what is new and measured here is only the routing, the ticker and the assembly.
