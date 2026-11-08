'''Collect sector labels from Matriks into DuckDB (table symbol_sectors).

Two requests, done in the same session as the ~12 Nov price refresh (the day's only pull):
  v4/meta/symbols.gz?symbolType=S   stocks: sC (symbol), seI (sector id), seC (sector code)
  v4/meta/sectors.gz                sector names: sI, sC, d (Turkish), de (English)
Docs read on 2026-11-09 (analistdocs.matriksdata.com, Meta Veriler); approved by Matriks (CLAUDE.md).

Steps, so a parse fix never needs a second pull:
  --pull --yes  two requests, raw JSON saved to data/raw_meta/
  --load        raw files -> symbol_sectors for the symbols that have disclosures (no network)
Stdout: counts only.

Usage:
  python scripts/sector_collect.py --self-test
  python scripts/sector_collect.py --plan
  python scripts/sector_collect.py --pull --yes
  python scripts/sector_collect.py --load
'''
import argparse
import json
import os
import sys
import time
from datetime import datetime

from price_collect import API, DB_PATH, decode, in_collection_window

RAW_DIR='data/raw_meta'
REQUESTS={'symbols':('v4/meta/symbols.gz',{'symbolType':'S'}),'sectors':('v4/meta/sectors.gz',{})}
MIN_INTERVAL=1.1

SCHEMA='''CREATE OR REPLACE TABLE symbol_sectors (
    symbol VARCHAR PRIMARY KEY, sector_id INTEGER, sector VARCHAR, sector_name VARCHAR, sector_name_en VARCHAR)'''


def sector_rows(symbols,sectors,wanted):
    '''Rows (symbol, sector_id, sector_code, name_tr, name_en) for wanted symbols.
    Returns (rows, counts). A symbol listed twice keeps its non-deleted entry; the sector code
    comes from seC, or from the sector list when seC is empty.'''
    names={s.get('sI'):s for s in sectors}
    best={}
    for s in symbols:
        code=s.get('sC')
        if code not in wanted or s.get('sT') not in (None,'S'):
            continue
        if code not in best or (best[code].get('d') and not s.get('d')):
            best[code]=s
    rows=[]
    no_sector=0
    for code in sorted(best):
        s=best[code]
        sid=s.get('seI')
        meta=names.get(sid,{})
        sector=s.get('seC') or meta.get('sC')
        if sid is None and not sector:
            no_sector+=1
            continue
        rows.append((code,sid,sector,meta.get('d'),meta.get('de')))
    counts={'wanted':len(wanted),'found':len(best),'missing':len(wanted-set(best)),'no_sector':no_sector,
            'with_sector':len(rows),'sectors':len({r[2] for r in rows})}
    return rows,counts


def disclosure_symbols():
    import duckdb
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        return {r[0] for r in con.execute('SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL').fetchall()}
    finally:
        con.close()


def pull():
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    headers={'Authorization':f'jwt {os.environ["KAP_TOKEN"]}'}
    os.makedirs(RAW_DIR,exist_ok=True)
    for name,(path,params) in REQUESTS.items():
        time.sleep(MIN_INTERVAL)
        resp=requests.get(f'{API}/{path}',params=params,headers=headers,timeout=60)
        if resp.status_code!=200:
            sys.exit(f'{name}: HTTP {resp.status_code}, stopped')
        data=decode(resp.content)
        with open(f'{RAW_DIR}/{name}.json','w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False)
        print(f'{name}: {len(data)} records -> {RAW_DIR}/{name}.json')


def load():
    import duckdb
    with open(f'{RAW_DIR}/symbols.json',encoding='utf-8') as f:
        symbols=json.load(f)
    with open(f'{RAW_DIR}/sectors.json',encoding='utf-8') as f:
        sectors=json.load(f)
    rows,counts=sector_rows(symbols,sectors,disclosure_symbols())
    con=duckdb.connect(DB_PATH)
    try:
        con.execute(SCHEMA)
        if rows:
            con.executemany('INSERT INTO symbol_sectors VALUES (?,?,?,?,?)',rows)
        n=con.execute('SELECT count(*) FROM symbol_sectors').fetchall()[0][0]
    finally:
        con.close()
    print(' '.join(f'{k}={v}' for k,v in counts.items())+f' table_rows={n}')


def _self_test():
    symbols=[{'sC':'AAA','sT':'S','seI':1,'seC':'GIDA','d':False},
             {'sC':'BBB','sT':'S','seI':2,'seC':'','d':False},          # code from the sector list
             {'sC':'CCC','sT':'S','d':False},                            # no sector at all
             {'sC':'DDD','sT':'S','seI':1,'seC':'GIDA','d':True},
             {'sC':'DDD','sT':'S','seI':2,'seC':'DOKUMA','d':False},     # active entry wins
             {'sC':'XU100','sT':'I','seI':9,'seC':'X'},                  # not a stock
             {'sC':'ZZZ','sT':'S','seI':1,'seC':'GIDA'}]                 # not wanted
    sectors=[{'sI':1,'sC':'GIDA','d':'Gıda','de':'Food'},{'sI':2,'sC':'DOKUMA','d':'Dokuma','de':'Textile'}]
    rows,c=sector_rows(symbols,sectors,{'AAA','BBB','CCC','DDD','XU100','EEE'})
    assert rows==[('AAA',1,'GIDA','Gıda','Food'),('BBB',2,'DOKUMA','Dokuma','Textile'),('DDD',2,'DOKUMA','Dokuma','Textile')]
    assert c=={'wanted':6,'found':4,'missing':2,'no_sector':1,'with_sector':3,'sectors':2}
    assert REQUESTS['symbols'][1]=={'symbolType':'S'} and len(REQUESTS)==2
    import duckdb
    con=duckdb.connect()
    con.execute(SCHEMA)
    con.executemany('INSERT INTO symbol_sectors VALUES (?,?,?,?,?)',rows)
    assert con.execute('SELECT count(*) FROM symbol_sectors').fetchall()[0][0]==3
    con.close()
    print('self-test ok: 4 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--plan',action='store_true',help='show what a pull would do, no network')
    ap.add_argument('--pull',action='store_true',help='two requests to Matriks')
    ap.add_argument('--yes',action='store_true')
    ap.add_argument('--load',action='store_true',help='raw files -> symbol_sectors, no network')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    if not (args.plan or args.pull or args.load):
        ap.error('give --plan, --pull --yes, --load or --self-test')
    if in_collection_window(datetime.now()):
        sys.exit('nightly collection window (23:30-23:59), try later')
    if args.plan:
        print(f'requests=2 ({", ".join(p for p,_ in REQUESTS.values())}) disclosure_symbols={len(disclosure_symbols())}')
    if args.pull:
        if not args.yes:
            sys.exit('add --yes to pull; do it in the same session as the price refresh')
        pull()
    if args.load:
        load()


if __name__=='__main__':
    main()
