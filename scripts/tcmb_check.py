'''Official TCMB rates through the registry MCP server tcmb-mcp 0.1.2 (rule: docs/tcmb_rule.md).

Part 1 --check: Matriks' tcmb_ex_rt vs TCMB forex buying (bulletin of the record's date, else the latest
before it, up to 7 days); match within 0.5%; decision at 95%. Part 2 report (same run, no LLM): the borrowed
rate of importance.fx_rate vs the TCMB rate on Set C run 1 / Set D run a FX outputs.
Each day is fetched once (data/tcmb_cache/, at most 1 request per second); only a date leaves the machine.
Stdout: counts and ids only; details to /tmp/tcmb_mismatches.txt.

Usage:
  python scripts/tcmb_check.py --self-test
  python scripts/tcmb_check.py --plan      # how many days still need a request (no network)
  python scripts/tcmb_check.py --check
'''
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import date, timedelta

CACHE='data/tcmb_cache'
DB='data/kap.duckdb'
REPORT='/tmp/tcmb_mismatches.txt'
LOOKBACK=7
TOL=0.005
BAR=0.95
MIN_GAP=1.0
OUTPUTS=('data/eval_set_c.jsonl','data/set_d_run_a.jsonl')


def cache_path(day,cache=CACHE):
    return os.path.join(cache,f'{day.isoformat()}.json')


def read_cache(day,cache=CACHE):
    '''{'rates': {code: {...}}} for a bulletin day, {'none': True} for a day without one, None if not fetched.'''
    p=cache_path(day,cache)
    if not os.path.exists(p):
        return None
    with open(p,encoding='utf-8') as f:
        return json.load(f)


def parse_answer(text):
    '''tcmb_get_rates_on JSON -> cache entry; a missing bulletin -> {'none': True}; other errors -> raise.'''
    d=json.loads(text)
    if 'error' in d:
        if 'no bulletin' in d['error']:
            return {'none':True}
        raise RuntimeError(d['error'][:120])
    return {'date':d.get('date'),'rates':{r['code'].upper():{'unit':r.get('unit') or 1,'buy':r.get('forex_buying'),
                                                             'sell':r.get('forex_selling')} for r in d['rates']}}


def per_unit(entry,code,side='buy'):
    r=(entry or {}).get('rates',{}).get(code.upper())
    if not r or not r.get(side):
        return None
    return r[side]/(r.get('unit') or 1)


def bulletin_for(day,get,lookback=LOOKBACK):
    '''(bulletin day, entry): the bulletin dated day, else the latest one before it (up to lookback days).'''
    for k in range(lookback+1):
        d=day-timedelta(days=k)
        e=get(d)
        if e and not e.get('none'):
            return d,e
    return None,None


def rate_on(code,day,get,side='buy',previous=False):
    '''TCMB rate per unit for code on day (rule convention); previous=True uses the previous business day's bulletin.'''
    b,e=bulletin_for(day,get)
    if previous and b is not None:
        b,e=bulletin_for(b-timedelta(days=1),get)
    return per_unit(e,code,side) if e else None


def rel(a,b):
    return abs(a/b-1)


def decide(n_match,n_checked):
    return 'MATRIKS_RATE_AGREES' if n_checked and n_match/n_checked>=BAR else 'MATRIKS_RATE_DIFFERS'


class Fetcher:
    '''One stdio session to tcmb-mcp; cache first; polite pacing.'''

    def __init__(self,session,cache=CACHE):
        self.s,self.cache,self.last,self.requests=session,cache,0.0,0

    async def get(self,day):
        e=read_cache(day,self.cache)
        if e is not None:
            return e
        wait=MIN_GAP-(time.time()-self.last)
        if wait>0:
            await asyncio.sleep(wait)
        self.last=time.time()
        self.requests+=1
        res=await self.s.call_tool('tcmb_get_rates_on',{'date':day.isoformat()})
        e=parse_answer(''.join(getattr(c,'text','') for c in res.content or []))
        os.makedirs(self.cache,exist_ok=True)
        with open(cache_path(day,self.cache),'w',encoding='utf-8') as f:
            json.dump(e,f)
        return e


async def with_server(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=sys.executable,args=['-m','tcmb_mcp.server'],env={'PATH':os.environ.get('PATH','')})
    with open(os.devnull,'w') as devnull:
        async with stdio_client(params,errlog=devnull) as (r,w):
            async with ClientSession(r,w) as s:
                await s.initialize()
                return await fn(Fetcher(s))


async def prefetch(days,fetcher):
    '''Fetch every day a bulletin lookup may touch (day and up to LOOKBACK+8 days before), cache-first.'''
    need=sorted({d-timedelta(days=k) for d in days for k in range(LOOKBACK+9)},reverse=True)
    t0=time.time()
    for k,d in enumerate(need,1):
        await fetcher.get(d)
        if fetcher.requests and fetcher.requests%50==0 and read_cache(d) is not None:
            print(f'  fetched {fetcher.requests} ({time.time()-t0:.0f} s), {k}/{len(need)} days looked at',flush=True)
    return len(need)


def matriks_records():
    import duckdb
    con=duckdb.connect(DB,read_only=True)
    try:
        return con.execute('''SELECT url,date,trim(upper(cur)),tcmb_ex_rt FROM new_business
            WHERE tcmb_ex_rt>0 AND trim(upper(cur)) NOT IN ('TRY','TL') ORDER BY date''').fetchall()
    finally:
        con.close()


def fx_outputs():
    '''(news_id, published day, amount, currency) of FX amounts in Set C run 1 and Set D run a.'''
    import duckdb
    from eval_vs_matriks import norm_cur
    con=duckdb.connect(DB,read_only=True)
    try:
        pub={str(n):(d,s) for n,d,s in con.execute('SELECT news_id,CAST(published_at AS DATE),symbol FROM disclosures').fetchall()}
    finally:
        con.close()
    out=[]
    for path in OUTPUTS:
        if not os.path.exists(path):
            continue
        with open(path,encoding='utf-8') as f:
            for l in f:
                r=json.loads(l)
                c=norm_cur(r.get('llm_cur'))
                if r.get('llm_amount') is not None and c not in (None,'TRY') and str(r['news_id']) in pub:
                    d,s=pub[str(r['news_id'])]
                    out.append((str(r['news_id']),d,s,float(r['llm_amount']),c,path))
    return out


def part1(records,get):
    '''Counts for the check; rows for the /tmp report.'''
    c={'records':len(records),'checked':0,'match':0,'match_sell':0,'match_prev':0,'no_tcmb':0}
    diffs,bad,rows=[],{},[]
    for url,d,cur,m in records:
        t=rate_on(cur,d,get)
        if t is None:
            c['no_tcmb']+=1
            continue
        c['checked']+=1
        x=rel(m,t)
        diffs.append(x)
        ok=x<=TOL
        c['match']+=ok
        s=rate_on(cur,d,get,'sell')
        p=rate_on(cur,d,get,previous=True)
        c['match_sell']+=bool(s and rel(m,s)<=TOL)
        c['match_prev']+=bool(p and rel(m,p)<=TOL)
        if not ok:
            k=f'{cur} {d.year}'
            bad[k]=bad.get(k,0)+1
            rows.append((url,str(d),cur,m,t,s,p))
    return c,diffs,bad,rows


def part2(outputs,get):
    '''Borrowed Matriks rate (importance.fx_rate) vs TCMB on the disclosure date; level changes.'''
    import duckdb
    from importance import company_baseline, fx_rate, score
    con=duckdb.connect(DB,read_only=True)
    out={'fx_items':len(outputs),'no_borrowed':0,'filled':0,'compared':0,'level_changes':0,'diffs':[]}
    try:
        for nid,d,sym,amt,cur,_ in outputs:
            b=fx_rate(con,cur,d)
            t=rate_on(cur,d,get)
            if b is None:
                out['no_borrowed']+=1
                out['filled']+=t is not None
                continue
            if t is None:
                continue
            out['compared']+=1
            out['diffs'].append(rel(b,t))
            base,n=company_baseline(con,sym,d)
            r={'amount':amt,'currency':cur}
            out['level_changes']+=score(r,b,base,n)['level']!=score(r,t,base,n)['level']
    finally:
        con.close()
    return out


def cmd_plan():
    days={d for _,d,_,_ in matriks_records()}|{d for _,d,*_ in fx_outputs()}
    need={d-timedelta(days=k) for d in days for k in range(LOOKBACK+9)}
    todo=sum(read_cache(d) is None for d in need)
    print(f'record days {len(days)}, days to look at {len(need)}, not cached {todo} (~{todo*MIN_GAP/60:.0f} min at 1 request/s)')


def cmd_check():
    records=matriks_records()
    outputs=fx_outputs()
    days={d for _,d,_,_ in records}|{d for _,d,*_ in outputs}

    async def run(fetcher):
        n=await prefetch(days,fetcher)
        return n,fetcher.requests
    n_days,n_req=asyncio.run(with_server(run))
    print(f'days looked at {n_days}, new requests {n_req}')
    get=lambda d:read_cache(d)
    c,diffs,bad,rows=part1(records,get)
    q=lambda xs,p:sorted(xs)[min(len(xs)-1,int(p*len(xs)))] if xs else float('nan')
    print(f'Part 1: records {c["records"]}, checked {c["checked"]}, currency not in TCMB bulletin {c["no_tcmb"]}')
    print(f'  match forex buying (primary, <= {TOL:.1%}) {c["match"]}/{c["checked"]} ({c["match"]/max(c["checked"],1):.1%}; bar {BAR:.0%})')
    print(f'  reported: forex selling {c["match_sell"]}/{c["checked"]}, previous business day {c["match_prev"]}/{c["checked"]}; '
          f'relative difference median {statistics.median(diffs) if diffs else float("nan"):.4%}, p95 {q(diffs,0.95):.4%}')
    print(f'  mismatches by currency/year: {dict(sorted(bad.items()))}')
    with open(REPORT,'w',encoding='utf-8') as f:
        f.write('url\tdate\tcur\tmatriks\ttcmb_buy\ttcmb_sell\ttcmb_prev_buy\n')
        for r in rows:
            f.write('\t'.join(str(x) for x in r)+'\n')
    print(f'  mismatch details: {REPORT} ({len(rows)} rows; not for this chat)')
    p=part2(outputs,get)
    ds=p['diffs']
    print(f'Part 2 report: FX outputs {p["fx_items"]} (Set C run 1 + Set D run a); no borrowed Matriks rate {p["no_borrowed"]}, '
          f'filled by TCMB {p["filled"]}; compared {p["compared"]}: borrowed vs TCMB median {statistics.median(ds) if ds else float("nan"):.3%}, '
          f'max {max(ds) if ds else float("nan"):.3%}; importance level changes {p["level_changes"]}')
    d=decide(c['match'],c['checked'])
    print(f'decision: {d}; gap filling {"ADOPT_FILL (wire on 26 Nov)" if d=="MATRIKS_RATE_AGREES" else "FILL_OFF"}')


def tcmb_rate(code,day,cache=CACHE):
    '''Sync helper for importance.fx_rate's fallback: TCMB forex buying per unit (rule convention), None on failure.'''
    try:
        if bulletin_for(day,lambda d:read_cache(d,cache))[0] is None:
            async def run(fetcher):
                for k in range(LOOKBACK+1):
                    e=await fetcher.get(day-timedelta(days=k))
                    if not e.get('none'):
                        return
            asyncio.run(with_server(run))
        return rate_on(code,day,lambda d:read_cache(d,cache))
    except Exception:
        return None


def _self_test():
    import tempfile
    xml_answer=json.dumps({'date':'13.11.2026','rates':[{'code':'USD','unit':1,'forex_buying':42.0,'forex_selling':42.1},
                                                        {'code':'JPY','unit':100,'forex_buying':27.5,'forex_selling':27.7}]})
    e=parse_answer(xml_answer)
    assert per_unit(e,'usd')==42.0 and abs(per_unit(e,'JPY')-0.275)<1e-12 and per_unit(e,'GBP') is None
    assert parse_answer(json.dumps({'error':'no bulletin for that date (TCMB publishes on business days only)'}))=={'none':True}
    try:
        parse_answer(json.dumps({'error':'TCMB returned HTTP 500'}))
        raise AssertionError('should raise')
    except RuntimeError:
        pass
    fri,sat,sun,mon=date(2026,11,13),date(2026,11,14),date(2026,11,15),date(2026,11,16)
    store={fri:e,sat:{'none':True},sun:{'none':True},
           mon:{'rates':{'USD':{'unit':1,'buy':43.0,'sell':43.1}}},date(2026,11,12):{'rates':{'USD':{'unit':1,'buy':41.0,'sell':41.1}}}}
    get=store.get
    assert bulletin_for(sun,get)==(fri,e) and rate_on('USD',sun,get)==42.0                 # weekend -> Friday
    assert rate_on('USD',mon,get)==43.0 and rate_on('USD',mon,get,previous=True)==42.0      # previous business day
    assert rate_on('USD',mon,get,'sell')==43.1 and rate_on('USD',date(2026,1,1),get) is None
    recs=[('u1',fri,'USD',42.1),('u2',sun,'USD',42.0),('u3',mon,'USD',45.0),('u4',mon,'XAU',1.0)]
    c,diffs,bad,rows=part1(recs,get)
    assert (c['checked'],c['match'],c['no_tcmb'])==(3,2,1) and bad=={'USD 2026':1} and [r[0] for r in rows]==['u3']
    assert decide(95,100)=='MATRIKS_RATE_AGREES' and decide(94,100)=='MATRIKS_RATE_DIFFERS' and decide(0,0)=='MATRIKS_RATE_DIFFERS'
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(tmp,exist_ok=True)
        with open(cache_path(fri,tmp),'w') as f:
            json.dump(e,f)
        for d in (sat,sun):
            with open(cache_path(d,tmp),'w') as f:
                json.dump({'none':True},f)
        assert tcmb_rate('USD',sun,cache=tmp)==42.0                                          # cached: no server started
    print('self-test ok: 14 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    for a in ('self-test','plan','check'):
        g.add_argument(f'--{a}',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.plan:
        cmd_plan()
    else:
        cmd_check()


if __name__=='__main__':
    main()
