# Making the public copy (history kept, internal parts removed)

The private repository stays the working copy (full history, internal notes, vendor-facing documents); the instructor gets read access to it. The public copy for GitHub / LinkedIn is built from it with `git filter-repo`, **only after Matriks agrees** (e-mail of 19 Nov).

## What the rewrite does (every commit, not only the last one)
- Removes three files from all commits: `CLAUDE.md` (the assistant's working rules, server details), `docs/matriks_feedback.md` and `docs/matriks_prototype.md` (written for the vendor).
- Replaces the server IP, the hosting company's name, the server alias and the home-folder path (the patterns live in `~/projects/kap-public-tools/replacements.txt`, outside the repo, so they are never committed).
- Maps the commit e-mail to the GitHub no-reply address (`~/projects/kap-public-tools/mailmap.txt`).
- Drops compiled files (`*.pyc`, `__pycache__/`) that slipped into early commits.
- Adds one commit with a README note: history rewritten, commit IDs differ from the ones in `PROJECT_NOTES.md`, no licensed data.

## Checks before publishing (19 Nov, first build: all passed)
- Full history, every version of every file: server IP 0, hosting name 0, server alias 0, personal e-mail 0, home path 0, token-like strings 0, removed files 0, `data/` files 0, compiled files 0.
- Vendor record amounts (625 non-round values from `new_business`) found only in self-test sentences that come from public KAP disclosure texts (allowed: KAP text is public).
- All self-tests pass inside the cleaned copy (86 passed, 1 skipped).
- Dates kept: 26 Oct - 19 Nov 2026, 164 commits.

## Rebuild after the last commit (before publishing)
```
cd ~/projects && rm -rf kap-public
git clone --no-local --single-branch --branch main ~/projects/kap-explore kap-public
cd kap-public
git filter-repo --force --invert-paths --path CLAUDE.md --path docs/matriks_feedback.md --path docs/matriks_prototype.md \
  --replace-text ~/projects/kap-public-tools/replacements.txt --mailmap ~/projects/kap-public-tools/mailmap.txt
git filter-repo --force --invert-paths --path-glob '*.pyc' --path-glob '*/__pycache__/*'
```
Then re-run the checks above, add the README note, create an empty public GitHub repository and push `main`.
