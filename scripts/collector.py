'''Collect KAP "Yeni Is Iliskisi" data from Matriks into DuckDB.

Two sources, joined later by KAP link:
  1) new-business-api  -> table new_business (amount, currency, ratios)
  2) news search (source:KAP tag:NewBusiness) -> table disclosures (form + free text)

Matriks rules: max 1 request/sec (1.1 s wait + backoff), raw data stays in data/.

Usage:
  python scripts/collector.py --start 2026-09-01 --end 2026-09-30
'''
from zoneinfo import ZoneInfo
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import duckdb
import requests
from dotenv import load_dotenv

from parse_form import parse_form
from pull_guard import AlreadyPulled, claim

# new_business comes from prod (probe v2, 2026-11-05: same deals, newer revenue periods);
# news is not tested on prod yet, so it stays on apitest
NB_API=os.environ.get('MATRIKS_NB_API','https://<MATRIKS_API_HOST>/dumrul')
NEWS_API=os.environ.get('MATRIKS_NEWS_API','https://<MATRIKS_API_HOST>/dumrul')
DB_PATH='data/kap.duckdb'
SCHEMA_PATH='scripts/schema.sql'
MIN_INTERVAL=1.1
MAX_TRIES=5
PAGE_SIZE=100
SEARCH_COUNT=2000

load_dotenv()
TOKEN=os.environ['KAP_TOKEN']
KAP_LINK=re.compile(r'https?://www\.kap\.org\.tr/Bildirim/\d+')
HEADLINE_SYM=re.compile(r'KAP:\s*([A-Z0-9]+)')


def get(path,params,base=NEWS_API):
    wait=MIN_INTERVAL
    for attempt in range(1,MAX_TRIES+1):
        time.sleep(wait)
        resp=requests.get(f'{base}/{path}',params=params,headers={'Authorization':f'jwt {TOKEN}'},timeout=60)
        if resp.status_code==429 or resp.status_code>=500:
            wait=MIN_INTERVAL*2**attempt
            print(f'  HTTP {resp.status_code}, retry {attempt}/{MAX_TRIES} in {wait:.1f}s')
            continue
        if resp.status_code!=200:
            sys.exit(f'HTTP {resp.status_code} on {path}: {resp.text[:300]}')
        return resp.json()
    sys.exit(f'Gave up on {path} after repeated 429/5xx.')


def month_ranges(start,end):
    s=start
    while s<=end:
        next_month=(s.replace(day=1)+timedelta(days=32)).replace(day=1)
        e=min(next_month-timedelta(days=1),end)
        yield s,e
        s=e+timedelta(days=1)


def norm_url(url):
    return (url or '').strip().rstrip('/').replace('http://','https://')


def answer_is_yes(value):
    return (value or '').strip().lower().startswith('evet')


def fetch_new_business(con,s,e,base=NB_API):
    rows=get('v1/new-business-api',{'start':s.isoformat(),'end':e.isoformat()},base=base)
    data=[(norm_url(r.get('url')),r.get('sym'),r.get('date'),r.get('cur'),r.get('amount'),
           r.get('desc'),r.get('per'),r.get('rt'),r.get('shfRet'),r.get('tcmbExRt'),
           r.get('cumRt'),r.get('marValRt')) for r in rows if r.get('url')]
    if data:
        con.executemany('''INSERT OR REPLACE INTO new_business
            (url,sym,date,cur,amount,description,per,rt,shf_ret,tcmb_ex_rt,cum_rt,mar_val_rt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',data)
    return len(data)


def fetch_disclosures(con,s,e):
    query=f'source:KAP tag:NewBusiness after:{s.isoformat()} before:{(e+timedelta(days=1)).isoformat()}'
    search=get('v2/news/search',{'query':query,'count':SEARCH_COUNT})
    qid,total=search.get('id'),search.get('messageCount') or 0
    if search.get('err') or not qid:
        print(f'  search error: {search.get("err")}')
        return 0,0
    if total>=SEARCH_COUNT:
        print(f'  WARNING: {total} results hit the search cap, use a shorter range')

    in_range,out_range,page=[],0,0
    while page*PAGE_SIZE<total:
        items=get('v2/news/search/page',{'qid':qid,'page':page,'pageSize':PAGE_SIZE})
        if not items:
            break
        for item in items:
            published=datetime.fromisoformat(item['date'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Istanbul'))
            if s<=published.date()<=e:
                in_range.append((item,published))
            else:
                out_range+=1
        page+=1

    data=[]
    for item,published in in_range:
        content=item.get('content') or ''
        link=KAP_LINK.search(content)
        syms=item.get('symbol') or []
        sym=syms[0] if syms else (HEADLINE_SYM.search(item.get('headline') or '') or [None,None])[1]
        form=parse_form(content)
        data.append((item['id'],norm_url(link.group(0) if link else None),item.get('headline'),sym,
                     published.replace(tzinfo=None),
                     answer_is_yes(form.get('Yapılan Açıklama Güncelleme mi?')),
                     answer_is_yes(form.get('Yapılan Açıklama Düzeltme mi?')),
                     json.dumps(form,ensure_ascii=False),form.get('Açıklama')))
    if data:
        con.executemany('''INSERT OR REPLACE INTO disclosures
            (news_id,kap_url,headline,symbol,published_at,is_update,is_correction,form_json,aciklama)
            VALUES (?,?,?,?,?,?,?,?,?)''',data)
    return len(data),out_range


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start',required=True,type=date.fromisoformat)
    parser.add_argument('--end',required=True,type=date.fromisoformat)
    args=parser.parse_args()

    con=duckdb.connect(DB_PATH)
    con.execute(open(SCHEMA_PATH,encoding='utf-8').read())
    try:
        claim('collector')   # one pull per day; after the DB lock, right before the first request
    except AlreadyPulled as e:
        con.close()
        sys.exit(str(e))

    for s,e in month_ranges(args.start,args.end):
        print(f'{s} -> {e}')
        nb=fetch_new_business(con,s,e)
        dc,out=fetch_disclosures(con,s,e)
        print(f'  new_business: {nb} | disclosures: {dc} (ignored out of range: {out})')

    nb_total=con.execute('SELECT count(*) FROM new_business').fetchall()[0][0]
    dc_total=con.execute('SELECT count(*) FROM disclosures').fetchall()[0][0]
    matched=con.execute('''SELECT count(*) FROM new_business n
        JOIN disclosures d ON n.url=d.kap_url''').fetchall()[0][0]
    print(f'\nTotals -> new_business: {nb_total} | disclosures: {dc_total} | matched by KAP link: {matched}')
    con.close()


if __name__=='__main__':
    main()