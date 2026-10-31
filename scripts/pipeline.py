'''Combined extraction pipeline: v3 prompt plus the three code checks.

The LLM extracts facts. Code checks only flag: they never change the amount or the
currency. Failures are flagged as run_error, never dropped.
Output goes to data/pipeline_<label>.jsonl. Stdout shows only counts.

Usage:
  python scripts/pipeline.py --self-test
  python scripts/pipeline.py --date 2026-10-30
  python scripts/pipeline.py --ids 123,456
'''
import argparse
import json
import subprocess
import time
from datetime import datetime

import duckdb

from amount_checks import amount_is_projection,cumulative_total
from currency_check import currency_unclear
from llm_extract import DEFAULT_PROMPT,MODEL,call_llm

DB_PATH='data/kap.duckdb'
RUN_ERROR='run_error'
SELECT='SELECT news_id,kap_url,symbol,published_at,aciklama FROM disclosures'


def apply_checks(data,text):
    '''Add the code-check flags. Same inputs as level 2 in score_silent.py.'''
    amount,currency=data.get('amount'),data.get('currency')
    reasons=list(data.get('needs_review_reasons') or [])
    if currency_unclear(text):
        reasons.append('currency_unclear')
    if amount_is_projection(text,amount):
        reasons.append('amount_is_projection')
    if cumulative_total(text,amount,currency):
        reasons.append('cumulative_total')
    data['needs_review_reasons']=list(dict.fromkeys(reasons))
    data['needs_review']=bool(data['needs_review_reasons'])
    return data


def analyze(text,extract=call_llm):
    '''Extract and check one text. Any failure comes back flagged, never missing.'''
    try:
        data=extract(text)
    except Exception as e:
        return {'needs_review':True,'needs_review_reasons':[RUN_ERROR],'error':type(e).__name__}
    if data is None:
        return {'needs_review':True,'needs_review_reasons':[RUN_ERROR],'error':'invalid_output'}
    return apply_checks(data,text)


def load_rows(date_value,ids):
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        if ids:
            marks=','.join('?' for _ in ids)
            return con.execute(f'{SELECT} WHERE news_id IN ({marks}) ORDER BY published_at',ids).fetchall()
        return con.execute(f'{SELECT} WHERE CAST(published_at AS DATE)=? ORDER BY published_at',[date_value]).fetchall()
    finally:
        con.close()


def _self_test():
    clean='2.000.000 USD tutarında sipariş alınmıştır.'
    base={'amount':2000000.0,'currency':'USD','needs_review_reasons':[]}

    out=apply_checks(dict(base),clean)
    assert out['needs_review'] is False and out['needs_review_reasons']==[]

    text='1.000.000 TL (25.000 USD) tutarında sipariş alınmıştır.'
    out=apply_checks({'amount':1000000.0,'currency':'TRY','needs_review_reasons':['currency_unclear']},text)
    assert out['needs_review_reasons']==['currency_unclear']

    text='Projenin 2027 yılı cirosu 5.000.000 EUR olarak bütçelenmiştir.'
    out=apply_checks({'amount':5000000.0,'currency':'EUR','needs_review_reasons':[]},text)
    assert out['needs_review_reasons']==['amount_is_projection'] and out['amount']==5000000.0

    text='Ek olarak 2.000.000 USD sipariş alınmış, toplamda 5.000.000 USD olmuştur.'
    out=apply_checks(dict(base),text)
    assert 'cumulative_total' in out['needs_review_reasons']
    assert out['amount']==2000000.0 and out['currency']=='USD'

    out=apply_checks({'amount':None,'currency':None,'needs_review_reasons':[]},clean)
    assert out['needs_review'] is False

    out=apply_checks({'amount':None,'currency':None,'needs_review_reasons':['amount_unclear']},clean)
    assert out['needs_review'] is True

    out=analyze(clean,extract=lambda t:None)
    assert out['needs_review'] and out['error']=='invalid_output'

    def broken(t):
        raise TimeoutError
    out=analyze(clean,extract=broken)
    assert out['needs_review_reasons']==[RUN_ERROR] and out['error']=='TimeoutError'

    out=analyze(clean,extract=lambda t:dict(base))
    assert out['needs_review'] is False and out['amount']==2000000.0
    print('self-test ok: 9 cases')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--date')
    parser.add_argument('--ids')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        _self_test()
        return
    if bool(args.date)==bool(args.ids):
        parser.error('give exactly one of --date or --ids')

    now=datetime.now()
    if now.hour==23 and 40<=now.minute<=50:
        raise SystemExit('collection window, try after 23:50')

    ids=args.ids.split(',') if args.ids else None
    rows=load_rows(args.date,ids)[:args.limit]
    commit=subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip()
    out_path=f'data/pipeline_{args.date or "ids"}.jsonl'
    flagged=errors=0
    start=time.time()
    with open(out_path,'w',encoding='utf-8') as f:
        for news_id,url,symbol,published_at,text in rows:
            result=analyze(text)
            flagged+=result['needs_review']
            errors+=RUN_ERROR in result['needs_review_reasons']
            result.update({'news_id':str(news_id),'kap_url':url,'symbol':symbol,'published_at':str(published_at),
                           'prompt_version':DEFAULT_PROMPT,'model':MODEL,'git_commit':commit})
            f.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(f'rows={len(rows)} flagged={flagged} run_errors={errors} seconds={time.time()-start:.0f} -> {out_path}')


if __name__=='__main__':
    main()
