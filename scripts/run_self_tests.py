'''Run every module self-test; exit 1 if any fails. Used locally and by CI.

Self-tests use only in-memory data: no data/ files, no .env, no network, no Ollama.
A module that needs one of those is listed in SKIP with the reason.

Usage:
  python scripts/run_self_tests.py
  python scripts/run_self_tests.py --skip daily_collect
'''
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent

# module -> extra args ('' means the self-test runs with no arguments)
TESTS={
    'currency_check':'',
    'amount_checks':'',
    'normalize':'',
    'pipeline':'--self-test',
    'importance':'--self-test',
    'price_moves':'--self-test',
    'morning':'--self-test',
    'rag_index':'--self-test',
    'agent':'--self-test',
    'eval_retrieval':'--self-test',
    'latency':'--self-test',
    'corpus_stats':'--self-test',
    'demo_candidates':'--self-test',
    'sample_set_c':'--self-test',
    'label_set_b':'--self-test',
    'write_questions':'--self-test',
    'morning_job':'--self-test',
    'clusters':'--self-test',
    'sector_collect':'--self-test',
    'injection_test':'--self-test',
    'injection_checks':'--self-test',
    'matriks_crosscheck':'--self-test',
    'price_collect':'--self-test',
    'prod_refresh':'--self-test',
    'daily_collect':'--self-test',
}
SKIP={}


def main():
    # --skip NAME[,NAME]: Claude skips daily_collect locally (CLAUDE.md: Claude does not run it); CI runs all
    skip=dict(SKIP)
    if '--skip' in sys.argv:
        for name in sys.argv[sys.argv.index('--skip')+1].split(','):
            skip[name]='--skip'
    failed=[]
    for name,arg in TESTS.items():
        if name in skip:
            print(f'{name:16} SKIP ({skip[name]})')
            continue
        cmd=[sys.executable,str(HERE/f'{name}.py')]+([arg] if arg else [])
        t0=time.time()
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
        lines=[l for l in p.stdout.strip().splitlines() if l.strip()]
        last=lines[-1] if lines else ''
        status='ok' if p.returncode==0 else f'FAIL exit {p.returncode}'
        print(f'{name:16} {status:12} {time.time()-t0:5.1f}s  {last[:70]}')
        if p.returncode!=0:
            failed.append(name)
            err=[l for l in p.stderr.strip().splitlines() if l.strip()]
            if err:
                # last error line only: tracebacks name the exception, never data values
                print(f'{"":16} {err[-1][:150]}')
    print(f'{len(TESTS)-len(skip)-len(failed)} passed, {len(failed)} failed, {len(skip)} skipped')
    sys.exit(1 if failed else 0)


if __name__=='__main__':
    main()
