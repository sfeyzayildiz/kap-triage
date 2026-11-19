'''Two-run disagreement count in the saved nightly lists (docs/known_issues.md A12; report only, no decision).

Set D measured the two-run flag with two separate processes of 50 texts; live it is a second reading in the
same nightly process. This counts, for each saved morning list data/morning_<day>.jsonl in the window, how
many disclosures carry `two_run_disagree` (the second reading gave another amount or currency, or the second
call failed) and how many carry `run_error`. Days without a saved list are listed by date.
Stdout shows only days and counts, never a disclosure field.

Usage:
  python scripts/two_run_count.py --start 2026-11-15 --end 2026-11-23
  python scripts/two_run_count.py --self-test
'''
import argparse
import json
import os
import sys
import tempfile
from datetime import date, timedelta

from pipeline import RUN_ERROR, TWO_RUN

DATA_DIR='data'


def count(start,end,data_dir=DATA_DIR):
    '''([(day, items, two_run, run_error)], [days without a saved list]) for start..end inclusive.'''
    rows,missing=[],[]
    d=start
    while d<=end:
        path=os.path.join(data_dir,f'morning_{d}.jsonl')
        if not os.path.exists(path):
            missing.append(str(d))
        else:
            with open(path,encoding='utf-8') as f:
                reasons=[set(json.loads(l).get('needs_review_reasons') or []) for l in f if l.strip()]
            rows.append((str(d),len(reasons),sum(TWO_RUN in r for r in reasons),sum(RUN_ERROR in r for r in reasons)))
        d+=timedelta(days=1)
    return rows,missing


def report(rows,missing):
    for day,n,t,e in rows:
        print(f'{day} items={n} {TWO_RUN}={t} {RUN_ERROR}={e}')
    n,t,e=(sum(r[i] for r in rows) for i in (1,2,3))
    print(f'lists={len(rows)} items={n} {TWO_RUN}={t} {RUN_ERROR}={e} no_list={len(missing)}'
          +(f' ({", ".join(missing)})' if missing else ''))


def _self_test():
    with tempfile.TemporaryDirectory() as tmp:
        def write(day,items):
            with open(os.path.join(tmp,f'morning_{day}.jsonl'),'w',encoding='utf-8') as f:
                for i in items:
                    f.write(json.dumps(i)+'\n')
        write('2026-11-15',[])
        write('2026-11-16',[{'needs_review_reasons':[TWO_RUN,'currency_unclear']},
                            {'needs_review_reasons':[RUN_ERROR]},{'needs_review_reasons':[]},{}])
        write('2026-11-18',[{'needs_review_reasons':[TWO_RUN,TWO_RUN]}])
        write('2026-11-20',[{'needs_review_reasons':[TWO_RUN]}])   # outside the window
        rows,missing=count(date(2026,11,15),date(2026,11,18),tmp)
        assert rows==[('2026-11-15',0,0,0),('2026-11-16',4,1,1),('2026-11-18',1,1,0)],rows
        assert missing==['2026-11-17'],missing
        rows,missing=count(date(2026,11,21),date(2026,11,21),tmp)
        assert rows==[] and missing==['2026-11-21']
    print('two_run_count self-test: 4/4 checks passed')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--start',type=date.fromisoformat)
    ap.add_argument('--end',type=date.fromisoformat)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    if not args.start or not args.end:
        sys.exit('--start and --end are required')
    report(*count(args.start,args.end))


if __name__=='__main__':
    main()
