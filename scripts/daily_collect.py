import os
import time
import subprocess
import sys
from datetime import date,timedelta

import duckdb
import requests
from dotenv import load_dotenv

load_dotenv()

DB='data/kap.duckdb'
# re-fetch the last few days: catches late disclosures,
# INSERT OR REPLACE in collector.py keeps this idempotent
LOOKBACK_DAYS=3
LOCK_RETRIES=3
LOCK_WAIT=int(os.environ.get('LOCK_WAIT','300'))   # seconds between attempts
NTFY_URL=os.environ.get('NTFY_URL')


def counts():
    con=duckdb.connect(DB,read_only=True)
    nb=con.execute('SELECT count(*) FROM new_business').fetchall()[0][0]
    d=con.execute('SELECT count(*) FROM disclosures').fetchall()[0][0]
    con.close()
    return nb,d


def notify(title,msg,priority='default'):
    print(f'{title}: {msg}')
    if not NTFY_URL:
        return
    # HTTP headers must be ASCII, so keep titles in plain English
    requests.post(
        NTFY_URL,
        data=msg.encode('utf-8'),
        headers={'Title':title,'Priority':priority},
        timeout=10,
    )
def retry_on_lock(fn):
    '''Call fn(); if it fails because another process holds the DB lock, wait and try again.'''
    for attempt in range(1,LOCK_RETRIES+1):
        try:
            return fn()
        except Exception as e:
            if 'could not set lock' not in str(e).lower() or attempt==LOCK_RETRIES:
                raise
            print(f'DB locked (attempt {attempt}/{LOCK_RETRIES}), retrying in {LOCK_WAIT}s',flush=True)
            time.sleep(LOCK_WAIT)


def run_collector(start,end):
    r=subprocess.run(
        [sys.executable,'scripts/collector.py','--start',start.isoformat(),'--end',end.isoformat()],
        capture_output=True,
        text=True,
    )
    if r.returncode!=0:
        raise RuntimeError(r.stderr[-500:] or 'no stderr')

def main():
    end=date.today()
    start=end-timedelta(days=LOOKBACK_DAYS)
    before=retry_on_lock(counts)
    retry_on_lock(lambda:run_collector(start,end))
    after=retry_on_lock(counts)
    msg=f'{start}..{end}: +{after[0]-before[0]} new_business, +{after[1]-before[1]} disclosures'
    notify('KAP collector OK',msg)


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        notify('KAP collector FAILED',str(e)[-500:],'high')
        raise   # keep the traceback in daily.log and a non-zero exit code