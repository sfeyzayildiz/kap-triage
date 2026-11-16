'''Score the sealed forward test: docs/forward_test_rule.md, applied as written. Counts and ids only.

Integrity  every snapshot hash equals its first logged hash (forward_seal.verify); a bad day is dropped
           and reported. The 16-character prefixes are printed so Feyza can compare them with her alerts.
Unit       each sealed disclosure of an intact day D. t1 = first trading day strictly after D (XU100 bars).
           AR = stock return - XU100 return on t1 (price_moves.abnormal, unadjusted closes).
Excluded   no price on t1; |stock return| > 22% on t1 (price_moves.SPLIT_JUMP). Counted and listed.
Primary    mean |AR| of look-first items minus mean |AR| of the others; one-sided permutation test,
           look-first labels shuffled 10,000 times, seed 20261114; p = (1 + shuffles >= observed) / 10,001.
Decision   at least 4 items in each group, difference > 0 and p <= 0.10 -> SUPPORTED; fewer -> TOO_FEW;
           otherwise NOT_SUPPORTED.
Reported   the same on the reaction day (price_moves.reaction_day), signed mean AR, counts per group.

INCOMPLETE (nothing scored) until XU100 has a bar on or after 2026-11-26. Scores once: the result goes to
data/forward_score.txt and a second call only prints it.

Usage:
  python scripts/forward_score.py --self-test
  python scripts/forward_score.py --score
'''
import argparse
import json
import os
import random
import statistics
from datetime import date, datetime, timedelta

from forward_seal import FIRST_DAY, LAST_DAY, LOG, SEAL_DIR, sha, verify
from price_moves import DB_PATH, INDEX, SPLIT_JUMP, abnormal, daily_returns, reaction_day

OUT='data/forward_score.txt'
NEED_BAR=date(2026,11,26)
SEED=20261114
SHUFFLES=10000
MIN_GROUP=4
P_BAR=0.10


def window_days():
    d,end=date.fromisoformat(FIRST_DAY),date.fromisoformat(LAST_DAY)
    out=[]
    while d<=end:
        out.append(d)
        d+=timedelta(days=1)
    return out


def load_seals(seal_dir=SEAL_DIR,log=LOG):
    '''({day: rows} of intact days in the window, bad days, days without a seal, {day: hash16}).'''
    _,_,bad=verify(seal_dir,log)
    seals,missing,prefix={},[],{}
    for d in window_days():
        p=os.path.join(seal_dir,f'{d.isoformat()}.json')
        if d.isoformat() in bad:
            continue
        if not os.path.exists(p):
            missing.append(d.isoformat())
            continue
        with open(p,'rb') as f:
            data=f.read()
        seals[d]=json.loads(data)
        prefix[d.isoformat()]=sha(data)[:16]
    return seals,[b for b in bad if FIRST_DAY<=b<=LAST_DAY],missing,prefix


def permutation_p(values,n_first,seed=SEED,shuffles=SHUFFLES):
    '''(difference of means: first n_first values minus the rest, one-sided p).'''
    diff=lambda v:statistics.fmean(v[:n_first])-statistics.fmean(v[n_first:])
    observed=diff(values)
    rng=random.Random(seed)
    v=list(values)
    hits=0
    for _ in range(shuffles):
        rng.shuffle(v)
        hits+=diff(v)>=observed
    return observed,(1+hits)/(1+shuffles)


def decide(n_look,n_other,diff,p):
    if n_look<MIN_GROUP or n_other<MIN_GROUP:
        return 'TOO_FEW'
    return 'SUPPORTED' if diff>0 and p<=P_BAR else 'NOT_SUPPORTED'


def measure(seals,closes,day_of):
    '''One pass. day_of(D, row, trading_days) -> the day whose AR is read. Returns the groups and exclusions.'''
    market=daily_returns(closes.get(INDEX,[]))
    trading=sorted(market)
    ar={s:abnormal(daily_returns(p),market) for s,p in closes.items() if s!=INDEX}
    out={'look':[],'other':[],'no_price':[],'split':[]}
    for d in sorted(seals):
        for row in seals[d]:
            t=day_of(d,row,trading)
            got=ar.get(row.get('symbol'),{}).get(t) if t else None
            if got is None:
                out['no_price'].append(row['news_id'])
            elif abs(got[1])>SPLIT_JUMP:
                out['split'].append(row['news_id'])
            else:
                out['look' if row['look_first'] else 'other'].append(got[0])
    return out


def t1_of(d,row,trading):
    later=[t for t in trading if t>d]
    return later[0] if later else None


def t0_of(d,row,trading):
    try:
        return reaction_day(datetime.fromisoformat(str(row.get('published_at'))),trading)
    except ValueError:
        return None


def summary(m):
    '''(n look, n other, difference of mean |AR|, p, decision, signed means) for one pass.'''
    look,other=m['look'],m['other']
    if not look or not other:
        return len(look),len(other),None,None,decide(len(look),len(other),0,1),(None,None)
    diff,p=permutation_p([abs(x) for x in look+other],len(look))
    return len(look),len(other),diff,p,decide(len(look),len(other),diff,p),(statistics.fmean(look),statistics.fmean(other))


def lines_for(seals,closes,bad=(),missing=(),prefix=None):
    out=[f'integrity: {"INTACT" if not bad else "BROKEN"}; sealed days {len(seals)}, dropped {list(bad)}, no seal {list(missing)}; '
         f'disclosures {sum(len(r) for r in seals.values())}']
    if prefix:
        out.append('hash prefixes (compare with the alerts): '+', '.join(f'{d} {h}' for d,h in sorted(prefix.items())))
    pct=lambda x:'n/a' if x is None else f'{x:+.4%}'
    primary=None
    for name,fn in (('t1 (primary)',t1_of),('reaction day (report)',t0_of)):
        m=measure(seals,closes,fn)
        nl,no,diff,p,dec,(sl,so)=summary(m)
        primary=primary or dec
        out.append(f'{name}: look-first {nl}, other {no}; mean |AR| difference {pct(diff)}; one-sided p '
                   f'{"n/a" if p is None else f"{p:.4f}"}; signed mean AR look-first {pct(sl)}, other {pct(so)}; '
                   f'excluded no price {len(m["no_price"])} {m["no_price"]}, possible split {len(m["split"])} {m["split"]}')
    out.append(f'bars: at least {MIN_GROUP} per group, difference > 0, p <= {P_BAR:.2f} ({SHUFFLES} shuffles, seed {SEED})')
    out.append(f'decision: {primary}')
    return out


def cmd_score():
    if os.path.exists(OUT):
        print(f'already scored once ({OUT}):')
        with open(OUT,encoding='utf-8') as f:
            print(f.read().rstrip())
        return
    import duckdb
    from price_moves import load_closes
    seals,bad,missing,prefix=load_seals()
    symbols={r.get('symbol') for rows in seals.values() for r in rows if r.get('symbol')}
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        closes=load_closes(con,date.fromisoformat(FIRST_DAY)-timedelta(days=10),NEED_BAR+timedelta(days=10),symbols)
    finally:
        con.close()
    last=max((d for d,_ in closes.get(INDEX,[])),default=None)
    if last is None or last<NEED_BAR:
        raise SystemExit(f'INCOMPLETE: {INDEX} bars end {last}, need {NEED_BAR}; nothing scored')
    out=lines_for(seals,closes,bad,missing,prefix)
    with open(OUT,'w',encoding='utf-8') as f:
        f.write('\n'.join(out)+'\n')
    print('\n'.join(out))


def _self_test():
    import tempfile
    from forward_seal import seal
    n=0

    def ok(cond):
        nonlocal n
        assert cond
        n+=1

    # prices: Mon 16 .. Fri 20, Mon 23 .. Thu 26 Nov 2026; index flat except +1% on the 17th
    days=[date(2026,11,d) for d in (13,16,17,18,19,20,23,24,25,26)]

    def bars(moves):
        c,out=100.0,[]
        for d in days:
            c*=1+moves.get(d.day,0.0)
            out.append((d,c))
        return out
    closes={INDEX:bars({17:0.01}),'AAA':bars({17:0.06}),'BBB':bars({17:0.02}),'CCC':bars({17:0.30}),
            'DDD':bars({23:-0.04}),'EEE':bars({23:0.01})}
    row=lambda i,s,look,at:{'news_id':str(i),'symbol':s,'published_at':at,'look_first':look,'level':'high','score':5}
    seals={date(2026,11,16):[row(1,'AAA',True,'2026-11-16 10:00:00'),row(2,'BBB',False,'2026-11-16 19:30:00'),
                             row(3,'CCC',True,'2026-11-16 10:00:00'),row(4,'ZZZ',False,'2026-11-16 10:00:00'),
                             row(5,None,False,'2026-11-16 10:00:00')],
           date(2026,11,20):[row(6,'DDD',True,'2026-11-20 11:00:00'),row(7,'EEE',False,'2026-11-20 11:00:00')]}
    m=measure(seals,closes,t1_of)
    ok(m['no_price']==['4','5'] and m['split']==['3'])                       # no bars, no symbol; 30% jump
    ok([round(x,4) for x in m['look']]==[0.05,-0.04] and [round(x,4) for x in m['other']]==[0.01,0.01])
    ok(t1_of(date(2026,11,20),None,days)==date(2026,11,23) and t1_of(date(2026,11,21),None,days)==date(2026,11,23))
    ok(t1_of(date(2026,11,26),None,days) is None)                            # strictly after D
    m0=measure(seals,closes,t0_of)                                           # reaction day: same day before 18:00
    ok([round(x,4) for x in m0['look']]==[0.0,0.0,0.0] and [round(x,4) for x in m0['other']]==[0.01,0.0])   # CCC's jump is on t1, not t0
    ok(m0['split']==[] and m0['no_price']==['4','5'])
    ok(t0_of(None,{'published_at':'bozuk'},days) is None)

    # permutation test: deterministic, one-sided
    d1,p1=permutation_p([5.0,6.0,7.0,8.0,1.0,1.0,1.0,1.0],4)
    ok(d1==5.5 and p1==permutation_p([5.0,6.0,7.0,8.0,1.0,1.0,1.0,1.0],4)[1] and 0.005<p1<0.03)   # exact 1/70
    d2,p2=permutation_p([1.0,1.0,1.0,1.0,5.0,6.0,7.0,8.0],4)
    ok(d2==-5.5 and p2>0.97)
    ok(permutation_p([2.0,2.0,2.0,2.0],2)[1]==1.0)                           # ties count against the claim
    ok(decide(4,4,0.01,0.10)=='SUPPORTED' and decide(4,4,0.01,0.11)=='NOT_SUPPORTED' and decide(4,4,-0.01,0.01)=='NOT_SUPPORTED')
    ok(decide(3,9,0.05,0.01)=='TOO_FEW' and decide(9,3,0.05,0.01)=='TOO_FEW')
    nl,no,diff,p,dec,_=summary(m)
    ok((nl,no,dec)==(2,2,'TOO_FEW') and round(diff,4)==0.035)
    ok(summary({'look':[],'other':[0.01]})[2:5]==(None,None,'TOO_FEW'))

    big={date(2026,11,16):[row(i,'AAA',True,'2026-11-16 10:00:00') for i in range(4)]+
                          [row(10+i,'BBB',False,'2026-11-16 10:00:00') for i in range(4)]}
    out=lines_for(big,closes)
    ok(out[0].startswith('integrity: INTACT; sealed days 1') and out[-1]=='decision: SUPPORTED' and 'look-first 4, other 4' in out[1])
    ok(lines_for(seals,closes,bad=['2026-11-18'])[0].startswith("integrity: BROKEN; sealed days 2, dropped ['2026-11-18']"))
    ok(lines_for(seals,closes)[-1]=='decision: TOO_FEW')                     # the report pass never decides

    # integrity: a changed snapshot is dropped, a day without a seal is listed
    with tempfile.TemporaryDirectory() as tmp:
        sd,lg=os.path.join(tmp,'seals'),os.path.join(tmp,'log.jsonl')
        item=lambda i:{'news_id':str(i),'symbol':'AAA','published_at':'2026-11-16 10:00:00','importance':{'needs_review':False,'level':'high','score':5}}
        h,_=seal('2026-11-16',[item(1)],sd,lg)
        seal('2026-11-17',[item(2)],sd,lg)
        seal('2026-11-14',[item(3)],sd,lg)                                   # outside the window: ignored
        s,bad,missing,prefix=load_seals(sd,lg)
        ok(sorted(d.isoformat() for d in s)==['2026-11-16','2026-11-17'] and bad==[] and prefix['2026-11-16']==h)
        ok('2026-11-21' in missing and len(missing)==9 and s[date(2026,11,16)][0]['look_first'] is True)
        with open(os.path.join(sd,'2026-11-17.json'),'ab') as f:
            f.write(b' ')
        s,bad,missing,_=load_seals(sd,lg)
        ok(list(s)==[date(2026,11,16)] and bad==['2026-11-17'] and '2026-11-17' not in missing)
    print(f'self-test ok: {n} checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--self-test',action='store_true')
    g.add_argument('--score',action='store_true')
    args=ap.parse_args()
    _self_test() if args.self_test else cmd_score()


if __name__=='__main__':
    main()
