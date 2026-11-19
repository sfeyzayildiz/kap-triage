# Making the public copy (history kept, internal parts removed)

The private repository stays the working copy (full history, internal notes, vendor-facing documents). The public copy for GitHub / LinkedIn (and the link for the instructor) is built from it with `git filter-repo`. Matriks agreed on 19 Nov (reply in the same e-mail thread: described use with vendor values hidden is fine).

## What the rewrite does (every commit, not only the last one)
- Removes three files from all commits: `CLAUDE.md` (the assistant's working rules, server details), `docs/matriks_feedback.md` and `docs/matriks_prototype.md` (written for the vendor).
- Replaces the server IP, the hosting company's name, the server alias, the home-folder path, the Matriks contact person's name (→ "Matriks yetkilisi") and the Matriks API host names (→ `<MATRIKS_API_HOST>`), in file contents and in commit messages (the patterns live in `~/projects/kap-public-tools/replacements.txt`, outside the repo, so they are never committed). The Matriks documentation portal address is not an API host and stays.
- Maps the commit e-mail to the GitHub no-reply address (`~/projects/kap-public-tools/mailmap.txt`).
- Drops compiled files (`*.pyc`, `__pycache__/`) that slipped into early commits.
- Adds one commit with a README note: history rewritten, commit IDs differ from the ones in `PROJECT_NOTES.md`, no licensed data.

## Checks before publishing (all must be 0; the counts are shown to Feyza before the push)
`python3 ~/projects/kap-public-tools/check_public.py ~/projects/kap-public` searches every version of every file, every commit message and the author fields, and prints labels and counts only:
- server IP 0, hosting name 0, server alias 0, home path 0, personal e-mail 0
- **person name (Matriks contact) 0**
- **Matriks API host 0**
- token-like strings 0, removed files 0, `data/` files 0, compiled files 0

Also:
- All self-tests pass inside the cleaned copy (`~/projects/kap-explore/.venv/bin/python scripts/run_self_tests.py --skip daily_collect`, run in `kap-public`).
- kap-kart leak scan on the copy's folder, run by Feyza (`docs/kap_kart_rule.md`, Note 1): all three counts 0.
- Vendor record amounts (first build, 19 Nov: 625 non-round values from `new_business` found only in self-test sentences that come from public KAP disclosure texts, allowed). This check reads the database and is not part of the script.
- First build (19 Nov): all counts 0, 86 self-tests passed, 1 skipped; 26 Oct - 19 Nov 2026, 164 commits.

## Rebuild after the last commit (before publishing)
`git filter-repo` 2.47.0 is installed in `~/projects/kap-public-tools/frvenv`.
```
cd ~/projects && rm -rf kap-public
git clone --no-local --single-branch --branch main ~/projects/kap-explore kap-public
cd kap-public
FR=~/projects/kap-public-tools/frvenv/bin/git-filter-repo
$FR --force --invert-paths --path CLAUDE.md --path docs/matriks_feedback.md --path docs/matriks_prototype.md \
  --replace-text ~/projects/kap-public-tools/replacements.txt --replace-message ~/projects/kap-public-tools/replacements.txt \
  --mailmap ~/projects/kap-public-tools/mailmap.txt
$FR --force --invert-paths --path-glob '*.pyc' --path-glob '*/__pycache__/*'
python3 ~/projects/kap-public-tools/check_public.py ~/projects/kap-public
```
Then the self-tests and the kap-kart leak scan above, add the README note, show the counts to Feyza, and only after her "aç" and the repository name: create an empty public GitHub repository and push `main`. On submission day (Tue 24 Nov) this is done by about 15:00 (`docs/runbook.md`, "Submission day").
