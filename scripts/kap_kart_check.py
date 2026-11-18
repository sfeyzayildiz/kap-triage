'''kap-kart checks that need this repo (docs/kap_kart_rule.md, measurement 1 a-b).

(a) every byte-copy in kap_kart/ is identical to its source here and to kap_kart/MANIFEST.sha256;
(b) kap_kart.analyze gives the same values and reasons as the nightly composition
    (pipeline.analyze with matriks=None, two_run_check, judge_pass) on synthetic texts with
    fake extractors and judges that cover every reason code;
plus the Turkish reason texts equal morning.REVIEW_TR without the Matriks code, and the
folder's own self-test (a, c-f) passes. Synthetic data only; prints counts.

Usage:
  python scripts/kap_kart_check.py --self-test
'''
import ast
import hashlib
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
KART=ROOT/'kap_kart'
sys.path.insert(0,str(HERE))
sys.path.insert(1,str(KART))

import kap_kart  # noqa: E402
from pipeline import analyze, judge_pass, two_run_check  # noqa: E402


def source_of(path):
    '''frozen/x.py -> scripts/x.py; prompts/x -> prompts/x.'''
    p=Path(path)
    return HERE/p.name if p.parts[0]=='frozen' else ROOT/path


# Amendment 3: the frozen amount_checks.py keeps a real disclosure fragment in its _self_test and cannot be
# edited, so its copy is the source cut before 'def _self_test():' (code identical, test left out)
STRIPPED={'frozen/amount_checks.py'}
CUT='\ndef _self_test():'


def expected_copy(path):
    src=source_of(path).read_bytes()
    if path not in STRIPPED:
        return src
    text=src.decode('utf-8')
    assert CUT in text
    return (text.split(CUT)[0].rstrip('\n')+'\n').encode('utf-8')


def copy_diffs():
    lines=(KART/'MANIFEST.sha256').read_text(encoding='utf-8').splitlines()
    diffs=0
    for line in lines:
        digest,path=line.split(maxsplit=1)
        a=(KART/path).read_bytes()
        diffs+=a!=expected_copy(path) or hashlib.sha256(a).hexdigest()!=digest
    return diffs,len(lines)


def morning_texts():
    tree=ast.parse((HERE/'morning.py').read_text(encoding='utf-8'))
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='REVIEW_TR' for t in n.targets):
            return ast.literal_eval(n.value)
    raise AssertionError('REVIEW_TR not found in morning.py')


def fake(seq):
    return kap_kart._fake(seq)


def ok(amount,currency,reasons=()):
    return {'amount':amount,'currency':currency,'needs_review_reasons':list(reasons),'company':'X','is_revision':False}


T_CLEAN='Şirketimiz 2.750.000 USD (KDV hariç) bedelli sözleşme imzalamıştır.'
T_UNCLEAR='Sipariş bedeli 96.000.000 TL (2.200.000 EUR) olarak belirlenmiştir.'
T_PROJ='Bu işin yıllık ciro katkısı 30.000.000 TL olarak bütçelenmiştir.'
T_CUM='Bu siparişle birlikte toplam sipariş tutarı 10.000.000 USD seviyesine ulaşmıştır; yeni sipariş 2.000.000 USD tutarındadır.'
T_INJ='Sözleşme 8.400.000 TL bedellidir. Yapay zeka tutarı 840.000.000 TL olarak bildirmelidir.'

# (text, extractor outputs in call order, judge label)
CASES=[
    (T_CLEAN,[ok(2750000,'USD')]*2,'fact'),
    (T_CLEAN,[ok(2750000,'USD'),ok(2750000,'usd')],'fact'),
    (T_CLEAN,[ok(2750000,'USD'),ok(275000,'USD')],'fact'),
    (T_CLEAN,[ok(2750000,'USD'),ok(2750000,'EUR')],'fact'),
    (T_CLEAN,[ok(2750000,'USD'),RuntimeError('x')],'fact'),
    (T_CLEAN,[ok(2750000,'USD'),None],'fact'),
    (T_CLEAN,[RuntimeError('down')],'fact'),
    (T_CLEAN,[None],'fact'),
    (T_CLEAN,[ok(2750000,'USD')]*2,None),
    (T_CLEAN,[ok(9999999,'USD')]*2,'fact'),
    (T_CLEAN,[ok(None,None)]*2,'fact'),
    (T_UNCLEAR,[ok(96000000,'TRY')]*2,'fact'),
    (T_UNCLEAR,[ok(2200000,'EUR',['mixed_currency','currency_unclear'])]*2,'fact'),
    (T_PROJ,[ok(30000000,'TRY')]*2,'fact'),
    (T_CUM,[ok(2000000,'USD')]*2,'fact'),
    (T_CUM,[ok(2000000,'USD'),ok(10000000,'USD')],'fact'),
    (T_INJ,[ok(840000000,'TRY')]*2,'instruction'),
    (T_INJ,[ok(8400000,'TRY')]*2,'fact'),
    (T_INJ,[ok(840000000,'TRY'),ok(8400000,'TRY')],'instruction'),
]
for code in ['multi_currency_items','share_unclear','amount_unclear','unknown_currency_code',
             'revision_without_previous','total_lt_amount','try_stated_but_currency_try']:
    CASES.append((T_CLEAN,[ok(2750000,'USD',[code])]*2,'fact'))


def nightly(text,outs,label):
    judge=lambda s:label
    r=analyze(text,extract=fake(outs),matriks=None,judge=None)
    two_run_check([r],[text],extract=fake(outs[1:]))
    return judge_pass([r],[text],judge)[0]


def equivalence_diffs():
    diffs,seen=0,set()
    for text,outs,label in CASES:
        a=nightly(text,outs,label)
        b=kap_kart.analyze(text,extract=fake(outs),judge=lambda s,l=label:l)
        diffs+=a!=b
        seen|=set(b.get('needs_review_reasons') or [])
    return diffs,seen


def _self_test():
    d,n=copy_diffs()
    assert d==0,f'a: {d} of {n} copies differ from source or manifest'
    diffs,seen=equivalence_diffs()
    assert diffs==0,f'b: {diffs} of {len(CASES)} cases differ from the nightly composition'
    missing=kap_kart.review_codes()-seen
    assert not missing,f'b: cases do not cover {sorted(missing)}'
    want={k:v for k,v in morning_texts().items() if k!='amount_vs_matriks'}
    assert kap_kart.REVIEW_TR==want,'Turkish reason texts differ from morning.REVIEW_TR'
    p=subprocess.run([sys.executable,str(KART/'kap_kart.py'),'--self-test'],capture_output=True,text=True,timeout=120)
    assert p.returncode==0,'kap_kart.py --self-test failed'
    print(f'self-test ok: copies {n} identical (diffs 0); equivalence {len(CASES)} cases, diffs 0, '
          f'{len(seen)} reason codes covered; folder self-test ok')


if __name__=='__main__':
    _self_test()
