'''Importance score v1 for pipeline results (rules in docs/importance_score.md).

The score is computed in code from extracted facts and our own database.
It never changes the extracted fields; needs_review is passed through as a reliability flag.
Output goes to data/triage_<label>.jsonl. Stdout shows only counts.

Usage:
  python scripts/importance.py --self-test
  python scripts/importance.py --pipeline data/pipeline_2026-10-28.jsonl
'''
import argparse
import json
import os
import re
from datetime import date, timedelta

import duckdb

DB_PATH='data/kap.duckdb'
USE_REVENUE=False  # rt / shf_ret stay off until the prod/apitest difference is explained
RATE_DAYS=10
MIN_HISTORY=3
TRY_CODES=('TRY','TL')

DURATION_RE=re.compile(r'(\d+(?:[.,]\d+)?)\s*(yıl|yil|sene|year|ay|month|gün|gun|day)',re.I)
UNIT_YEARS={'yıl':1,'yil':1,'sene':1,'year':1,'ay':1/12,'month':1/12,'gün':1/365,'gun':1/365,'day':1/365}


def duration_years(text):
    '''Longest duration written in the text, in years; None if none is found.'''
    best=None
    for num,unit in DURATION_RE.findall(text or ''):
        value=float(num.replace(',','.'))
        if value>=1900:
            continue  # a calendar year ("2026 yılı sonuna kadar"), not a length
        years=value*UNIT_YEARS[unit.lower()]
        best=years if best is None else max(best,years)
    return best


def fx_rate(con,currency,day):
    '''Central bank rate for currency, latest on or before day (at most RATE_DAYS back).'''
    if currency in TRY_CODES:
        return 1.0
    rows=con.execute('''SELECT tcmb_ex_rt FROM new_business
        WHERE trim(upper(cur))=? AND tcmb_ex_rt>0 AND date<=? AND date>=?
        ORDER BY date DESC LIMIT 1''',[currency,day,day-timedelta(days=RATE_DAYS)]).fetchall()
    return rows[0][0] if rows else None


def company_baseline(con,symbol,day):
    '''Median TRY value of the company's deals before day, and how many there were.'''
    rows=con.execute('''SELECT median(CASE WHEN trim(upper(cur)) IN ('TRY','TL') THEN amount ELSE amount*tcmb_ex_rt END),count(*)
        FROM new_business WHERE sym=? AND date<? AND amount>0
        AND (trim(upper(cur)) IN ('TRY','TL') OR tcmb_ex_rt>0)''',[symbol,day]).fetchall()
    return rows[0]


def size_points(amount_try,baseline,n_history):
    if amount_try is None or amount_try<=0:
        return 0,None
    if n_history>=MIN_HISTORY and baseline:
        ratio=amount_try/baseline
        points=3 if ratio>=3 else 2 if ratio>=1.5 else 1 if ratio>=0.5 else 0
        return points,{'code':'size_vs_history','ratio':round(ratio,2),'n_history':n_history}
    points=2 if amount_try>=1e9 else 1 if amount_try>=1e8 else 0
    return points,{'code':'size_absolute','n_history':n_history}


def score(result,rate,baseline,n_history):
    '''Points and reasons for one pipeline result. rate is TRY per unit of its currency.'''
    reasons,total=[],0
    amount,currency=result.get('amount'),result.get('currency')
    kind='revision' if result.get('is_revision') else 'new'
    if kind=='revision' and amount is not None:
        previous=result.get('previous_amount')
        amount=amount-previous if previous is not None else None
        reasons.append({'code':'revision','points':0})
    if amount is None:
        reasons.append({'code':'no_amount','points':0})
    elif rate is None:
        reasons.append({'code':'no_rate','currency':currency,'points':0})
    else:
        points,reason=size_points(amount*rate,baseline,n_history)
        if reason:
            reason['points']=points
            reasons.append(reason)
        else:
            reasons.append({'code':'no_increase','points':0})
        total+=points
    if currency and currency not in TRY_CODES:
        reasons.append({'code':'foreign_currency','currency':currency,'points':1})
        total+=1
    if result.get('counterparty_origin')=='foreign':
        reasons.append({'code':'foreign_counterparty','points':1})
        total+=1
    years=duration_years(result.get('duration'))
    if years is not None and years>=2:
        reasons.append({'code':'long_contract','years':round(years,1),'points':1})
        total+=1
    if result.get('related_party') is True:
        reasons.append({'code':'related_party','points':-2})
        total-=2
    level='high' if total>=4 else 'medium' if total>=2 else 'low'
    return {'score':total,'level':level,'kind':kind,'reasons':reasons,
            'needs_review':bool(result.get('needs_review')),
            'needs_review_reasons':result.get('needs_review_reasons') or []}


def score_result(con,result):
    day=date.fromisoformat(result['published_at'][:10])
    currency=result.get('currency')
    rate=fx_rate(con,currency,day) if currency else None
    baseline,n_history=company_baseline(con,result.get('symbol'),day)
    return score(result,rate,baseline,n_history)


def _self_test():
    assert duration_years('3 yıl')==3 and duration_years('36 ay')==3
    assert duration_years('2 yıl 6 ay')==2 and duration_years('teslim tarihi 31.12.2027') is None
    assert abs(duration_years('18 months')-1.5)<1e-9 and duration_years(None) is None
    assert duration_years('2026 yılı sonuna kadar') is None and duration_years('730 gün')==2

    con=duckdb.connect()
    con.execute('CREATE TABLE new_business (sym VARCHAR, date DATE, cur VARCHAR, amount DOUBLE, tcmb_ex_rt DOUBLE)')
    con.executemany('INSERT INTO new_business VALUES (?,?,?,?,?)',[
        ('AAA',date(2026,1,5),'TRY',100.0,1.0),('AAA',date(2026,2,5),'USD',10.0,20.0),
        ('AAA',date(2026,3,5),'TRY',300.0,1.0),('AAA',date(2026,10,1),'TRY',9999.0,1.0),
        ('AAA',date(2026,9,25),' USD',1.0,40.0),('BBB',date(2026,3,5),'TRY',50.0,1.0)])
    assert fx_rate(con,'USD',date(2026,9,30))==40.0
    assert fx_rate(con,'USD',date(2026,10,20)) is None
    assert fx_rate(con,'TRY',date(2026,10,20))==1.0
    assert company_baseline(con,'AAA',date(2026,9,1))==(200.0,3)
    assert company_baseline(con,'BBB',date(2026,9,1))[1]==1

    base={'amount':700.0,'currency':'TRY','counterparty_origin':'unknown','related_party':None,
          'is_revision':False,'previous_amount':None,'duration':None,'needs_review':False}
    out=score(base,1.0,200.0,3)
    assert out['score']==3 and out['level']=='medium' and out['reasons'][0]['ratio']==3.5
    out=score({**base,'currency':'USD','counterparty_origin':'foreign','duration':'3 yıl'},40.0,200.0,3)
    assert out['score']==6 and out['level']=='high'
    out=score({**base,'related_party':True},1.0,200.0,3)
    assert out['score']==1 and out['level']=='low'
    out=score({**base,'amount':None},1.0,200.0,3)
    assert out['score']==0 and out['reasons'][0]['code']=='no_amount'
    out=score({**base,'currency':'XYZ'},None,200.0,3)
    assert out['reasons'][0]['code']=='no_rate' and out['score']==1
    out=score({**base,'is_revision':True,'previous_amount':650.0},1.0,200.0,3)
    assert out['kind']=='revision' and out['score']==0
    out=score({**base,'amount':2e9},1.0,None,0)
    assert out['score']==2 and out['reasons'][0]['code']=='size_absolute'
    out=score({**base,'needs_review':True,'needs_review_reasons':['currency_unclear']},1.0,200.0,3)
    assert out['score']==3 and out['needs_review'] and out['needs_review_reasons']==['currency_unclear']
    con.close()
    print('self-test ok: 20 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pipeline')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    if not args.pipeline:
        ap.error('give --pipeline or --self-test')

    with open(args.pipeline,encoding='utf-8') as f:
        results=[json.loads(l) for l in f if l.strip()]
    label=os.path.basename(args.pipeline).removeprefix('pipeline_').removesuffix('.jsonl')
    out_path=f'data/triage_{label}.jsonl'
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        scored=[{**r,'importance':score_result(con,r)} for r in results]
    finally:
        con.close()
    with open(out_path,'w',encoding='utf-8') as f:
        for r in scored:
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
    levels={k:sum(r['importance']['level']==k for r in scored) for k in ('high','medium','low')}
    flagged=sum(r['importance']['needs_review'] for r in scored)
    print(f'rows={len(scored)} '+' '.join(f'{k}={v}' for k,v in levels.items())+f' flagged={flagged} -> {out_path}')


if __name__=='__main__':
    main()
