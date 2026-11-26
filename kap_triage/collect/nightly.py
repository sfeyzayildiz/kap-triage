"""Nightly entry point (launchd, 23:43; deploy/): collect, then build the morning list.

Order in main():
  1. pull_guard: if a vendor pull already happened today, send a SKIPPED alert and stop (one pull per day).
  2. wait until the API hosts resolve (after sleep the network can be late), so a retry is never a second pull.
  3. collector.py for the last LOOKBACK_DAYS days (INSERT OR REPLACE, so re-fetching is safe); DB lock -> wait, retry.
  4. Only OK builds and seals a morning list. PARTIAL and FAILED alert and exit non-zero.

Usage:
  python -m kap_triage.collect.nightly              # the nightly run (calls the vendor API)"""

import os
import re
import socket
import time
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta
import duckdb
import requests
from dotenv import load_dotenv

from kap_triage.collect.collector import CollectionStatus, PRE_PULL_LOCK
from kap_triage.collect.pull_guard import pulled_today
from kap_triage.settings import settings


# --- Collection -----------------------------------------------------------------

load_dotenv()

DB = settings.path('kap.duckdb')
# re-fetch the last few days: catches late disclosures,
# INSERT OR REPLACE in collector.py keeps this idempotent
LOOKBACK_DAYS = 3
LOCK_RETRIES = 6
LOCK_WAIT = int(os.environ.get('LOCK_WAIT', '300'))  # seconds between attempts
NTFY_URL = os.environ.get('NTFY_URL')
FAILURE_HINT = 'See data/daily.log.'
API_HOSTS = ('<MATRIKS_API_HOST>', '<MATRIKS_API_HOST>')  # NB_API and NEWS_API hosts in collector.py
NET_RETRIES = 10
NET_WAIT = 60  # seconds; after wake from sleep Wi-Fi can take a while


def counts():
    con = duckdb.connect(DB, read_only=True)
    nb = con.execute('SELECT count(*) FROM new_business').fetchall()[0][0]
    d = con.execute('SELECT count(*) FROM disclosures').fetchall()[0][0]
    con.close()
    return nb, d


def ts():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def notify(title, msg, priority='default'):
    print(f'[{ts()}] {title}: {msg}', flush=True)
    if not NTFY_URL:
        return
    try:
        # HTTP headers must be ASCII, so keep titles in plain English
        requests.post(
            NTFY_URL,
            data=msg.encode('utf-8'),
            headers={'Title': title, 'Priority': priority},
            timeout=10,
        )
    except requests.RequestException as e:
        # a failed alert must not hide the original error
        print(f'[{ts()}] notify failed: {type(e).__name__}', flush=True)


def wait_for_network(resolve=socket.getaddrinfo, sleep=time.sleep):
    """Wait until the API hosts resolve, before any request is sent (so a retry is never a second pull)."""
    for attempt in range(1, NET_RETRIES + 1):
        try:
            for host in API_HOSTS:
                resolve(host, 443)
            return attempt
        except OSError:
            last = attempt == NET_RETRIES
            print(
                f'[{ts()}] no network (attempt {attempt}/{NET_RETRIES}), '
                + ('giving up' if last else f'retrying in {NET_WAIT}s'),
                flush=True,
            )
            if not last:
                sleep(NET_WAIT)
    raise RuntimeError(f'no network after {NET_RETRIES} attempts')


def lock_holder(message):
    """Command of the process that holds the DB lock, from the PID in DuckDB's error, for the log."""
    m = re.search(r'PID (\d+)', message or '')
    if not m:
        return 'unknown'
    r = subprocess.run(['ps', '-p', m.group(1), '-o', 'etime=,command='], capture_output=True, text=True)
    return f'PID {m.group(1)}: ' + (r.stdout.strip() or 'already gone')


class PrePullLock(RuntimeError):
    """The collector reported a lock failure before any request."""


def retry_on_lock(fn):
    """Call fn(); if it fails because another process holds the DB lock, wait and try again."""
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            if not isinstance(e, PrePullLock) and 'could not set lock' not in str(e).lower():
                raise
            print(f'[{ts()}] DB locked (attempt {attempt}/{LOCK_RETRIES}), held by {lock_holder(str(e))}', flush=True)
            if attempt == LOCK_RETRIES:
                raise
            time.sleep(LOCK_WAIT)


def run_collector(start, end):
    r = subprocess.run(
        [sys.executable, '-m', 'kap_triage.collect.collector', '--start', start.isoformat(), '--end', end.isoformat()],
        capture_output=True,
        text=True,
    )
    # Keep collector diagnostics local. Only a reserved pre-pull lock failure can retry.
    print(r.stdout, end='', flush=True)
    print(r.stderr, end='', file=sys.stderr, flush=True)
    if r.returncode == PRE_PULL_LOCK:
        raise PrePullLock(r.stderr.strip() or 'Collector database is locked')
    if r.returncode == CollectionStatus.OK:
        return CollectionStatus.OK
    if r.returncode == CollectionStatus.PARTIAL:
        return CollectionStatus.PARTIAL
    return CollectionStatus.FAILED


def skip_message(kind, day):
    """Alert text when a pull already happened today (one pull per day, pull_guard)."""
    return f'{day}: already pulled today ({kind}); no second pull, no morning list. Next night fills the gap.'


def collect_and_list():
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    kind = pulled_today()
    if kind:
        notify('KAP collector SKIPPED', skip_message(kind, end))
        return
    wait_for_network()
    before = retry_on_lock(counts)
    status = retry_on_lock(lambda: run_collector(start, end))
    if status == CollectionStatus.PARTIAL:
        notify('KAP collector PARTIAL', FAILURE_HINT, 'high')
        return status
    if status != CollectionStatus.OK:
        raise RuntimeError('Collector subprocess failed')
    after = retry_on_lock(counts)
    msg = f'{start}..{end}: +{after[0] - before[0]} new_business, +{after[1] - before[1]} disclosures'
    notify('KAP collector OK', msg)
    # morning list after a good collection; it sends its own alert and never raises
    run_morning(list_day(datetime.now()), notify)


def main():
    try:
        status = collect_and_list()
    except Exception:
        notify('KAP collector FAILED', FAILURE_HINT, 'high')
        raise  # keep the traceback in daily.log and a non-zero exit code
    if status == CollectionStatus.PARTIAL:
        raise SystemExit(status)


# --- Morning list after the collection (never raises) ---------------------------

SUMMARY_RE = re.compile(r'disclosures=(\d+) look_first=(\d+) flagged=(\d+) run_errors=(\d+)')
TIMEOUT = 1800  # seconds; a busy day is about 3 min (docs/latency.md)


def list_day(now):
    """The day to list: today for the normal 23:43 run; yesterday if launchd ran it after midnight (wake from sleep)."""
    return (now.date() if now.hour >= 12 else now.date() - timedelta(days=1)).isoformat()


def summary(stdout):
    m = None
    for m in SUMMARY_RE.finditer(stdout or ''):
        pass
    if not m:
        return None
    return dict(zip(('disclosures', 'look_first', 'flagged', 'run_errors'), map(int, m.groups())))


def message(day, s):
    if s['disclosures'] == 0:
        return f'{day}: yeni bildirim yok'
    msg = f'{day}: {s["disclosures"]} bildirim, önce bak {s["look_first"]}, kontrol et {s["flagged"]}'
    if s['run_errors']:
        msg += f', LLM hatası {s["run_errors"]} (Ollama açık mı?)'
    return msg


def run_morning(day, notify, runner=subprocess.run, sealer=None):
    """Build the morning list for day and send one alert. Returns True on success; never raises.
    sealer: docs/forward_test_rule.md, seals the saved list and returns the alert suffix (default forward_seal.seal_day)."""
    if sealer is None:
        from kap_triage.collect.seal import seal_day as sealer
    try:
        r = runner(
            [sys.executable, '-m', 'kap_triage.analysis.morning', '--date', day, '--allow-window'],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        if r.returncode != 0:
            print(f'Morning list exited with status {r.returncode}\n{r.stderr}', file=sys.stderr, flush=True)
            notify('KAP morning FAILED', f'{day}: {FAILURE_HINT}', 'high')
            return False
        s = summary(r.stdout)
        if s is None:
            notify('KAP morning FAILED', f'{day}: no summary line', 'high')
            return False
        notify('KAP morning list', message(day, s) + sealer(day), 'high' if s['run_errors'] else 'default')
        return True
    except Exception:
        traceback.print_exc()
        notify('KAP morning FAILED', f'{day}: {FAILURE_HINT}', 'high')
        return False


if __name__ == '__main__':
    main()
