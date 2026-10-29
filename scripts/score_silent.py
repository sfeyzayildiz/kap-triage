'''Silent-error scoring for amount extraction (Set B decision rule).

Reference per row: gold label if present, else Matriks values from the
results file (Set A fallback). Gold needs_review rows are included.

Silent error: row is not flagged and (amount, currency) does not match the
reference. Types: fabricated (ref null, model amount), missed (ref amount,
model null), wrong_amount, wrong_currency.

Levels, all from the same run:
  frozen:            flagged = needs_review_reasons non-empty or run error
  +currency_unclear: also flagged when currency_unclear(aciklama) is true
  +projection+cumulative (post-hoc): also amount_is_projection / cumulative_total
                     (designed after Set B error analysis; on Set B = optimistic)

Decision: PASS if silent errors <= 1 and flag rate <= 15%.
INCOMPLETE if any gold id is missing from the results.

Usage:
    python scripts/score_silent.py RESULTS --gold data/gold_set_b.jsonl
'''
import argparse
import json

import duckdb

from amount_checks import amount_is_projection,cumulative_total
from currency_check import currency_unclear
from eval_vs_matriks import amount_ok,norm_cur

DB='data/kap.duckdb'
MAX_SILENT=1
MAX_FLAG_RATE=0.15
LEVELS=(('frozen',0),('+currency_unclear',1),('+projection+cumulative (post-hoc)',2))


def load_jsonl(path):
    with open(path,encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def load_results(path):
    # keep the last row per news_id in case a run was resumed
    rows={}
    for r in load_jsonl(path):
        rows[str(r['news_id'])]=r
    return rows


def load_texts(ids):
    con=duckdb.connect(DB,read_only=True)
    try:
        rows=con.execute('select news_id, aciklama from disclosures').fetchall()
    finally:
        con.close()
    return {str(nid):txt for nid,txt in rows if str(nid) in ids}


def upper_95(k,n):
    '''One-sided 95% Clopper-Pearson upper bound for k errors in n.'''
    if n==0 or k>=n:
        return 1.0

    def cdf(p):
        # P(X<=k) for Binomial(n,p)
        total=0.0
        term=(1-p)**n
        for i in range(k+1):
            if i>0:
                term*=(n-i+1)/i*p/(1-p)
            total+=term
        return total

    lo,hi=0.0,1.0
    for _ in range(60):
        mid=(lo+hi)/2
        if cdf(mid)>0.05:
            lo=mid
        else:
            hi=mid
    return hi


def compare(r,ref_amount,ref_cur):
    '''Return None if correct, else the error type.'''
    llm=r.get('llm_amount')
    if ref_amount is None and llm is None:
        return None
    if ref_amount is None:
        return 'fabricated'
    if llm is None:
        return 'missed'
    if not amount_ok(llm,ref_amount):
        return 'wrong_amount'
    if norm_cur(r.get('llm_cur'))!=norm_cur(ref_cur):
        return 'wrong_currency'
    return None


def extra_flag(level,text,amount,currency):
    if level>=1 and currency_unclear(text):
        return True
    if level>=2 and (amount_is_projection(text,amount) or cumulative_total(text,amount,currency)):
        return True
    return False


def score(rows,gold,texts,level):
    stats={'n':0,'flagged':0,'extra':0,'run_error':0,'silent':0,'gold_review':0,'gold_review_flagged':0}
    kinds={}
    silent_ids=[]
    for nid,r in sorted(rows.items()):
        stats['n']+=1
        g=gold.get(nid)
        if g is None:
            ref_amount,ref_cur,gold_review=r.get('matriks_amount'),r.get('matriks_cur'),False
        else:
            ref_amount,ref_cur,gold_review=g['amount'],g['currency'],bool(g['needs_review'])
        run_error=bool(r.get('error'))
        base=run_error or bool(r.get('needs_review_reasons'))
        extra=extra_flag(level,texts.get(nid),r.get('llm_amount'),r.get('llm_cur'))
        flagged=base or extra
        stats['run_error']+=run_error
        stats['flagged']+=flagged
        stats['extra']+=extra and not base
        if gold_review:
            stats['gold_review']+=1
            stats['gold_review_flagged']+=flagged
        if flagged:
            continue
        err=compare(r,ref_amount,ref_cur)
        if err:
            stats['silent']+=1
            kinds[err]=kinds.get(err,0)+1
            silent_ids.append((nid,err))
    return stats,kinds,silent_ids


def report(label,complete,stats,kinds,silent_ids):
    n=stats['n']
    rate=stats['flagged']/n if n else 0
    if not complete:
        decision='INCOMPLETE'
    elif stats['silent']<=MAX_SILENT and rate<=MAX_FLAG_RATE:
        decision='PASS'
    else:
        decision='FAIL'
    kind_str=', '.join(f'{k}={v}' for k,v in sorted(kinds.items())) or '-'
    print(f'[{label}]')
    print(f"  silent errors: {stats['silent']}/{n} ({kind_str}), 95% upper bound: {upper_95(stats['silent'],n):.1%}")
    print(f"  flagged: {stats['flagged']}/{n} ({rate:.1%}), extra from code checks: {stats['extra']}, run errors: {stats['run_error']}")
    print(f"  gold needs_review rows: {stats['gold_review']}, flagged: {stats['gold_review_flagged']}")
    print(f'  decision: {decision} (silent <= {MAX_SILENT}, flag rate <= {MAX_FLAG_RATE:.0%})')
    if silent_ids:
        print('  silent error ids: '+', '.join(f'{nid}({k})' for nid,k in silent_ids))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('results',help='eval result jsonl')
    p.add_argument('--gold',required=True)
    args=p.parse_args()

    rows=load_results(args.results)
    gold={str(g['news_id']):g for g in load_jsonl(args.gold)}
    texts=load_texts(set(rows))

    meta=next(iter(rows.values()),{})
    print(f"== {args.results} ({meta.get('prompt_version')}, {meta.get('model')}, think={meta.get('think')}, commit={meta.get('git_commit')})")
    missing=sorted(set(gold)-set(rows))
    if missing:
        print(f'  WARNING: {len(missing)} gold ids missing from results')
    no_text=sorted(set(rows)-set(texts))
    if no_text:
        print(f'  WARNING: {len(no_text)} result ids have no text in DB')
    fallback=sum(1 for nid in rows if nid not in gold)
    if fallback:
        print(f'  note: {fallback} rows scored against Matriks (no gold row)')

    for label,level in LEVELS:
        report(label,not missing,*score(rows,gold,texts,level))


if __name__=='__main__':
    main()