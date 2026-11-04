import os
import socket
import time
import subprocess
import sys
from datetime import date,datetime,timedelta

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
API_HOSTS=('<MATRIKS_API_HOST>','<MATRIKS_API_HOST>')  # NB_API and NEWS_API hosts in collector.py
NET_RETRIES=10
NET_WAIT=60   # seconds; after wake from sleep Wi-Fi can take a while


def counts():
    con=duckdb.connect(DB,read_only=True)
    nb=con.execute('SELECT count(*) FROM new_business').fetchall()[0][0]
    d=con.execute('SELECT count(*) FROM disclosures').fetchall()[0][0]
    con.close()
    return nb,d

def ts():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def notify(title,msg,priority='default'):
    print(f'[{ts()}] {title}: {msg}',flush=True)
    if not NTFY_URL:
        return
    try:
        # HTTP headers must be ASCII, so keep titles in plain English
        requests.post(
            NTFY_URL,
            data=msg.encode('utf-8'),
            headers={'Title':title,'Priority':priority},
            timeout=10,
        )
    except requests.RequestException as e:
        # a failed alert must not hide the original error
        print(f'[{ts()}] notify failed: {type(e).__name__}',flush=True)


def wait_for_network(resolve=socket.getaddrinfo,sleep=time.sleep):
    '''Wait until the API hosts resolve, before any request is sent (so a retry is never a second pull).'''
    for attempt in range(1,NET_RETRIES+1):
        try:
            for host in API_HOSTS:
                resolve(host,443)
            return attempt
        except OSError:
            last=attempt==NET_RETRIES
            print(f'[{ts()}] no network (attempt {attempt}/{NET_RETRIES}), '+('giving up' if last else f'retrying in {NET_WAIT}s'),flush=True)
            if not last:
                sleep(NET_WAIT)
    raise RuntimeError(f'no network after {NET_RETRIES} attempts')
def retry_on_lock(fn):
    '''Call fn(); if it fails because another process holds the DB lock, wait and try again.'''
    for attempt in range(1,LOCK_RETRIES+1):
        try:
            return fn()
        except Exception as e:
            if 'could not set lock' not in str(e).lower() or attempt==LOCK_RETRIES:
                raise
            print(f'[{ts()}] DB locked (attempt {attempt}/{LOCK_RETRIES}), retrying in {LOCK_WAIT}s',flush=True)
            time.sleep(LOCK_WAIT)


def run_collector(start,end):
    r=subprocess.run(
        [sys.executable,'scripts/collector.py','--start',start.isoformat(),'--end',end.isoformat()],
        capture_output=True,
        text=True,
    )
    if r.returncode!=0:
        raise RuntimeError(r.stderr[-500:] or 'no stderr')

def _self_test():
    calls=[]
    def flaky(host,port):
        calls.append(host)
        if len(calls)<3:
            raise socket.gaierror('down')
    assert wait_for_network(flaky,sleep=lambda s:None)==3 and calls==[API_HOSTS[0]]*3+[API_HOSTS[1]]
    def down(host,port):
        raise socket.gaierror('down')
    try:
        wait_for_network(down,sleep=lambda s:None)
        raise AssertionError('must raise')
    except RuntimeError:
        pass
    print('self-test ok: 2 checks')


def main():
    end=date.today()
    start=end-timedelta(days=LOOKBACK_DAYS)
    wait_for_network()
    before=retry_on_lock(counts)
    retry_on_lock(lambda:run_collector(start,end))
    after=retry_on_lock(counts)
    msg=f'{start}..{end}: +{after[0]-before[0]} new_business, +{after[1]-before[1]} disclosures'
    notify('KAP collector OK',msg)


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
        sys.exit(0)
    try:
        main()
    except Exception as e:
        notify('KAP collector FAILED',str(e)[-500:],'high')
        raise   # keep the traceback in daily.log and a non-zero exit code