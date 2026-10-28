import argparse
import json 
import subprocess
import time
from pathlib import Path

import duckdb

from llm_extract import MODEL,NUM_PREDICT,THINK,call_llm,load_prompt


def git_commit():
    # tie every result row to the code that produced it; -dirty = uncommitted changes
    try:
        h=subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
        dirty=subprocess.run(['git','status','--porcelain','--untracked-files=no'],capture_output=True,text=True,check=True).stdout.strip()
        return h+('-dirty' if dirty else '')
    except Exception:
        return None


GIT_COMMIT=git_commit()

DB='data/kap.duckdb'
OUT=Path('data/eval_llm_vs_matriks.jsonl')
AMOUNT_FIELD='amount'      # TODO: check name in Disclosure class
CURRENCY_FIELD='currency'  # TODO: check name in Disclosure class
N_WITH=70     # regex finds an amount in text
N_WITHOUT=30  # regex finds nothing, but Matriks has an amount
TOL=0.01      # 1% relative tolerance
MAX_ERROR_STREAK=3   # stop the run after this many errors in a row

AMOUNT_RE=r'(?i)(\d[\d.,]*\s*(milyon|milyar|bin)?\s*(tl|türk lirası|usd|abd doları|dolar|euro|avro|eur|€|\$))|([€$]\s*\d)'

CUR_MAP={
    'tl':'TRY','try':'TRY','türk lirası':'TRY',
    'usd':'USD','abd doları':'USD','dolar':'USD','$':'USD',
    'eur':'EUR','euro':'EUR','avro':'EUR','€':'EUR',
}

SAMPLE_SQL=f'''
WITH m AS (
    SELECT d.news_id,d.kap_url,d.aciklama,d.is_update,n.amount,n.cur,
        regexp_matches(d.aciklama,'{AMOUNT_RE}') AS regex_hit
    FROM disclosures d
    JOIN new_business n ON n.url=d.kap_url
    WHERE d.aciklama IS NOT NULL
)
(SELECT * FROM m WHERE regex_hit ORDER BY hash(news_id) LIMIT {N_WITH})
UNION ALL
(SELECT * FROM m WHERE NOT regex_hit ORDER BY hash(news_id) LIMIT {N_WITHOUT})
'''

IDS_SQL=f'''
SELECT d.news_id,d.kap_url,d.aciklama,d.is_update,n.amount,n.cur,
    regexp_matches(d.aciklama,'{AMOUNT_RE}') AS regex_hit
FROM disclosures d
JOIN new_business n ON n.url=d.kap_url
WHERE d.aciklama IS NOT NULL AND list_contains(?,d.news_id)
'''


def load_ids(path):
    with open(path,encoding='utf-8') as f:
        return [str(json.loads(line)['news_id']) for line in f if line.strip()]


def norm_cur(c):
    if not c:
        return None
    c=str(c).strip().lower()
    return CUR_MAP.get(c,c.upper())


def to_dict(res):
    if res is None:
        raise ValueError('call_llm returned None (invalid model output)')
    if hasattr(res,'model_dump'):
        return res.model_dump()
    if isinstance(res,str):
        return json.loads(res)
    return dict(res)


def amount_ok(llm,mx):
    if llm is None and mx is None:
        return True  # both agree: no amount in text
    if llm is None or mx is None:
        return False
    try:
        llm=float(llm)
    except (TypeError,ValueError):
        return False
    if mx==0:
        return llm==0
    return abs(llm-mx)/abs(mx)<=TOL


def load_done(out,retry_errors=False):
    '''Load finished rows; the last row per news_id wins.
    retry_errors=True drops rows that ended in an error so a resumed run tries them again.'''
    if not out.exists():
        return {}
    recs={}
    with out.open(encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if retry_errors and r.get('error'):
                continue
            r['amount_ok']=amount_ok(r['llm_amount'],r['matriks_amount'])
            recs[r['news_id']]=r
    return recs


def run(limit,ids_path,out,prompt_version):
    con=duckdb.connect(DB,read_only=True)
    if ids_path:
        ids=load_ids(ids_path)
        rows=con.execute(IDS_SQL,[ids]).fetchall()
        cols=[c[0] for c in con.description]
        order={nid:i for i,nid in enumerate(ids)}
        rows=sorted(rows,key=lambda row:order[str(row[0])])
        if len(rows)!=len(ids):
            print(f'WARNING: {len(ids)} ids, {len(rows)} found in DB')
    else:
        rows=con.execute(SAMPLE_SQL).fetchall()
        cols=[c[0] for c in con.description]
    con.close()
    if limit:
        rows=rows[:limit]
    done=load_done(out,retry_errors=True)
    mixed=[r['news_id'] for r in done.values() if r.get('prompt_version')!=prompt_version]
    if mixed:
        raise SystemExit(f'{out} has {len(mixed)} rows from another prompt version; use a new --out')
    prompt=load_prompt(prompt_version)
    test_set=Path(ids_path).stem if ids_path else 'default_sample'
    print(f'{len(rows)} samples, {len(done)} already done')

    streak=0
    with out.open('a',encoding='utf-8') as f:
        for i,row in enumerate(rows,1):
            r=dict(zip(cols,row))
            if r['news_id'] in done:
                continue
            t0=time.time()
            try:
                pred=to_dict(call_llm(r['aciklama'],prompt=prompt,version=prompt_version))
                err=None
            except Exception as e:
                pred={}
                err=str(e)
            llm_amt=pred.get(AMOUNT_FIELD)
            llm_cur=norm_cur(pred.get(CURRENCY_FIELD))
            mx_cur=norm_cur(r['cur'])
            rec={
                'news_id':r['news_id'],
                'kap_url':r['kap_url'],
                'prompt_version':prompt_version,
                'model':MODEL,
                'think':THINK,
                'num_predict':NUM_PREDICT,
                'git_commit':GIT_COMMIT,
                'test_set':test_set,
                'group':'regex_hit' if r['regex_hit'] else 'regex_miss',
                'is_update':r['is_update'],
                'matriks_amount':r['amount'],
                'matriks_cur':mx_cur,
                'llm_amount':llm_amt,
                'llm_cur':llm_cur,
                'amount_try_stated':pred.get('amount_try_stated'),
                'needs_review_reasons':pred.get('needs_review_reasons'),
                'amount_ok':amount_ok(llm_amt,r['amount']),
                'cur_ok':llm_cur==mx_cur,
                'error':err,
                'seconds':round(time.time()-t0,1),
            }
            f.write(json.dumps(rec,ensure_ascii=False)+'\n')
            # stop early if the model keeps failing (e.g. Ollama hung); rerun the same command to resume
            streak=streak+1 if err else 0
            if streak>=MAX_ERROR_STREAK:
                raise SystemExit(f'{streak} errors in a row, last: {err}\nCheck Ollama (ollama ps), restart it, then rerun the same command to resume.')
            f.flush()
            mark='OK' if rec['amount_ok'] and rec['cur_ok'] else 'XX'
            print(f'[{i}/{len(rows)}] {mark} {rec["group"]} {rec["seconds"]}s')


def summarize(out):
    recs=list(load_done(out).values())
    if not recs:
        print('no results yet')
        return
    print('\n== summary ==')
    for g in ['regex_hit','regex_miss','ALL']:
        sub=[r for r in recs if g=='ALL' or r['group']==g]
        if not sub:
            continue
        n=len(sub)
        a=sum(r['amount_ok'] for r in sub)
        c=sum(r['cur_ok'] for r in sub)
        both=sum(r['amount_ok'] and r['cur_ok'] for r in sub)
        nulls=sum(r['llm_amount'] is None for r in sub)
        errs=sum(r['error'] is not None for r in sub)
        print(f'{g:11} n={n:3}  amount={a}/{n}  currency={c}/{n}  both={both}/{n}  llm_null={nulls}  errors={errs}')

    # unit mistakes (thousand / million) show up as round ratios
    print('\n== amount mismatches (llm / matriks ratio) ==')
    for r in recs:
        if r['amount_ok'] or r['llm_amount'] is None or not r['matriks_amount']:
            continue
        try:
            ratio=float(r['llm_amount'])/r['matriks_amount']
        except (TypeError,ValueError):
            ratio=None
        print(r['news_id'],r['group'],r['llm_amount'],r['matriks_amount'],ratio)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--summary',action='store_true')
    p.add_argument('--ids',default='',help='jsonl with a news_id per line; replaces the default sample')
    p.add_argument('--out',default=str(OUT))
    p.add_argument('--prompt',default='v2',help='prompt version, reads prompts/extract_<version>.txt')
    args=p.parse_args()
    out=Path(args.out)
    if not args.summary:
        run(args.limit,args.ids,out,args.prompt)
    summarize(out)