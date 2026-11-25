# Reviewing this project in 10 minutes

For a grader or a company reviewer who has not seen the project. Everything below is in the repository; no licensed data is in it (`data/` is never committed, checked over the full git history).

## Minutes 0-3: what and why
1. `README.md`, top: the problem, why the vendor's structured record is not enough, the story table (Set B failed, Set C passed), the building blocks with their numbers, screenshots from version 1's demo mode (licensed values hidden).
2. `docs/results.md`, first two sections: what Matriks gives vs what the system adds, and how to read the numbers (bounds, small sets, one annotator).

## Minutes 3-6: is it measured honestly?
3. `docs/results.md`, tables "Extraction" and "Security": Set B failed (4/100 silent), the fix was designed from its errors, Set C (unseen) passed (1/100, 95% upper bound 4.7%; recount it with `python main.py verify-results` from `evidence/set_c.jsonl`); the regex baseline gets 25/100 (same command, from `evidence/regex_set_c.jsonl`); prompt injection 9/18 → 0/18 with the layered defence (same command, from `evidence/injection_set_c.jsonl`). Rejected attempts are listed next to adopted ones.
4. Pick a rule file, for example `docs/fdv_pilot_rule.md` or `docs/source_sentence_rule.md`, and run `git log -- <file>`: the rule, the bar and the decision line come in one commit, the notes and the result in later ones (FDV: rule 19 Nov 02:27, freeze 16:19, result 17:07; source sentence: rule 20 Nov 02:19, result 02:42). Every pull request was squash-merged, so where a rule and its result were merged in the same pull request (for example `scope_guard_v3_rule.md`, `kap_kart_rule.md`, `demo_mode_rule.md`), `main` shows one commit for both. For those, the rule's own earlier commit is kept in the pull request of the private working repository (kap-kart rule 19 Nov 00:12, scope guard v3 rule 01:21, demo mode rule 18 Nov 21:03), and `docs/PROJECT_NOTES.md` has a dated "rule before code" entry for each.
5. `docs/known_issues.md`: what went wrong and what was done, including what an outside review found.

## Minutes 6-8: how it is built
6. `docs/architecture.md`: nightly path, analyst tools, where the LLM is used and where code decides.
7. `kap_triage/analysis/pipeline.py` (extraction + checks + defence, ~150 lines) and `kap_triage/collect/pull_guard.py` (one vendor pull per day, enforced in code). The running system is the `kap_triage/` package in four folders (`collect`, `analysis`, `assistant`, `web`) with one entry point, `main.py`; README, "The code", gives the reading order. Version 1 kept the same code in one `scripts/` folder; [`v1_to_v2_map.md`](v1_to_v2_map.md) says where each file went. CI runs `ruff` and `pytest` on every pull request (`.github/workflows/tests.yml`). `tests/test_sample_data.py` runs the real nightly chain (extraction with postprocessing, code checks, vendor cross-check, two readings, source-sentence judge, importance, morning list) on the made-up sample data, with only the model replaced by pre-written answers, then reads the result through the panel and the agent. To click through the panel yourself: `.venv/bin/python main.py panel --sample`, then open `http://127.0.0.1:8765/genel` (made-up data; setup and a 10-minute tour in `sample/README.md`).

## Minutes 8-10: try it without our data
8. README, "Try it in 2 minutes": the tests and the nightly chain on made-up disclosures run with no model and no data (`.venv/bin/pip install -e '.[dev]'`, then `.venv/bin/pytest`).
9. `/kart` in the panel (or `python main.py kart text.txt`): paste a public KAP "Yeni İş İlişkisi" text and get the same card the nightly job builds, on your own computer (needs Ollama). Four made-up trap examples are in `sample/kart/`.

## What is not claimed
- No user or time study; analyst time saved is not measured.
- One person labeled every gold set; held-out sets are new disclosures, not new companies.
- The importance score did not beat sorting by amount; the live order is a simple, measured rule.
- The forward test (lists sealed each night before prices exist) was shortened to end with 20 Nov and scored once on 24 Nov (rule Notes 7-9): seals intact, 3 look-first and 3 other items, so the decision is `TOO_FEW` (the bar needs 4 per group). It shows that sealing, the later price pull and the one-time scoring work end to end; it is not a trading claim.
- Running the full system needs a Matriks token; the README screenshots come from version 1's demo mode because the license forbids showing vendor values, and the panel in this repository runs on made-up sample data.
