import os
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


def main():
    end=date.today()
    start=end-timedelta(days=LOOKBACK_DAYS)
    before=counts()

    r=subprocess.run(
        [sys.executable,'scripts/collector.py','--start',start.isoformat(),'--end',end.isoformat()],
        capture_output=True,
        text=True,
    )
    if r.returncode!=0:
        notify('KAP collector FAILED',r.stderr[-500:] or 'no stderr','high')
        sys.exit(1)

    after=counts()
    msg=f'{start}..{end}: +{after[0]-before[0]} new_business, +{after[1]-before[1]} disclosures'
    notify('KAP collector OK',msg)


if __name__=='__main__':
    main()