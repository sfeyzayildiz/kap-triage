'''Price reaction to disclosures and abnormal-move scan, from daily_bars.

Abnormal return = stock return - XU100 return (market-adjusted, close to close).
Prices are unadjusted, so a day with |stock return| > SPLIT_JUMP is treated as a
possible split or bonus issue: it is flagged, never explained.
Stdout shows only counts; details go to data/.

Usage:
  python -m kap_triage.analysis.prices --scan 2026-10-30
  python -m kap_triage.analysis.prices --reactions
'''
import argparse
import json
import statistics
from datetime import date, datetime, timedelta

import duckdb
from kap_triage.settings import settings

DB_PATH=settings.path('kap.duckdb')
INDEX='XU100'
CLOSE_HOUR=18  # published at or after 18:00 -> reaction on the next trading day
SPLIT_JUMP=0.22  # BIST daily limit is about 10%; larger moves are corporate actions
EST_DAYS=60
MIN_EST=30
Z_ABNORMAL=3.0
EVENT_DAYS=3  # t0, t0+1, t0+2
LOOKBACK_DAYS=4  # scan: disclosures up to this many calendar days before the move


def load_closes(con,start,end,symbols=None):
    '''{symbol: [(date, close), ...]} sorted by date, always including the index.'''
    sql='SELECT symbol,date,close FROM daily_bars WHERE date BETWEEN ? AND ?'
    params=[start,end]
    if symbols:
        wanted=sorted(set(symbols)|{INDEX})
        sql+=f' AND symbol IN ({",".join("?" for _ in wanted)})'
        params+=wanted
    series={}
    for sym,d,close in con.execute(sql+' ORDER BY symbol,date',params).fetchall():
        series.setdefault(sym,[]).append((d,close))
    return series


def daily_returns(points):
    return {d:c/p-1 for (_,p),(d,c) in zip(points,points[1:])}


def abnormal(stock,market):
    '''{date: (abnormal return, stock return)} on days both have a return.'''
    return {d:(r-market[d],r) for d,r in stock.items() if d in market}


def reaction_day(published_at,trading_days):
    '''First trading day on which the market could react.'''
    day=published_at.date()
    if published_at.hour>=CLOSE_HOUR:
        day+=timedelta(days=1)
    later=[d for d in trading_days if d>=day]
    return later[0] if later else None


def sigma_before(ar,day):
    '''Std of abnormal returns over the EST_DAYS trading days before day, split days left out.'''
    past=[a for d,(a,r) in sorted(ar.items()) if d<day and abs(r)<=SPLIT_JUMP][-EST_DAYS:]
    return (statistics.stdev(past),len(past)) if len(past)>=MIN_EST else (None,len(past))


def event_reaction(ar,trading_days,published_at):
    t0=reaction_day(published_at,trading_days)
    if t0 is None:
        return {'status':'too_early'}
    window=[d for d in trading_days if d>=t0][:EVENT_DAYS]
    if t0 not in ar:
        return {'status':'no_bar','t0':str(t0)}
    sigma,n_est=sigma_before(ar,t0)
    out={'status':'ok','t0':str(t0),'ar0':ar[t0][0],'n_est':n_est,
         'car':sum(ar[d][0] for d in window if d in ar),'car_days':sum(d in ar for d in window),
         'possible_split':any(abs(ar[d][1])>SPLIT_JUMP for d in window if d in ar)}
    out['z0']=out['ar0']/sigma if sigma else None
    if sigma is None:
        out['status']='short_history'
    return out


def scan(series,day):
    '''Abnormal moves on day: |z| >= Z_ABNORMAL, split days left out and counted.'''
    market=daily_returns(series.get(INDEX,[]))
    moves,splits=[],0
    for sym,points in series.items():
        if sym==INDEX:
            continue
        ar=abnormal(daily_returns(points),market)
        if day not in ar:
            continue
        a,r=ar[day]
        if abs(r)>SPLIT_JUMP:
            splits+=1
            continue
        sigma,_=sigma_before(ar,day)
        if sigma and abs(a/sigma)>=Z_ABNORMAL:
            moves.append({'symbol':sym,'date':str(day),'ar':a,'z':a/sigma})
    return moves,splits


def disclosures_before(con,symbol,day):
    '''News ids of the symbol's disclosures from LOOKBACK_DAYS before day up to day's close.'''
    end=datetime(day.year,day.month,day.day,CLOSE_HOUR)
    rows=con.execute('''SELECT news_id,kap_url,published_at FROM disclosures
        WHERE symbol=? AND published_at>=? AND published_at<? ORDER BY published_at''',
        [symbol,end-timedelta(days=LOOKBACK_DAYS),end]).fetchall()
    return [{'news_id':str(n),'kap_url':u,'published_at':str(p)} for n,u,p in rows]




def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--scan',type=date.fromisoformat,help='abnormal moves on this trading day')
    ap.add_argument('--reactions',action='store_true',help='reaction for every disclosure')
    args=ap.parse_args()
    if not (args.scan or args.reactions):
        ap.error('give --scan DATE, --reactions')

    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        if args.scan:
            series=load_closes(con,args.scan-timedelta(days=150),args.scan)
            moves,splits=scan(series,args.scan)
            for m in moves:
                m['disclosures']=disclosures_before(con,m['symbol'],args.scan)
            out_path=settings.path(f'moves_{args.scan}.jsonl')
            rows=moves
            explained=sum(bool(m['disclosures']) for m in moves)
            summary=f'symbols={len(series)-1} abnormal={len(moves)} with_disclosure={explained} split_days_skipped={splits}'
        else:
            disc=con.execute('SELECT news_id,kap_url,symbol,published_at FROM disclosures ORDER BY published_at').fetchall()
            first,last=disc[0][3].date(),disc[-1][3].date()
            series=load_closes(con,first-timedelta(days=150),last+timedelta(days=10))
            trading_days=[d for d,_ in series.get(INDEX,[])]
            market=daily_returns(series.get(INDEX,[]))
            cache,rows={},[]
            for news_id,url,sym,published in disc:
                if sym not in series:
                    rows.append({'news_id':str(news_id),'kap_url':url,'symbol':sym,'status':'no_symbol_bars'})
                    continue
                if sym not in cache:
                    cache[sym]=abnormal(daily_returns(series[sym]),market)
                rows.append({'news_id':str(news_id),'kap_url':url,'symbol':sym,
                             **event_reaction(cache[sym],trading_days,published)})
            out_path=settings.path('reactions.jsonl')
            status={}
            for r in rows:
                status[r['status']]=status.get(r['status'],0)+1
            summary=f'disclosures={len(rows)} '+' '.join(f'{k}={v}' for k,v in sorted(status.items()))+\
                    f' possible_split={sum(bool(r.get("possible_split")) for r in rows)}'
    finally:
        con.close()
    with open(out_path,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(f'{summary} -> {out_path}')


if __name__=='__main__':
    main()
