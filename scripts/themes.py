'''Weekly themes from the evaluated clustering (data/clusters.json, k=27, docs/clustering_rule.md).

Clusters reflect sector beyond chance but weakly, and follow the company more than the sector
(template effect, PROJECT_NOTES 2026-11-11); the panel page states this. Desk routing stays on the
Matriks sector label. No LLM, no network. Stdout prints counts only (theme words are never printed).

Usage:
  python scripts/themes.py --self-test
  python scripts/themes.py --weeks        # counts only
'''
import argparse
import json
import os
from collections import Counter
from datetime import date, timedelta

CLUSTERS='data/clusters.json'
DB_PATH='data/kap.duckdb'


def week_start(day):
    d=date.fromisoformat(str(day)[:10])
    return d-timedelta(days=d.weekday())


def load_clusters(path=CLUSTERS):
    if not os.path.exists(path):
        return None
    with open(path,encoding='utf-8') as f:
        return json.load(f)


def n_weeks(assign):
    starts=[week_start(a['published_at']) for a in assign]
    return (max(starts)-min(starts)).days//7+1 if starts else 0


def profile(assign):
    '''cluster -> {'n': docs, 'companies': distinct symbols} over the whole period.'''
    out={}
    for a in assign:
        p=out.setdefault(a['cluster'],{'n':0,'symbols':set()})
        p['n']+=1
        p['symbols'].add(a['symbol'])
    return {c:{'n':p['n'],'companies':len(p['symbols'])} for c,p in out.items()}


def weeks(assign):
    '''[(week start, docs)] newest first.'''
    c=Counter(str(week_start(a['published_at'])) for a in assign)
    return sorted(c.items(),reverse=True)


def last_clustered(assign):
    return max((a['published_at'] for a in assign),default=None)


def week_view(out,start):
    '''Clusters present in the week starting on start (a Monday), most docs first.'''
    assign=out['assign']
    start=str(start)
    end=str(date.fromisoformat(start)+timedelta(days=7))
    rows=[a for a in assign if start<=a['published_at'][:10]<end]
    prof=profile(assign)
    total_weeks=n_weeks(assign) or 1
    groups={}
    for a in sorted(rows,key=lambda a:a['published_at']):
        groups.setdefault(a['cluster'],[]).append(a)
    view=[]
    for c,items in groups.items():
        avg=prof[c]['n']/total_weeks
        view.append({'cluster':c,'n':len(items),'words':out['themes'].get(str(c),[]),
                     'companies_week':len({a['symbol'] for a in items}),'companies_all':prof[c]['companies'],
                     'avg_per_week':avg,'ratio':len(items)/avg if avg else None,'items':items})
    return sorted(view,key=lambda v:(-v['n'],-(v['ratio'] or 0),v['cluster']))


def load_meta(news_ids):
    '''news_id -> kap_url (one short read).'''
    import duckdb
    if not news_ids or not os.path.exists(DB_PATH):
        return {}
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        marks=','.join('?' for _ in news_ids)
        return {str(n):u for n,u in con.execute(f'SELECT news_id,kap_url FROM disclosures WHERE news_id IN ({marks})',
                                                 list(news_ids)).fetchall()}
    finally:
        con.close()


def count_after(day):
    '''Disclosures published after day (not in the clustering).'''
    import duckdb
    if not day or not os.path.exists(DB_PATH):
        return 0
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        return con.execute('SELECT count(*) FROM disclosures WHERE published_at>CAST(? AS TIMESTAMP)',[day]).fetchall()[0][0]
    finally:
        con.close()


def _self_test():
    assert week_start('2026-11-12 09:30:00')==date(2026,11,9) and week_start('2026-11-09')==date(2026,11,9)
    assign=[{'news_id':'1','symbol':'AAA','published_at':'2026-11-02 09:00:00','cluster':0},
            {'news_id':'2','symbol':'BBB','published_at':'2026-11-03 10:00:00','cluster':0},
            {'news_id':'3','symbol':'AAA','published_at':'2026-11-10 09:00:00','cluster':0},
            {'news_id':'4','symbol':'CCC','published_at':'2026-11-11 09:00:00','cluster':1},
            {'news_id':'5','symbol':'CCC','published_at':'2026-11-12 08:00:00','cluster':1},
            {'news_id':'6','symbol':'DDD','published_at':'2026-11-13 08:00:00','cluster':2}]
    out={'k':3,'themes':{'0':['savunma','teslimat'],'1':[],'2':['enerji']},'assign':assign}
    assert n_weeks(assign)==2 and n_weeks([])==0
    assert profile(assign)=={0:{'n':3,'companies':2},1:{'n':2,'companies':1},2:{'n':1,'companies':1}}
    assert weeks(assign)==[('2026-11-09',4),('2026-11-02',2)]
    assert last_clustered(assign)=='2026-11-13 08:00:00' and last_clustered([]) is None
    v=week_view(out,'2026-11-09')
    assert [x['cluster'] for x in v]==[1,2,0]  # 2 docs first; then 1 doc each, higher ratio first (2: 1/0.5, 0: 1/1.5)
    assert v[0]['n']==2 and v[0]['companies_week']==1 and v[0]['companies_all']==1 and v[0]['words']==[]
    assert v[2]['words']==['savunma','teslimat'] and abs(v[2]['avg_per_week']-1.5)<1e-9 and abs(v[1]['ratio']-2)<1e-9
    assert [a['news_id'] for a in v[0]['items']]==['4','5']  # oldest first
    assert week_view(out,'2026-10-26')==[]
    print('self-test ok: 10 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--weeks',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.weeks:
        out=load_clusters()
        if out is None:
            raise SystemExit(f'{CLUSTERS} missing: python scripts/clusters.py --build --k 27')
        w=weeks(out['assign'])
        last=last_clustered(out['assign'])
        print(f'k={out["k"]} docs={len(out["assign"])} weeks with docs={len(w)} span weeks={n_weeks(out["assign"])} '
              f'last clustered={last[:10] if last else None} not clustered after it={count_after(last)}')
    else:
        ap.error('give --weeks or --self-test')


if __name__=='__main__':
    main()
