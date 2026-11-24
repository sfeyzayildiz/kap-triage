"""One Matriks pull per day, enforced in code.

PROJECT_NOTES rule: at most one pull per day (Matriks, 28 Oct 2026). It was broken by hand
twice (10 and 11 Nov 2026: a one-off pull at noon, then the nightly job reloaded the same day).
A rule that lives in people's memory fails; this module keeps it in a marker file.

Every script that sends a request to Matriks calls `claim(kind)` right before its first request.
The marker `data/last_pull.txt` holds one line, `YYYY-MM-DD kind HH:MM`; `data/pull_log.txt`
keeps every claim. kap-deploy's `data/` is a symlink to the dev folder, so both clones share it.

- Same kind again on the same day: refused, unless the caller passes `resume=True`
  (the price pull is resumable by manifest, so a re-run after a failure is the same session).
- A kind listed in `after`: allowed after that kind on the same day (sectors follow prices
  in the same approved session).
- Everything else: `AlreadyPulled`. The conscious override is to delete the marker file;
  the error message says so, nothing does it for you.

"""

import os
from datetime import date, datetime
from kap_triage.settings import settings

MARKER = settings.path('last_pull.txt')
LOG = settings.path('pull_log.txt')


class AlreadyPulled(Exception):
    pass


def read_marker(path=MARKER):
    """(date, kind, time) of the last claim, or None when there is no readable marker."""
    try:
        with open(path, encoding='utf-8') as f:
            parts = f.read().split()
        return date.fromisoformat(parts[0]), parts[1], parts[2]
    except (OSError, ValueError, IndexError):
        return None


def pulled_today(today=None, path=MARKER):
    """Kind of today's pull, or None."""
    m = read_marker(path)
    today = today or date.today()
    return m[1] if m and m[0] == today else None


def claim(kind, resume=False, after=(), today=None, now=None, path=MARKER, log=LOG):
    """Record that `kind` is about to pull today, or raise AlreadyPulled."""
    today = today or date.today()
    done = pulled_today(today, path)
    if done and not ((resume and done == kind) or done in after):
        raise AlreadyPulled(
            f'already pulled today ({done}); the rule is one pull per day. '
            f'If this is really intended, delete {path} first.'
        )
    stamp = (now or datetime.now()).strftime('%H:%M')
    line = f'{today.isoformat()} {kind} {stamp}\n'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(line)
    with open(log, 'a', encoding='utf-8') as f:
        f.write(line)
    return done


if __name__ == '__main__':
    m = read_marker()
    print('no marker' if m is None else f'last pull {m[0]} {m[1]} {m[2]}; today={"yes" if pulled_today() else "no"}')
