'''Run every module self-test; exit 1 if any fails. Used locally and by CI.

Self-tests use only in-memory data: no data/ files, no .env, no network, no Ollama.
A module that needs one of those is listed in SKIP with the reason.
Modules live in scripts/ (the system) or experiments/ (evaluations, labeling, pilots; moved there
unchanged on 21 Nov). Experiments import system modules by name, so scripts/ is put on PYTHONPATH.

Usage:
  python scripts/run_self_tests.py
  python scripts/run_self_tests.py --skip daily_collect
'''
import os
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
EXPERIMENTS=HERE.parent/'experiments'

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
    'pull_guard':'--self-test',
    'injection_test':'--self-test',
    'injection_checks':'--self-test',
    'matriks_crosscheck':'--self-test',
    'source_check':'--self-test',
    'themes':'--self-test',
    'reliability':'--self-test',
    'price_chart':'--self-test',
    'form':'--self-test',
    'panel':'--self-test',
    'chat':'--self-test',
    'demo_mode':'--self-test',
    'demo_leak_check':'--self-test',
    'answer':'--self-test',
    'eval_answers':'--self-test',
    'regex_baseline':'--self-test',
    'build_chunks':'--self-test',
    'brief_eval':'--self-test',
    'scope_eval':'--self-test',
    'periods':'--self-test',
    'period_eval':'--self-test',
    'desk_mail':'--self-test',
    'fields_eval':'--self-test',
    'drift_check':'--self-test',
    'forward_seal':'--self-test',
    'forward_score':'--self-test',
    'two_run_count':'--self-test',
    'amount_checks_v2':'',
    'sample_set_d':'--self-test',
    'set_d':'--self-test',
    'vendor_audit':'--self-test',
    'mail_mcp':'--self-test',
    'tcmb_check':'--self-test',
    'capital_form':'--self-test',
    'capital_checks':'--self-test',
    'capital_score':'--self-test',
    'capital_collect':'--self-test',
    'capital_profile':'--self-test',
    'sample_capital':'--self-test',
    'label_capital':'--self-test',
    'capital_extract':'--self-test',
    'mcp_server':'--self-test',
    'mcp_client':'--self-test',
    'mcp_agent':'--self-test',
    'repeat_check':'--self-test',
    'desk_route_check':'--self-test',
    'importance_check':'--self-test',
    'write_negatives':'--self-test',
    'revenue_check':'--self-test',
    'deploy_check':'--self-test',
    'route_eval':'--self-test',
    'card_eval':'--self-test',
    'names':'--self-test',
    'v2_eval':'--self-test',
    'quantities':'--self-test',
    'source_eval':'--self-test',
    'write_route_questions':'--self-test',
    'price_collect':'--self-test',
    'prod_refresh':'--self-test',
    'daily_collect':'--self-test',
    'e2e_check':'--self-test',
    'sample_data':'--self-test',
    'make_timeline':'--self-test',
    'demo_video':'--self-test',
    'fdv_collect':'--self-test',
    'sample_fdv':'--self-test',
    'label_fdv':'--self-test',
    'fdv_form':'--self-test',
    'fdv_checks':'--self-test',
    'fdv_extract':'--self-test',
    'fdv_score':'--self-test',
    'kap_kart_check':'--self-test',
    'kap_kart_leak_scan':'--self-test',
}
SKIP={}


def module_path(name):
    '''scripts/NAME.py or experiments/NAME.py. The public copy has no experiments/ folder (instructor, 21 Nov:
    as little test code as possible), so there an experiment returns None; anywhere else a missing name is an error.'''
    for folder in (HERE,EXPERIMENTS):
        if (folder/f'{name}.py').exists():
            return folder/f'{name}.py'
    if not EXPERIMENTS.exists():
        return None
    raise SystemExit(f'{name}.py is in neither scripts/ nor experiments/')


def main():
    # --skip NAME[,NAME]: Claude skips daily_collect locally (CLAUDE.md: Claude does not run it); CI runs all
    skip=dict(SKIP)
    if '--skip' in sys.argv:
        for name in sys.argv[sys.argv.index('--skip')+1].split(','):
            skip[name]='--skip'
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(HERE)]+[p for p in [os.environ.get('PYTHONPATH')] if p]))
    failed=[]
    passed={'system':0,'experiments':0}
    absent=0
    for name,arg in TESTS.items():
        path=module_path(name)
        if path is None:
            absent+=1
            continue
        group='system' if path.parent==HERE else 'experiments'
        if name in skip:
            print(f'{name:16} SKIP ({skip[name]})')
            continue
        cmd=[sys.executable,str(path)]+([arg] if arg else [])
        t0=time.time()
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=300,env=env)
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
        else:
            passed[group]+=1
    print(f'system {passed["system"]} passed, experiments {passed["experiments"]} passed'
          +(f' (experiments/ is not in this copy: {absent} experiment self-tests not run)' if absent else ''))
    print(f'{len(TESTS)-len(skip)-len(failed)-absent} passed, {len(failed)} failed, {len(skip)} skipped')
    sys.exit(1 if failed else 0)


if __name__=='__main__':
    main()
