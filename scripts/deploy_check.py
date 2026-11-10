'''Check that a Python environment can run the nightly path (postmortem 2026-11-10: numpy missing in kap-deploy).

Compares installed versions with requirements.txt and imports every module the nightly job uses.
No network, no data. Run it with the Python that launchd uses, after every kap-deploy pull:
  ~/projects/kap-deploy/.venv/bin/python scripts/deploy_check.py

Usage:
  python scripts/deploy_check.py --self-test
  python scripts/deploy_check.py
'''
import argparse
import importlib
import re
import sys
from importlib import metadata

NIGHTLY_MODULES=('daily_collect','morning_job','morning','pipeline','importance','price_moves','rag_index',
                 'matriks_crosscheck','source_check','llm_extract','currency_check','amount_checks')
REQ_RE=re.compile(r'^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)')


def requirements(path='requirements.txt'):
    out={}
    with open(path,encoding='utf-8') as f:
        for line in f:
            m=REQ_RE.match(line)
            if m:
                out[m.group(1)]=m.group(2)
    return out


def version_problems(reqs,installed=None):
    '''[(package, wanted, found or None)] for missing or different versions.'''
    def get(name):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return None
    installed=installed or get
    return [(p,v,installed(p)) for p,v in sorted(reqs.items()) if installed(p)!=v]


def import_problems(modules=NIGHTLY_MODULES):
    sys.path.insert(0,'scripts')
    bad=[]
    for m in modules:
        try:
            importlib.import_module(m)
        except Exception as e:
            bad.append((m,f'{type(e).__name__}: {e}'))
    return bad


def _self_test():
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=os.path.join(d,'r.txt')
        with open(p,'w') as f:
            f.write('duckdb==2.0.0\n# comment\nnumpy==2.5.4  # pinned\n\nrequests>=2\n')
        assert requirements(p)=={'duckdb':'2.0.0','numpy':'2.5.4'}
    inst={'duckdb':'2.0.0','numpy':None}.get
    assert version_problems({'duckdb':'2.0.0','numpy':'2.5.4'},inst)==[('numpy','2.5.4',None)]
    assert import_problems(('json',))==[] and import_problems(('no_such_module_x',))[0][0]=='no_such_module_x'
    print('self-test ok: 4 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    vp=version_problems(requirements())
    ip=import_problems()
    for p,want,found in vp:
        print(f'version {p}: want {want}, found {found}')
    for m,err in ip:
        print(f'import {m}: {err}')
    print(f'python={sys.executable} packages_off={len(vp)} imports_failed={len(ip)} -> '+('OK' if not vp and not ip else 'FIX'))
    sys.exit(0 if not ip else 1)


if __name__=='__main__':
    main()
