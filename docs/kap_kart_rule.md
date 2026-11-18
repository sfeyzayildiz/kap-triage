# kap-kart: rule (written before code, 19 Nov 2026)

## Why
When the Matriks permission ends, the live system stops. `kap-kart` is the one part that runs without Matriks data: a person pastes the text of a public "Yeni İş İlişkisi" disclosure (copied from kap.org.tr) and gets the same card the nightly job builds: amount, currency, revision, source sentence with the amount marked, and a KONTROL ET warning with reasons. It lets anyone (instructor, a company, a recruiter) try the system on their own input, which our private, licensed system cannot offer.

It is a **copy of the measured extraction path, not a new system**. It changes nothing on the nightly path (forward test sealed to 25 Nov, freeze 26 Nov).

## What it is
- Folder `kap_kart/` in this repo (private). Everything that may ever go public lives in this folder and nowhere else.
- **Byte-copies, not imports** (decided here): a public repo cannot import from a private one, and `pipeline.py` imports `duckdb`, `matriks_crosscheck` and `eval_vs_matriks`. Copied unchanged into `kap_kart/frozen/`: `llm_extract.py`, `amount_checks.py` (frozen), `amount_checks_v2.py`, `currency_check.py`, `source_check.py`; into `kap_kart/prompts/`: `extract_v3.txt` (frozen). `kap_kart/MANIFEST.sha256` lists their sha256.
- New code, `kap_kart/kap_kart.py` only: the same composition as the nightly path without Matriks: extraction (v3, `gemma4:e4b`, thinking on, temperature 0, num_ctx 8192) → code checks (`currency_unclear`, `amount_is_projection`, `cumulative_total`) → second run (`two_run_disagree`, ADOPT_TWO_RUN) → source-sentence judge (`amount_not_in_text`, `amount_from_instruction`, `judge_error`) with **no cache file** (`CachedJudge(path=None)`), so pasted text is never written to disk. Failures come back as `run_error`, never dropped.
- **Not in kap-kart (needs Matriks):** layer 1 cross-check (`amount_vs_matriks`), importance score and level, revenue ratio, FX rate / TL equivalent, sector desk, prices. The card says "Matriks çapraz kontrolü ve önem skoru bu sürümde yok".
- Interfaces: CLI (`python kap_kart.py metin.txt` or stdin) and a small paste page (`--serve`, bound to 127.0.0.1 only, no external scripts or fonts, CSP as in the panel, pasted text HTML-escaped, input capped at 30,000 characters). An optional KAP link field is shown only if it starts with `https://www.kap.org.tr/`; it is never fetched. The only network call is to the local Ollama.
- Four synthetic trap examples in `kap_kart/examples/`, written by Claude, not taken from any disclosure: (1) clean, (2) currency unclear, (3) revision, (4) hidden instruction (injection). Their expected behaviour is fixed below, before any run.
- `run.sh` launcher (macOS/Linux): checks Python, that Ollama answers and that `gemma4:e4b` is present (prints the `ollama pull` command if not; never pulls by itself), then starts the paste page. `requirements.txt` pinned to the versions this repo uses. `LICENSE` (MIT, Feyza Yıldız 2026). README (English, Turkish quick start) with a "No data included" section and the stated limits.

## How it is measured
1. **Synthetic (self-test, CI; Claude):**
   a. Every copied file is byte-identical to its source in `scripts/` / `prompts/` (sha256) and matches `MANIFEST.sha256`. Differences: **0**.
   b. Composition equivalence: on synthetic texts with a fake extractor and a fake judge covering every reason code, kap-kart's reasons and values equal `pipeline.analyze` (matriks=None) + `two_run_check` + `judge_pass`. Differences: **0**.
   c. No network except Ollama: building a card with the fakes opens no socket; the paste page binds to 127.0.0.1. Count of other connections: **0**.
   d. Escaping: a pasted `<script>` / HTML tag appears escaped in the page. Raw tags: **0**.
   e. The Turkish reason table covers every code the copied code can produce (model `ReviewReason` + code checks + layer 2 + `run_error` + `two_run_disagree`). Missing: **0**.
   f. `kap_kart/` imports nothing outside its folder except the standard library, `ollama`, `pydantic`, `python-dotenv` (no `duckdb`, no Matriks module is reachable). Violations: **0**.
   (b) runs in this repo only (it needs `pipeline.py`); (a, c-f) also run inside the folder alone (`kap_kart.py --self-test`).
2. **Leak scan (Feyza runs, counts only):** `scripts/kap_kart_leak_scan.py` prints:
   - files in `kap_kart/` not in the allowlist (code, prompt, examples, README, LICENSE, manifest, requirements, launcher): **0**; no `.duckdb`, `.jsonl`, `.env`, `.gz`, `.parquet` anywhere;
   - forbidden patterns: Matriks API hosts/paths (`new-business-api`, the base URLs in our collector), `KAP_TOKEN`, IPv4 addresses other than 127.0.0.1, e-mail addresses, `/Users/`, `kap-deploy`, the server alias: **0**;
   - text overlap with the corpus: 12-word shingles of every file in `kap_kart/` against every `disclosures.aciklama`: **0** shared shingles. On a hit it prints only the count and our own file:line, never the disclosure.
3. **Trap examples (Feyza runs, local Ollama):** each example 3 times = 12 cards. Expected:
   - clean: amount and currency as written, no flag;
   - currency unclear: `currency_unclear` among the reasons (KONTROL ET shown);
   - revision: `is_revision` true, amount = the new amount, `previous_amount` = the old one;
   - hidden instruction: the instruction's amount never appears without KONTROL ET (either the real amount, or a flag from layer 2).
   Reported as X/12 plus latency per card (first card separately, then median and max). This is a demo check, not a new reliability number (the code's reliability is the one measured on Sets B/C/D, with layer 1 on). **A failing example is not rewritten after the first run**: it stays, README states what happened, and we say it in the demo.
4. **Visual check (Feyza):** `run.sh`, one text she copies herself from kap.org.tr into the paste page, and the four examples. She does not paste the text into Claude.

## Amendment 1 (19 Nov, with the code, before any measurement; nothing has been run on real data or with the model)
Found while writing the code; needs Feyza's approval before she runs measurements 2-4.
1. **Two dead imports in a byte-copy.** `frozen/source_check.py` imports `matriks_crosscheck` and `score_silent` inside `false_alarms()` (a dev-time report). The file cannot be edited (byte-copy), and neither module is in the folder. Check (1f) therefore allows exactly these two imports inside that one function, and also checks that `kap_kart.py` never calls `false_alarms` and that no vendor module (`duckdb`, `matriks_crosscheck`, `eval_vs_matriks`, `pipeline`) is loaded after a card is built.
2. **Leak scan skips `__pycache__/`, `.DS_Store` and `.venv/`** (created by Python, macOS and `run.sh` when the folder is used); `kap_kart/.gitignore` excludes them and the export takes git-tracked files only. `.gitignore` is on the allowlist. The scan also refuses to run in the nightly window (23:35-00:10) because it reads the DB.
3. **Composition details made explicit:** the two-run comparison uses a copy of `eval_vs_matriks.norm_cur`'s currency map (not the module), and the Turkish reason texts are those of `morning.REVIEW_TR` without `amount_vs_matriks`; both are checked against the source in `scripts/kap_kart_check.py` (26 synthetic cases cover all 16 codes).
4. **Synthetic results (measurement 1, Claude, 19 Nov):** copies 6/6 identical; equivalence diffs 0 of 26; sockets 0; raw tags 0; missing texts 0; import violations 0. Self-tests 78 ok / 1 skip.

Approved by Feyza 19 Nov.

## Round 1 of measurements 2-4 (Feyza, 19 Nov)
- (2) leak scan: `files=0 pattern=0 overlap=2 -> FAIL`. Both shingles on `frozen/amount_checks_v2.py:64`, a sentence inside that module's `_self_test()` (written 15 Nov from a real disclosure fragment). Not used at run time.
- (3) trap examples: **12/12**; first card 21.6 s, then median 27.0 s, max 31.5 s.
- (4) visual check: clean (four examples; one real disclosure she copied from kap.org.tr had no amount, the card said "metinde tutar bulunamadı", nothing invented).

## Amendment 2 (19 Nov, after round 1; fix for the leak)
The leak is fixed at the source instead of stripping the copy, so the copies stay byte-identical: the sentence in `scripts/amount_checks_v2.py` `_self_test()` is replaced by a synthetic one, and the copy and manifest are refreshed. This is an exception to "no nightly-path file changes": only the self-test changed; the module's code outside `_self_test` is AST-identical to before (checked), so nightly results cannot change and kap-deploy needs no pull. Round 2: re-run (1), (2), (4) as the rule says; the result is reported with 2 rounds.

## Round 2 (Feyza, 19 Nov, on eda83ce)
- (2) leak scan: `files=0 pattern=0 overlap=1 -> FAIL`, at `frozen/amount_checks.py:123`: the same real fragment in the v1 module's `_self_test()`. Correction to round 1: its `overlap=2` was most likely one hit here and one in `amount_checks_v2.py:64` (only one location line was pasted; the scan prints one line per file:line).

## Amendment 3 (19 Nov, after round 2)
`scripts/amount_checks.py` is frozen (CLAUDE.md) and cannot be edited. Its copy in `kap_kart/frozen/` is therefore the source **cut before `def _self_test():`** (114 of 144 lines; all code kept, the test and the `__main__` call left out). Check (1a) for this one file compares the copy with that deterministic cut of the source (`scripts/kap_kart_check.py`, `STRIPPED`); the other five copies stay byte-identical. The frozen source is unchanged. Round 3: Feyza re-runs (2); (1) is 0 again; (4) is not repeated because the code path is unchanged (the cut part never runs in a card).
- (4) visual check: clean (`1_temiz` card, 2.750.000 USD).

## Round 3 (Feyza, 19 Nov, on 6435c58)
- (2) leak scan: `scanned 17 files against 1296 disclosure texts`, `files=0 pattern=0 overlap=0`, `LEAKS=0 -> pass`.

## Result (19 Nov 2026)
**ADOPT_KAP_KART, round 3** (private). (1) synthetic all 0; (2) leaks 0 in round 3 (round 1: 2, round 2: 1, both a real fragment in a copied module's self-test; fixed by Amendments 2 and 3); (3) examples 12/12, first card 21.6 s, then median 27.0 s, max 31.5 s; (4) visual check clean (rounds 1 and 2). Public only after the Matriks reply and Feyza's go.

## Decision
- **ADOPT_KAP_KART** (private, usable in the demo and the video) if (1) all six synthetic counts are 0, (2) the leak scan is 0 on all three counts, and (4) the visual check is clean. (3) is reported with its number in README and `results.md` whatever it is.
- Any leak in (2) or (4): fix, re-run all of (1), (2), (4); the result is reported with the number of rounds.
- **Public** only after Matriks replies and Feyza says go: a new repo built from the `kap_kart/` folder with a fresh history (no history from this repo), the leak scan re-run on the exported folder first. Until then the folder stays in this private repo.
- No nightly-path file changes; no kap-deploy pull needed. If a frozen source file ever changes, check (1a) fails until the copy is refreshed on purpose.
