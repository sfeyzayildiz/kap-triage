'''Leak scan of the kap_kart/ folder before it is shown or published (docs/kap_kart_rule.md, measurement 2).

Three counts, all must be 0:
  files   files in the folder that are not on the allowlist (__pycache__ and .DS_Store are skipped:
          the export takes git-tracked files only and .gitignore excludes them)
  pattern forbidden strings: vendor API hosts and paths, the token name, IPv4 addresses other than
          127.0.0.1, e-mail addresses, home paths, the deploy folder, the server alias
  overlap 12-word shingles shared between any folder file and any disclosure text in the DB
On a hit it prints only counts and our own file:line, never a disclosure text.
Feyza runs it (it reads the DB); Claude runs only --self-test.

Usage:
  python scripts/kap_kart_leak_scan.py            # real scan (reads data/kap.duckdb read-only)
  python scripts/kap_kart_leak_scan.py --dir PATH # scan an exported copy of the folder
  python scripts/kap_kart_leak_scan.py --self-test
'''
import argparse
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
DIR=ROOT/'kap_kart'
DB_PATH='data/kap.duckdb'
N=12
ALLOW={
    'kap_kart.py','MANIFEST.sha256','README.md','LICENSE','requirements.txt','run.sh','.gitignore',
    'frozen/llm_extract.py','frozen/amount_checks.py','frozen/amount_checks_v2.py',
    'frozen/currency_check.py','frozen/source_check.py','prompts/extract_v3.txt',
    'examples/1_temiz.txt','examples/2_para_birimi_belirsiz.txt','examples/3_revizyon.txt',
    'examples/4_gizli_talimat.txt',
}
SKIP_PARTS={'__pycache__','.DS_Store','.venv'}
FORBIDDEN=[
    ('vendor_host',re.compile(r'matriksdata|dumrul|new-business-api',re.I)),
    ('token_name',re.compile(r'KAP_TOKEN')),
    ('ipv4',re.compile(r'(?<![\d.])(?!127\.0\.0\.1(?![\d.]))\d{1,3}(?:\.\d{1,3}){3}(?![\d.])')),
    ('email',re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')),
    ('home_path',re.compile(r'/Users/|/home/')),
    ('deploy',re.compile(r'kap-deploy|ssh <server>|\biett\b',re.I)),
]


def files(folder):
    return sorted(p for p in folder.rglob('*') if p.is_file() and not SKIP_PARTS&set(p.parts))


def words(s):
    s=s.replace('I','ı').replace('İ','i').lower()
    return re.findall(r'\w+',s)


def shingles(ws):
    return {' '.join(ws[i:i+N]) for i in range(len(ws)-N+1)}


def scan(folder,corpus):
    '''corpus: iterable of disclosure texts. Returns counts and our own file:line hits.'''
    allfiles=files(folder)
    extra=[p for p in allfiles if p.relative_to(folder).as_posix() not in ALLOW]
    pattern_hits=[]
    overlap_hits=[]
    ref=set()
    for t in corpus:
        if t:
            ref|=shingles(words(t))
    for p in allfiles:
        rel=p.relative_to(folder).as_posix()
        try:
            text=p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue  # binary files are already counted under files if not allowed
        for i,line in enumerate(text.splitlines(),1):
            for name,rx in FORBIDDEN:
                if rx.search(line):
                    pattern_hits.append((rel,i,name))
        ws=[]
        owner=[]
        for i,line in enumerate(text.splitlines(),1):
            w=words(line)
            ws+=w
            owner+=[i]*len(w)
        for j in range(len(ws)-N+1):
            if ' '.join(ws[j:j+N]) in ref:
                overlap_hits.append((rel,owner[j]))
    return {'files':len(extra),'pattern':len(pattern_hits),'overlap':len(overlap_hits),
            'extra':[p.relative_to(folder).as_posix() for p in extra],
            'pattern_hits':pattern_hits,'overlap_lines':sorted(set(overlap_hits)),'n_files':len(allfiles)}


def load_corpus():
    import duckdb
    con=duckdb.connect(str(ROOT/DB_PATH),read_only=True)
    try:
        return [r[0] for r in con.execute('SELECT aciklama FROM disclosures').fetchall()]
    finally:
        con.close()


def report(res,n_docs):
    print(f'scanned {res["n_files"]} files against {n_docs} disclosure texts')
    for f in res['extra']:
        print(f'  not allowed: {f}')
    for rel,i,name in res['pattern_hits']:
        print(f'  pattern {name}: {rel}:{i}')
    for rel,i in res['overlap_lines']:
        print(f'  overlap: {rel}:{i}')
    print(f'files={res["files"]} pattern={res["pattern"]} overlap={res["overlap"]}')
    total=res['files']+res['pattern']+res['overlap']
    print(f'LEAKS={total} -> {"pass" if total==0 and n_docs>0 else "FAIL"}')


def _self_test():
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp)
        (d/'examples').mkdir()
        (d/'__pycache__').mkdir()
        (d/'__pycache__'/'x.pyc').write_bytes(b'\x00')
        (d/'kap_kart.py').write_text("HOST='127.0.0.1'\nVERSION='0.6.3'\n",encoding='utf-8')
        (d/'README.md').write_text('Sürüm 2.14.1, yerel çalışır.\n',encoding='utf-8')
        doc='bir iki üç dört beş altı yedi sekiz dokuz on onbir oniki onüç'
        (d/'examples'/'1_temiz.txt').write_text('ÖRNEK\nBir iki üç dört beş altı yedi sekiz dokuz on onbir\n',encoding='utf-8')
        res=scan(d,[doc])
        assert (res['files'],res['pattern'],res['overlap'])==(0,0,0),res
        (d/'examples'/'1_temiz.txt').write_text('ÖRNEK\nBİR iki üç dört beş altı\nyedi sekiz dokuz on onbir oniki\n',encoding='utf-8')
        (d/'notes.jsonl').write_text('{}\n',encoding='utf-8')
        (d/'kap_kart.py').write_text("U='https://example.invalid/dumrul/x'\nT='KAP_TOKEN'\nIP='94.1.2.3'\nM='a@b.com'\nP='/Users/x'\nD='kap-deploy'\n",encoding='utf-8')
        res=scan(d,[doc])
        assert res['files']==1 and res['extra']==['notes.jsonl']
        assert res['pattern']==6 and {h[2] for h in res['pattern_hits']}=={n for n,_ in FORBIDDEN}
        assert res['overlap']==1 and res['overlap_lines']==[('examples/1_temiz.txt',2)]
    real=scan(DIR,[])
    assert real['files']==0 and real['pattern']==0,f'kap_kart/ itself: files {real["extra"]} patterns {real["pattern_hits"]}'
    print(f'self-test ok: 6 checks (synthetic leaks found 8 of 8; kap_kart/ files 0, patterns 0 without the DB)')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dir',default=str(DIR))
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        return _self_test()
    now=datetime.now().strftime('%H:%M')
    if '23:35'<=now or now<'00:10':
        sys.exit('nightly window (23:35-00:10): run later')
    corpus=load_corpus()
    report(scan(Path(args.dir),corpus),len(corpus))


if __name__=='__main__':
    main()
