'''One Matriks pull per day, enforced in code.

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

Self-test: `python scripts/pull_guard.py --self-test` (temp files only).
'''
import os
import sys
import tempfile
from datetime import date, datetime

MARKER='data/last_pull.txt'
LOG='data/pull_log.txt'


class AlreadyPulled(Exception):
    pass


def read_marker(path=MARKER):
    '''(date, kind, time) of the last claim, or None when there is no readable marker.'''
    try:
        with open(path,encoding='utf-8') as f:
            parts=f.read().split()
        return date.fromisoformat(parts[0]),parts[1],parts[2]
    except (OSError,ValueError,IndexError):
        return None


def pulled_today(today=None,path=MARKER):
    '''Kind of today's pull, or None.'''
    m=read_marker(path)
    today=today or date.today()
    return m[1] if m and m[0]==today else None


def claim(kind,resume=False,after=(),today=None,now=None,path=MARKER,log=LOG):
    '''Record that `kind` is about to pull today, or raise AlreadyPulled.'''
    today=today or date.today()
    done=pulled_today(today,path)
    if done and not ((resume and done==kind) or done in after):
        raise AlreadyPulled(f'already pulled today ({done}); the rule is one pull per day. '
                            f'If this is really intended, delete {path} first.')
    stamp=(now or datetime.now()).strftime('%H:%M')
    line=f'{today.isoformat()} {kind} {stamp}\n'
    os.makedirs(os.path.dirname(path) or '.',exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        f.write(line)
    with open(log,'a',encoding='utf-8') as f:
        f.write(line)
    return done


def _self_test():
    d1,d2=date(2026,11,11),date(2026,11,12)
    with tempfile.TemporaryDirectory() as tmp:
        p,l=os.path.join(tmp,'m.txt'),os.path.join(tmp,'l.txt')
        assert read_marker(p) is None and pulled_today(d1,p) is None
        assert claim('prices',today=d1,path=p,log=l) is None
        assert pulled_today(d1,p)=='prices' and pulled_today(d2,p) is None
        for kind,kw in (('collector',{}),('prices',{}),('prod_refresh',{'after':('sectors',)})):
            try:
                claim(kind,today=d1,path=p,log=l,**kw)
                raise AssertionError('must refuse')
            except AlreadyPulled as e:
                assert 'prices' in str(e) and p in str(e)
        assert claim('prices',resume=True,today=d1,path=p,log=l)=='prices'   # resumable same-kind session
        assert claim('sectors',after=('prices',),today=d1,path=p,log=l)=='prices'   # same approved session
        assert pulled_today(d1,p)=='sectors'
        assert claim('collector',today=d2,path=p,log=l) is None   # next day is free
        with open(l,encoding='utf-8') as f:
            lines=f.read().splitlines()
        assert len(lines)==4 and lines[-1].startswith('2026-11-12 collector ')
        with open(p,'w',encoding='utf-8') as f:
            f.write('garbage')
        assert read_marker(p) is None and claim('collector',today=d1,path=p,log=l) is None   # unreadable marker = none
    print('self-test ok: 12 checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
    else:
        m=read_marker()
        print('no marker' if m is None else f'last pull {m[0]} {m[1]} {m[2]}; today={"yes" if pulled_today() else "no"}')
