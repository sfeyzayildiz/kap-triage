# Detail card: answer a question about one disclosure with extracted fields (rule written before code and questions)

Date: 2026-11-10. Committed **before** the code and before Feyza writes any question for it.

## Problem
A question about one disclosure ("FONET'in Aydın sözleşmesinin süresi kaç ay?") is routed to `company`, which lists the company's last 12 months and does not read the question. Letting the LLM write the answer was tried (cited answers v1-v3) and **not adopted**: it answered unanswerable questions confidently. Found by Feyza in the chat page, 2026-11-10.

## Design (no free text from the model)
1. **Detail switch (code, after `agent.validate`)**: if the validated intent is `company` or `search` and the question matches `DETAIL_RE`, the intent becomes `detail`. The LLM router and its prompt are unchanged.
   `DETAIL_RE` (case-insensitive, fixed here):
   `\b(kaç|kac|ne kadar|ne zaman|süres|sures|kim|karşı taraf|karsi taraf|tutar|bedel|teslim|hangi (ülke|ulke|şirket|sirket|firma|müşteri|musteri|kurum|para birimi|döviz|doviz)|nerede|nereye|nereden)`
2. **Detail tool**: the measured question search (`rag_index.search_question`: embed, top 20, cross-encoder rerank), filtered to the validated ticker if there is one. The top hit goes through the production extraction (`pipeline.analyze`: v3 + code checks + layered defence). The card shows, from code: date, ticker, KAP link, subject, event type, counterparty and origin, duration, amount and currency (VAT, revision and previous amount if any), related party, and the review flags in Turkish ("KONTROL ET"). Hits 2-5 are listed as links ("başka bildirim olabilir").
3. Notes on the card: amount and currency are measured (Set C: 1/100 silent, 11/100 flagged); the other fields are not measured; the card belongs to the disclosure shown, check the KAP text.

## Questions (Feyza)
- 10 new questions written by Feyza with `scripts/write_questions.py --out data/card_questions.jsonl --target 10`, after this rule and the code are committed. Each: the ticker written, one detail whose answer is in that disclosure's text (duration, counterparty, country, amount, delivery date...). Disclosures with an earlier Set B, C or D question are skipped. Claude does not propose questions.

## Measurement (run by Feyza, once)
`scripts/card_eval.py --run`: each question through the LLM router, `validate`, the switch and the detail tool. Stored per question: intent, top-1 news_id, seconds; card fields go to `data/` only. `--review`: Feyza sees each question, her own short answer and the card in her terminal and answers y/n: "does the card show the right answer to the question?". `--score`: counts only.
- **A** routed to `detail`: count of 10.
- **B** top-1 is the intended disclosure: count of 10.
- **C** Feyza's yes: count of 10.
- **D** median seconds per question (everything included).
- **R** regression, no LLM call: on the 20 routing questions (`data/route_questions.jsonl` with the stored LLM routes in `data/route_results.jsonl`), how many correctly routed questions the switch would change.

## Decision
- **Adopt the card** if A ≥ 8, B ≥ 8, C ≥ 7, D ≤ 45 s and R ≤ 1.
- If A, B and R pass but C or D fails: keep the switch, **card off** (`CARD=False`): `detail` shows the ticker-filtered search with links only.
- If A or R fails: remove the switch; the agent stays as it is.

## Honest limits
- 10 questions, one author, who also reviews the cards and knows the design.
- Only "the card shows the answer" is judged, per question; field accuracy beyond amount and currency stays unmeasured.
- The ticker filter on search is new; the measured search (Set D) had no filter.
