'''Nightly morning list: called by daily_collect.py right after a successful collection.

Runs morning.py for the day in a subprocess and sends a counts-only alert (no symbols,
no amounts: ntfy is an external service). It never raises, so a failed list cannot turn a
successful collection into a failure; a failed list gets its own FAILED alert.

Usage (manual test, prints the alert instead of sending it):
  python scripts/morning_job.py --date 2026-11-06
  python scripts/morning_job.py --self-test
'''
import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta

SUMMARY_RE=re.compile(r'disclosures=(\d+) look_first=(\d+) flagged=(\d+) run_errors=(\d+)')
TIMEOUT=1800  # seconds; a busy day is about 3 min (docs/latency.md)


def list_day(now):
    '''The day to list: today for the normal 23:43 run; yesterday if launchd ran it after midnight (wake from sleep).'''
    return (now.date() if now.hour>=12 else now.date()-timedelta(days=1)).isoformat()


def summary(stdout):
    m=None
    for m in SUMMARY_RE.finditer(stdout or ''):
        pass
    if not m:
        return None
    return dict(zip(('disclosures','look_first','flagged','run_errors'),map(int,m.groups())))


def message(day,s):
    if s['disclosures']==0:
        return f'{day}: yeni bildirim yok'
    msg=f'{day}: {s["disclosures"]} bildirim, önce bak {s["look_first"]}, kontrol et {s["flagged"]}'
    if s['run_errors']:
        msg+=f', LLM hatası {s["run_errors"]} (Ollama açık mı?)'
    return msg


def last_error(stderr):
    '''Last meaningful stderr line (the exception), skipping ^^^ marker lines.'''
    lines=[l.strip() for l in (stderr or '').splitlines() if set(l.strip())-set('^~ ')]
    return lines[-1][:300] if lines else 'no stderr'


def run(day,notify,runner=subprocess.run):
    '''Build the morning list for day and send one alert. Returns True on success; never raises.'''
    try:
        r=runner([sys.executable,'scripts/morning.py','--date',day,'--allow-window'],
                 capture_output=True,text=True,timeout=TIMEOUT)
        if r.returncode!=0:
            notify('KAP morning FAILED',f'{day}: {last_error(r.stderr)}','high')
            return False
        s=summary(r.stdout)
        if s is None:
            notify('KAP morning FAILED',f'{day}: no summary line','high')
            return False
        notify('KAP morning list',message(day,s),'high' if s['run_errors'] else 'default')
        return True
    except Exception as e:
        notify('KAP morning FAILED',f'{day}: {type(e).__name__}','high')
        return False


def _self_test():
    assert list_day(datetime(2026,11,9,23,45))=='2026-11-09'
    assert list_day(datetime(2026,11,10,0,20))=='2026-11-09'
    assert list_day(datetime(2026,11,10,13,0))=='2026-11-10'
    out='doc vectors...\ndisclosures=3 look_first=1 flagged=1 run_errors=0 -> data/morning_2026-11-09.md\n'
    s=summary(out)
    assert s=={'disclosures':3,'look_first':1,'flagged':1,'run_errors':0} and summary('nothing') is None
    assert message('2026-11-09',s)=='2026-11-09: 3 bildirim, önce bak 1, kontrol et 1'
    assert message('2026-11-08',{**s,'disclosures':0})=='2026-11-08: yeni bildirim yok'
    assert 'LLM hatası 2' in message('d',{**s,'run_errors':2})

    class R:
        def __init__(self,code,out='',err=''):
            self.returncode,self.stdout,self.stderr=code,out,err
    sent=[]
    note=lambda t,m,p='default':sent.append((t,m,p))
    assert run('2026-11-09',note,runner=lambda *a,**k:R(0,out)) and sent[-1]==('KAP morning list','2026-11-09: 3 bildirim, önce bak 1, kontrol et 1','default')
    assert not run('d',note,runner=lambda *a,**k:R(1,err='Traceback\n  x\n  ^^^\nValueError: bad\n')) and sent[-1][1]=='d: ValueError: bad'
    assert not run('d',note,runner=lambda *a,**k:R(0,'no line')) and sent[-1][1]=='d: no summary line'
    def boom(*a,**k):
        raise subprocess.TimeoutExpired('x',1)
    assert not run('d',note,runner=boom) and sent[-1]==('KAP morning FAILED','d: TimeoutExpired','high')
    assert run('d',note,runner=lambda *a,**k:R(0,out.replace('run_errors=0','run_errors=2'))) and sent[-1][2]=='high'
    print('self-test ok: 13 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--date')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    day=args.date or list_day(datetime.now())
    ok=run(day,lambda t,m,p='default':print(f'[alert, not sent] {t}: {m}'))
    sys.exit(0 if ok else 1)


if __name__=='__main__':
    main()
