# Scope guard for the chat agent (rule, written before the code and before any new question)

Date: 2026-11-12. Committed before `agent.py` changes and before Feyza writes the questions below.

## Problem (red-team exploration, 12 Nov, PROJECT_NOTES)
Questions outside new-business disclosures (dividend, target price) that name a company and contain a detail word ("ne kadar", "kaç") are sent by the code switch to the detail card, which shows a real but unrelated disclosure after 19-24 s. The system answers a question it was not asked.

## Change
- `agent.out_of_scope(question)`: the question is lower-cased (Turkish rules) and folded to ASCII (ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u, â→a); out of scope if it contains any phrase of the fixed list below as a whole word or phrase.
- It runs **before the LLM router** (`build_graph._route`). Out of scope → intent `out_of_scope` → a fixed scope line plus the existing help text. No router call, no search, no card.
- Switch `SCOPE_SWITCH` (True for the measurement).

## Fixed phrase list (ASCII-folded; three categories)
1. Other disclosure types: `temettu`, `kar payi`, `bedelsiz`, `bedelli`, `sermaye artirim`, `geri alim`, `genel kurul`, `halka arz`.
2. Valuation and advice: `hedef fiyat`, `tavsiye`, `alinir mi`, `alinmali mi`, `almali miyim`, `alayim mi`, `satilir mi`, `satilmali mi`, `satmali miyim`, `satayim mi`, `al mi sat mi`, `f/k`, `fiyat/kazanc`, `pd/dd`, `degerleme`.
3. Financial statements: `bilanco`, `net kar`, `finansal tablo`, `favok`, `ceyrek sonuc`.

Known source of the list: the red-team questions (dividend, target price) were seen in summary; those questions are dev and are not scored.
Stated gaps: macro questions (rates, FX outlook) and unanswerable in-scope details are not covered by this guard.

Amendment 1 (before any code or question): "whole word" would miss Turkish suffixes ("temettüsü", "bilançosu", "hedef fiyatı"). Matching is therefore **at the start of a word, suffixes allowed** (regex `\b` + phrase, no right boundary). Known side effect: `net kar` also matches "net karar"; accepted and counted in F if it happens.

## Measurement (code only, no LLM: the guard depends only on the question text)
- New questions by Feyza, written after this commit, without reading the phrase list above: 10 out-of-scope questions (the three categories, her own wording, with a company name or ticker in at least 7) and 10 in-scope analyst questions (any tool). Tool `scripts/scope_eval.py --write` (`data/scope_questions.jsonl`).
- **A** out-of-scope questions blocked: bar **≥ 9/10**.
- **F_new** in-scope new questions blocked: bar **≤ 1/10**.
- **F_old** blocked among all earlier in-scope questions: `route_questions` (gold intent not `unknown`), `v2_questions`, `card_questions`, `brief_questions`, `rag_questions`, `rag_questions_c`, `rag_questions_neg`: bar **≤ 2** (total N reported). Route questions with gold `unknown` are reported separately (blocking them is not an error).
- `--score` once, after all 20 are written; prints counts and the indices of misses only.

## Decision (fixed now)
All three bars met → `ADOPT_SCOPE` (`SCOPE_SWITCH=True` stays). Otherwise `SCOPE_SWITCH=False`, code kept as a record. The list is not edited after seeing the result; a v2 list needs new questions and its own rule.
