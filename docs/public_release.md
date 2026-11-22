# Making the public copy (history kept, internal parts removed)

The private repository stays the working copy (full history, internal notes, vendor-facing documents). The public copy for GitHub / LinkedIn (and the link for the instructor) is built from it with `git filter-repo`. Matriks agreed on 19 Nov (reply in the same e-mail thread: described use with vendor values hidden is fine).

## What the rewrite does (every commit, not only the last one)
- Removes six files from all commits: `CLAUDE.md` (the assistant's working rules, server details), `docs/matriks_feedback.md` and `docs/matriks_prototype.md` (written for the vendor), `docs/talk_plan.md` and `docs/demo_script.md` (old internal plans for the talk and the demo, superseded), `docs/mimari_ozet.md` (Turkish summary for a gist that was never sent; the public copy is English only). The last three were added on 21 Nov.
- Removes the measurement scripts from all commits: `experiments/`, the same 63 files under their earlier `scripts/` paths, and the two pilots' prompts (`~/projects/kap-public-tools/remove_paths.txt`). Instructor, 21 Nov: as little test code as possible. The rule files stay, each with its bar and its result; `run_self_tests.py` runs the 47 system self-tests when `experiments/` is absent (46 locally, where `daily_collect` is skipped).
- Replaces the server IP, the hosting company's name, the server alias, the home-folder path, the Matriks contact person's name (→ "Matriks yetkilisi") and the Matriks API host names (→ `<MATRIKS_API_HOST>`), in file contents and in commit messages (the patterns live in `~/projects/kap-public-tools/replacements.txt`, outside the repo, so they are never committed). The Matriks documentation portal address is not an API host and stays.
- Maps the commit e-mail to the GitHub no-reply address (`~/projects/kap-public-tools/mailmap.txt`).
- Drops compiled files (`*.pyc`, `__pycache__/`) that slipped into early commits.
- Adds one commit with a README note: history rewritten, commit IDs differ from the ones in `docs/PROJECT_NOTES.md`, no licensed data.

## Checks before publishing (all must be 0; the counts are shown to Feyza before the push)
`python3 ~/projects/kap-public-tools/check_public.py ~/projects/kap-public` searches every version of every file, every commit message and the author fields, and prints labels and counts only:
- server IP 0, hosting name 0, server alias 0, home path 0, personal e-mail 0
- **person name (Matriks contact) 0**
- **Matriks API host 0**
- token-like strings 0, removed files 0, experiment and pilot files 0, `data/` files 0, compiled files 0

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
$FR --force --invert-paths --path CLAUDE.md --path docs/matriks_feedback.md --path docs/matriks_prototype.md --path docs/talk_plan.md --path docs/demo_script.md --path docs/mimari_ozet.md \
  --paths-from-file ~/projects/kap-public-tools/remove_paths.txt \
  --replace-text ~/projects/kap-public-tools/replacements.txt --replace-message ~/projects/kap-public-tools/replacements.txt \
  --mailmap ~/projects/kap-public-tools/mailmap.txt
$FR --force --invert-paths --path-glob '*.pyc' --path-glob '*/__pycache__/*'
python3 ~/projects/kap-public-tools/check_public.py ~/projects/kap-public
```
Then the self-tests and the kap-kart leak scan above, add the README note, show the counts to Feyza.

## Publishing (private first)
The repository `sfeyzayildiz/kap-disclosure-triage` was created **private** on 19 Nov with the trial copy, so the pages can be checked on GitHub before anyone else sees them. On submission day (Tue 24 Nov, by about 15:00; `docs/runbook.md`, "Submission day") the copy is rebuilt as above and replaces it:
```
cd ~/projects/kap-public
git config user.name 'Feyza Yildiz' && git config user.email '192357242+sfeyzayildiz@users.noreply.github.com'
python3 ~/projects/kap-public-tools/add_readme_note.py ~/projects/kap-public   # badges (tests, Python, MIT) + the copy note
git commit -qam 'Public copy: history rewritten, internal parts removed (note at the top of README)'
python3 ~/projects/kap-public-tools/check_public.py ~/projects/kap-public      # all 0 again, shown to Feyza
git remote add origin https://github.com/sfeyzayildiz/kap-disclosure-triage.git
git push --force -u origin main
```
Only after Feyza's "aç": `gh repo edit sfeyzayildiz/kap-disclosure-triage --visibility public --accept-visibility-change-consequences`. Then open the repository in a private browser window (not logged in) and check that the README demo GIF (`docs/img/demo.gif`, added 21 Nov because the attachment player did not show reliably) moves and that the "watch" link of the full video plays, **in both Safari and Chrome**: it was uploaded as a GitHub attachment while the repository was private, and on 20 Nov it did not play in Safari on the private repository (the file itself is standard H.264, yuv420p, faststart). If it does not play, Feyza uploads `kap_demo_v5_github.mp4` again (drag it into a new issue box, do not create the issue) and the README line gets the new link. Then the link goes to the instructor and LinkedIn.
