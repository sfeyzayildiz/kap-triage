# Reviewing this project in 10 minutes

For a grader or a company reviewer who has not seen the project. Everything below is in the repository; no licensed data is in it (`data/` is never committed, checked over the full git history).

## Minutes 0-3: what and why
1. `README.md`, top: the problem, why the vendor's structured record is not enough, the three layers, screenshots in demo mode (licensed values hidden).
2. `docs/results.md`, first two sections: what Matriks gives vs what the system adds, and how to read the numbers (bounds, small sets, one annotator).

## Minutes 3-6: is it measured honestly?
3. `docs/results.md`, tables "Extraction" and "Security": Set B failed (4/100 silent), the fix was designed from its errors, Set C (unseen) passed (1/100, 95% upper bound 4.7%); the regex baseline gets 25/100; prompt injection 9/18 → 0/18 with the layered defence. Rejected attempts are listed next to adopted ones.
4. Pick any rule file, for example `docs/scope_guard_v3_rule.md` or `docs/kap_kart_rule.md`: the rule, the bar and the decision line were committed before the measurement; the result section was added after one run. Git history shows the order.
5. `docs/known_issues.md`: what went wrong and what was done, including what an outside review found.

## Minutes 6-8: how it is built
6. `docs/architecture.md` (Turkish summary: `docs/mimari_ozet.md`): nightly path, analyst tools, where the LLM is used and where code decides.
7. `scripts/pipeline.py` (extraction + checks + defence, ~200 lines) and `scripts/pull_guard.py` (one vendor pull per day, enforced in code). Every module has `--self-test`; CI runs all of them on every pull request (`.github/workflows/`). `scripts/e2e_check.py` runs the real nightly chain (extraction with postprocessing, code checks, vendor cross-check, two readings, source-sentence judge, importance, morning list) on three made-up disclosures in a temporary database, with only the model replaced by a fake.

## Minutes 8-10: try it without our data
8. `kap_kart/`: paste a public KAP "Yeni İş İlişkisi" text and get the same card the nightly job builds, on your own computer (`./kap_kart/run.sh`, needs Ollama). Four made-up trap examples included.

## What is not claimed
- No user or time study; analyst time saved is not measured.
- One person labeled every gold set; held-out sets are new disclosures, not new companies.
- The importance score did not beat sorting by amount; the live order is a simple, measured rule.
- The forward test (lists sealed 15-25 Nov) is scored once on 27 Nov, after the submission date; it checks the live pipeline without hindsight, it is not a trading claim.
- Running the full system needs a Matriks token; screens are shown in demo mode because the licence forbids showing vendor values.

## Submission checklist (for the author)
- [ ] Repository access for the instructor: read-only collaborator on the private repo (licence: no public copy).
- [ ] `README.md` and `docs/results.md` current (pilot 2 result added when scored).
- [ ] CI green on `main`.
- [ ] Gist (`docs/mimari_ozet.md`) updated if the architecture text changed.
- [ ] Forward-test status written as "running, scored 27 Nov".
- [ ] Demo mode screenshots in `docs/img/` current.
