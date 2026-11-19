# Development timeline

Generated from the git history of `main` by `scripts/make_timeline.py`; not edited by hand. 2026-10-26 to 2026-11-19: **168 commits on 23 of 25 days**, 154 of them merged pull requests (the first days were direct commits). Every measured result also has a rule file that was committed before it; this page shows the order in which the work happened.

## Week of 2026-10-26

**2026-10-26 (Mon)**: 5 changes
- Initial commit: Project skeleton, rules, and explore.py
- docs/kap manual notes (#1)
- feat/regex baseline (#2)
- feat/llm extract (#3)
- Add Matriks KAP API probe (search + page) (#4)

**2026-10-27 (Tue)**: 10 changes
- Add KAP form table parser (#5)
- feat/collector (#6)
- analysis/unmatched disclosures (#8)
- Fix scoring when both amounts are null (#9)
- feat/llm retry (#10)
- Add daily collector wrapper with ntfy alerts (#11)
- Schedule daily collector on Mac with launchd (#12)
- Add test set sampling script excluding dev set and eval_v1 (#13)
- Add --ids and --out options to eval_vs_matriks (#14)
- Move prompts to versioned files and record prompt/model/test set in eval output (#15)

**2026-10-28 (Wed)**: 5 changes
- Set A error analysis: annotation guidelines and adjudicated scoring (#16)
- Robustness: DB lock retry, LLM timeout, eval error handling (#17)
- Run nightly launchd job from a separate deploy clone on main (#18)
- Extraction v3: review reasons, cleaned prompt, code consistency checks, Set A evaluation (#19)
- Add thinking and max-token settings, record run settings in eval rows, ceiling test results (#20)

**2026-10-29 (Thu)**: 2 changes
- Extraction v4 experiment (rejected): mixed-currency headline, guidelines v1.2, headline scoring (#21)
- Add timestamps to daily collector log lines (#22)

**2026-10-30 (Fri)**: 2 changes
- Set B evaluation: silent-error scoring and amount checks (#23)
- Small fixes: default prompt v3, readline, test-set guard, gold amount check (#24)

**2026-10-31 (Sat)**: 1 change
- RAG embeddings: normalization, retrieval eval, model choice (#25)

**2026-11-01 (Sun)**: 1 change
- Combined extraction pipeline (#26)

## Week of 2026-11-02

**2026-11-02 (Mon)**: 8 changes
- Daily price bars from Matriks; detailed Set C labeling guide (#27)
- Importance score v1: rules in code, revenue ratio off (#28)
- Price moves: disclosure reactions and abnormal-move scan (#29)
- Morning list: one command from disclosures to ranked report (#30)
- Search index with incremental updates; similar earlier disclosures in the morning list (#31)
- Triage agent with LangGraph: LLM routes, code answers (#32)
- README: problem, system, measured results, how to run; update task queue (#33)
- Notes: no daily price update, one refresh before the demo (#34)

**2026-11-03 (Tue)**: 2 changes
- Daily collector: wait for network before pulling; alert failure no longer hides the error (#35)
- Daily collector: say giving up on the last network attempt (#36)

**2026-11-04 (Wed)**: 1 change
- Corpus stats and demo candidate days (#37)

**2026-11-05 (Thu)**: 3 changes
- Notes: prod probe v2 result, revenue gap comes from balance-sheet periods (#38)
- Prod switch for new_business, one-time prod archive refresh with apitest snapshot (#39)
- Notes: Matriks approved the prod archive refresh (#40)

**2026-11-06 (Fri)**: 1 change
- Labeling guide: RAG question types with answer shapes, same-company type (#41)

**2026-11-08 (Sun)**: 15 changes
- Daily collector: log collector output, alert with the real error line (#42)
- Daily collector: log the lock holder, retry the lock for 30 minutes (#43)
- Notes: do not claim the lock holder was not Claude (#44)
- CLAUDE.md: current task queue and schedule for a fresh session (#45)
- CLAUDE.md: course alignment, final-project gaps and the plan to close them (#46)
- Set C: label checks, frozen gold and result (PASS, 1/100 silent) (#47)
- eval_vs_matriks: amount mismatches to /tmp, stdout counts and ids only (#48)
- Held-out retrieval on Set C questions (#49)
- Architecture doc with diagram (#50)
- Latency: rule, script and result (#51)
- CI: run all module self-tests on every PR and push to main (#52)
- label_set_b: --redo keeps the RAG question unless changed (keep/new/delete prompt) (#53)
- BM25 hybrid: rule, code, held-out result (embed stays) (#54)
- Cross-encoder rerank: rule, result (adopted) and agent search (#55)
- Notes: 8 Nov night run OK, gap filled (#56)

## Week of 2026-11-09

**2026-11-09 (Mon)**: 10 changes
- Morning list runs after the nightly collection, counts-only alert (#57)
- Demo script draft for 14 Nov (#58)
- Clustering: themes and sector evaluation (rule first) (#59)
- Sector labels loader; price refresh re-pulls symbols for a new end date (#60)
- Prompt-injection test: rule before measurement (#61)
- Prompt-injection test code (run and score), not run yet (#62)
- Notes: prompt-injection result (amount attack 20/20, 14 silent) (#63)
- Prompt-injection defence: tried and not adopted (record) (#64)
- Matriks cross-check: tried, close, not adopted (record) (#65)
- Layered defence against injected amounts (adopted)

**2026-11-10 (Tue)**: 17 changes
- Wire layered injection defence into pipeline and morning list
- Desk panel with human confirm step
- Panel review stats per reason code
- Cited answers: tried, not adopted (record)
- Cited answers v2/v3: dev iterations, held-out kept unused (record)
- Revenue ratio (switch off) and demo script update
- Runbook, deploy check, README update
- Agent routing measured: keep LLM router (17/20 vs 9/20)
- Revenue ratio on; prod refresh recorded
- Metrics cheat sheet
- Agent: today before collection, clean output
- Notes: second dogfooding round
- Chat page for the agent in the panel (#79)
- Detail card for questions about one disclosure (#80)
- Router v2: company names, two-company note, date filter, detail card (#81)
- Chat page: example questions for names, details and dates (#82)
- Name table v1.1: short names, code-only regression (#83)

**2026-11-11 (Wed)**: 5 changes
- Card quantities: rule, finder, review result (OFF) (#84)
- Notes and demo script: 11 Nov pull, clustering, two pulls on 10 Nov (#85)
- Cited answers v4 (gemma4:26b): rule, code, dev result (not adopted) (#86)
- Ablations: regex baseline on Set C, rerank depth, chunking (report only) (#87)
- Company brief: multi-step LangGraph flow, adopted (9/10, 10/10, 9/10, 18.5 s) (#88)

**2026-11-12 (Thu)**: 16 changes
- One pull per day in code: pull_guard marker, SKIPPED alert in daily_collect; notes on the 11 Nov double pull (#89)
- Model family ceiling test on Set A (qwen3:14b, Turkish-Gemma-9b-T1), report only (#90)
- Importance score vs blind look-first choice: rule and tool (#91)
- Weekly themes page in the panel (#92)
- Notes: red-team exploration of the chat agent (16 questions, 7 right) (#93)
- Scope guard for out-of-scope questions (#94)
- Notes: name-matching red-team case not reproduced; wrong diagnosis corrected (#95)
- Docs: one-page results, README name, architecture agent diagram, metrics FAQ and demo script updated (#96)
- Importance ordering v2: rule, dev choice, round 2 (#97)
- Guided question form and panel theme (#98)
- Price chart on panel cards and form answers (#99)
- Reliability page and theme switch (#100)
- Docs: guided form, price chart, reliability page and ordering v2 in README, architecture and demo script (#101)
- Docs: known issues (what we got wrong: fixed, fixable or accepted) (#102)
- Docker setup (#104)
- Docs: system card and how the system extends to other disclosure types (#105)

**2026-11-13 (Fri)**: 6 changes
- Scope guard v2: measured, SCOPE_V2_OFF (#103)
- Relative periods: measured, ADOPT_PERIODS (#106)
- n8n desk e-mails: measured, ADOPT_N8N (#107)
- Docs: periods, n8n desk e-mails, scope v2 (#108)
- Fields measured: long KEEP, foreign OFF, related OFF (#109)
- Demo script: n8n desk e-mails, relative periods, 13 Nov results (#110)

**2026-11-14 (Sat)**: 3 changes
- Drift check after Set C: NO_DRIFT_SEEN (#111)
- Sealed forward test: rule before any sealed list; seal in the nightly morning alert (#112)
- MCP server (v2 adopted) + extraction repeatability (#113)

**2026-11-15 (Sun)**: 3 changes
- Set D: two-run flag and amount_checks v2 adopted (rule, code, result, wiring) (#114)
- smtp-mcp adopted: registry MCP server for desk e-mail with human approval (#115)
- Source sentence on panel cards and the chat card (verbatim, amount marked) (#116)

## Week of 2026-11-16

**2026-11-16 (Mon)**: 15 changes
- tcmb-mcp: Matriks' rate checked against TCMB (differs, small); gap filling off (#117)
- Capital-increase pilot: design, guideline v0.1, rule (before any pull, label or code) (#118)
- Notes: independent review of #114-#117 (findings only, no code change) (#119)
- Docs: wording after the #114-#117 review (text only; tcmb rule Note 2) (#120)
- Talk plan: ten hardest questions with answers, ten-minute flow (#121)
- Matriks data feedback, one page (Turkish) (#122)
- Feedback doc: previous-day mismatches by currency, negative shfRet recounted on prod (counts only) (#123)
- Talk plan: architecture slide (one-screen diagram, two-minute script) (#124)
- Talk plan: demo pre-mortem and checklist (#125)
- Capital-increase pilot: form reader (multi-column tables) and extraction prompt v1, drafts before the pull (#126)
- Capital-increase pilot: code checks, primary key, combination and scorer (drafts, no data) (#127)
- Forward-test scorer, written from the rule before any outcome exists (#128)
- Capital-increase pilot: collector, counts-only profile and sampler (code only, nothing pulled) (#129)
- Capital-increase pilot: blind labeling tool and F/L/C runner (code only, no data) (#130)
- Runbook: capital-increase pilot day, step by step (21 Nov) (#131)

**2026-11-18 (Wed)**: 16 changes
- Forward test Note 3: no seal for 17 Nov (Mac off), recorded before any outcome (#133)
- Capital-increase pull moved to 18 Nov (window to 17 Nov); rule notes before the pull (#134)
- Capital pilot rule Note 4: long-text threshold 8000 chars from the profile, before sampling (#135)
- Capital guideline v0.2 after the 8 dev texts; frozen for the held-out set (#136)
- Capital pilot dev changes: form reader v2 (tahsis without amount), checks v2 (no decrease word check), C per record; rule Note 5 (#137)
- Capital pilot FREEZE: form reader v3 (withdrawal wording), C recomputes checks on its own values; rule Note 6 (#138)
- Capital scorer: parse Matriks start dates (report-only line crashed before scoring); rule Note 7 (#139)
- Capital-increase pilot result: PILOT_NOT_ADOPTED, LLM_ADDS (held-out 30); results, FAQ, extending, Matriks feedback (#140)
- Talk plan Q1: capital-increase pilot result (code reads the form, LLM cross-checks) (#141)
- DRAFT for Feyza: README summary, Matriks prototype page, system card fix (#132)
- Architecture: capital-increase pilot section (#142)
- Turkish one-page architecture summary (docs/mimari_ozet.md), linked from README (#143)
- Data-vendor auditor: rule, code, M1 and M2 (AUDITOR_OFF) (#145)
- Repository map in README + docs index (no file moves) (#144)
- Architecture docs: data-vendor auditor line (report tool only) (#146)
- Turkish architecture summary: plan to 28 Nov (demo mode, kap-kart, sealed forward test, freeze, not added) (#148)

**2026-11-19 (Thu)**: 21 changes
- Demo mode: hide Matriks-licensed values on panel pages (display flag) (#147)
- kap-kart: card from pasted KAP text (rule, code, measurement 1) (#149)
- README top (problem, solution, proof, run) + demo-mode screenshots (#150)
- Panel: no DB read in the nightly window (known_issues C6) (#151)
- Scope guard v3: separate judge on content paths -> SCOPE_V3_OFF (#152)
- FDV pilot: rule, guideline v0.1, forward-test Note 5, Saturday tooling (#153)
- fdv_collect --load: clear stop when nothing is pulled yet (#154)
- UI polish 1/2: headings, green reviewed badge, Turkish review time, origin wording (#155)
- Record demo leak re-check after UI polish (LEAKS=0) (#156)
- FDV pull moved to Thu 19 Nov (rule Note 1, forward-test Note 6, window to 18 Nov) (#157)
- FDV pilot: readers v1 (form, prompt, checks), runner, scorer; rule Note 2 (pull + profile) (#158)
- UI polish 2/2: [gizli] tag, Önce bak box, card anchors, larger charts (#159)
- FDV dev run 1 -> form reader v2, prompt v2, guideline v0.2 (rule Note 3) (#160)
- FDV pilot FREEZE after dev run 2 (rule Note 4): prompt v2, form v2, checks v1 (#161)
- Independent review fixes: vendor-vs-system table, how to read numbers, three layers, wording, known issues D1-D5 (#162)
- Reviewer guide (10 minutes), key-decisions index at the top of the notes, submission checklist (#163)
- End-to-end check of the nightly chain on synthetic data (fake model only) (#164)
- Record the Ollama ID of gemma4:e4b (#165)
- FDV pilot result: PILOT_NOT_ADOPTED (C 2/30 silent, 6/30 flagged), LLM_ADDS (#166)
- Forward test ends with the 20 Nov list (rule Note 7); score Tue 24 Nov (#167)
- Public copy: how it is built (history kept, internal parts removed) and the checks (#168)

