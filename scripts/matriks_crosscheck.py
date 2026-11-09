'''Cross-check the extracted amount against Matriks' own record (rules: docs/matriks_crosscheck_rule.md).

amount_vs_matriks(...) flags when our amount and Matriks' amount, both in TRY, differ by more
than 2x either way. Flag only; nothing is changed. Skipped when there is no Matriks record,
no extracted amount, or no common rate.

--fp RESULTS...  false-alarm count on existing v3 eval files (no LLM). Stdout: counts only.

Usage:
  python scripts/matriks_crosscheck.py --self-test
  python scripts/matriks_crosscheck.py --fp data/eval_v3final_test_amount.jsonl data/eval_v3_e4b_set_b.jsonl
'''
import argparse
import json

from eval_vs_matriks import norm_cur

DB_PATH='data/kap.duckdb'
MAX_RATIO=2.0


def in_try(amount,cur,mx_cur,rate):
    '''Amount in TRY using Matriks' rate for its own currency; None if no common basis.'''
    if amount is None:
        return None
    cur=norm_cur(cur)
    if cur=='TRY':
        return float(amount)
    if cur and cur==norm_cur(mx_cur) and rate:
        return float(amount)*float(rate)
    return None


def amount_vs_matriks(our_amount,our_cur,mx_amount,mx_cur,mx_rate):
    '''True if both amounts exist in TRY and their ratio is above MAX_RATIO or below 1/MAX_RATIO.'''
    if our_amount is None or not mx_amount or mx_amount<=0:
        return False
    mx_try=in_try(mx_amount,mx_cur,mx_cur,mx_rate)
    ours=in_try(our_amount,our_cur,mx_cur,mx_rate)
    if not mx_try or ours is None:
        return False
    ratio=ours/mx_try
    return ratio>MAX_RATIO or ratio<1/MAX_RATIO


def load_matriks(news_ids):
    '''news_id -> (amount, cur, tcmb_ex_rt) for disclosures with a Matriks record (one short read).'''
    import duckdb
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        rows=con.execute('''SELECT d.news_id,n.amount,n.cur,n.tcmb_ex_rt FROM disclosures d
                            JOIN new_business n ON n.url=d.kap_url''').fetchall()
    finally:
        con.close()
    wanted={str(i) for i in news_ids}
    return {str(nid):(a,c,r) for nid,a,c,r in rows if str(nid) in wanted}


def false_alarms(paths):
    from amount_checks import amount_is_projection, cumulative_total
    from currency_check import currency_unclear
    from score_silent import load_texts
    rows={}
    for p in paths:
        with open(p,encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line)
                    rows[str(r['news_id'])]=r
    texts=load_texts(set(rows))
    mx=load_matriks(rows)
    c={'rows':len(rows),'with_matriks':0,'already_flagged':0,'checked':0,'skipped_no_basis':0,'new_flags':0}
    for nid,r in rows.items():
        if nid not in mx:
            continue
        c['with_matriks']+=1
        text=texts.get(nid) or ''
        amt,cur=r.get('llm_amount'),r.get('llm_cur')
        if r.get('needs_review_reasons') or r.get('error') or currency_unclear(text) or \
                amount_is_projection(text,amt) or cumulative_total(text,amt,cur):
            c['already_flagged']+=1
            continue
        a,mc,rate=mx[nid]
        if amt is None or in_try(amt,cur,mc,rate) is None or not in_try(a,mc,mc,rate):
            c['skipped_no_basis']+=1
            continue
        c['checked']+=1
        c['new_flags']+=amount_vs_matriks(amt,cur,a,mc,rate)
    return c


def _self_test():
    assert not amount_vs_matriks(1_200_000,'TRY',1_000_000,'TRY',None)        # VAT-size gap: left alone
    assert amount_vs_matriks(999_999_999,'TRY',1_000_000,'TRY',None)           # gross gap: flagged
    assert amount_vs_matriks(400_000,'TRY',1_000_000,'TRY',None)               # below half: flagged
    assert not amount_vs_matriks(500_000,'TRY',1_000_000,'TRY',None)           # exactly half: left alone
    assert not amount_vs_matriks(30_000_000,'TRY',1_000_000,'USD',32.0)        # TL equivalent of a USD deal
    assert amount_vs_matriks(999_999_999,'USD',1_000_000,'USD',32.0)           # same currency, gross gap
    assert not amount_vs_matriks(1_000_000,'EUR',1_000_000,'USD',32.0)         # two foreign currencies: skipped
    assert not amount_vs_matriks(None,'TRY',1_000_000,'TRY',None)              # no extracted amount
    assert not amount_vs_matriks(5,'TRY',None,'TRY',None) and not amount_vs_matriks(5,'TRY',0,'TRY',None)
    assert not amount_vs_matriks(1_000_000,'TL',1_000_000,'TRY',None)          # TL normalised to TRY
    assert not amount_vs_matriks(5_000_000,'USD',1_000_000,'USD',None)         # foreign without a rate: skipped
    print('self-test ok: 12 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fp',nargs='+',metavar='RESULTS')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.fp:
        print(' '.join(f'{k}={v}' for k,v in false_alarms(args.fp).items()))
    else:
        ap.error('give --fp RESULTS... or --self-test')


if __name__=='__main__':
    main()
