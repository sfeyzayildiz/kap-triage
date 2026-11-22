'''Watchlist module: keeps the analyst's tracked tickers in data/watchlist.json.

Data contract:
- Plain JSON list of uppercase ASCII tickers (e.g. ["SVN1", "BLS2"]), no dates.
- Validation order: strip -> reject Turkish letters -> ASCII check -> uppercase -> 3-6 ASCII alphanumeric.
- Max 50 tickers (analyst scope and abuse limit); full list is rejected explicitly.
- Missing file returns an empty list; broken file (invalid JSON, bad item or duplicate) is never overwritten and blocks writes.
- Duplicate add returns 'exists'; removing a missing ticker passes silently (returns 'absent').

Usage:
  python scripts/watchlist.py --self-test
'''
import argparse
import json
import os
import re
import tempfile
import threading

PATH='data/watchlist.json'
MAX=50
CODE_RE=re.compile(r'[A-Z0-9]{3,6}')
TR_CHARS=set('çğıöşüÇĞİÖŞÜ')
LOCK=threading.Lock()
# 'absent' has no entry here on purpose: removing a missing ticker passes silently
MESSAGES={
    'added':'Takip listesine eklendi.',
    'removed':'Takip listesinden çıkarıldı.',
    'exists':'Bu şirket zaten takip listesinde.',
    'full':f'En fazla {MAX} şirket takip edilebilir.',
    'turkish':'Türkçe karakter kullanmayın, ör. SISE, BIMAS.',
    'bad_code':'Hisse kodu 3-6 karakter harf veya rakam olmalı (desene uymuyor).',
    'broken':f'Takip listesi dosyası bozuk ({PATH}); ekleme/çıkarma kapalı. Dosyayı silin ya da düzeltin.',
}


def normalize(raw):
    '''Clean and validate a ticker; returns (code, None) or (None, status_code).'''
    s=(raw or '').strip()
    if any(c in TR_CHARS for c in s):
        return None,'turkish'
    if not s.isascii():
        return None,'bad_code'
    code=s.upper()
    if not CODE_RE.fullmatch(code):
        return None,'bad_code'
    return code,None


def load(path=PATH):
    '''Return (codes, broken). Missing file is ([], False); invalid JSON, bad items or duplicates are ([], True).'''
    if not os.path.exists(path):
        return [],False
    try:
        with open(path,encoding='utf-8') as f:
            data=json.load(f)
    except (json.JSONDecodeError,OSError,UnicodeDecodeError):
        return [],True
    if not isinstance(data,list):
        return [],True
    if not all(isinstance(x,str) and CODE_RE.fullmatch(x) for x in data):
        return [],True
    if len(set(data))!=len(data):
        return [],True
    return data,False


def save(path,codes):
    '''Atomic write via a temporary file so a crash never leaves a half-written file.'''
    parent=os.path.dirname(path)
    if parent:
        os.makedirs(parent,exist_ok=True)
    tmp=path+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(codes,f,ensure_ascii=False)
    os.replace(tmp,path)


def add(path,raw):
    '''Add one ticker and return a status code; never writes over a broken file.'''
    with LOCK:
        codes,broken=load(path)
        if broken:
            return 'broken'
        code,err=normalize(raw)
        if err:
            return err
        if code in codes:
            return 'exists'
        if len(codes)>=MAX:
            return 'full'
        codes.append(code)
        save(path,codes)
        return 'added'


def remove(path,raw):
    '''Remove one ticker; returns 'absent' silently if it was not in the list.'''
    with LOCK:
        codes,broken=load(path)
        if broken:
            return 'broken'
        code,err=normalize(raw)
        if err:
            return err
        if code not in codes:
            return 'absent'
        codes.remove(code)
        save(path,codes)
        return 'removed'


def _self_test():
    assert normalize(' svn1 ')==('SVN1',None)
    assert normalize('bımas')==(None,'turkish') and normalize('ŞİŞE')==(None,'turkish')
    assert normalize('aßc')==(None,'bad_code') and normalize('café')==(None,'bad_code')
    assert normalize('AB')==(None,'bad_code') and normalize('ABCDEFG')==(None,'bad_code') and normalize(None)==(None,'bad_code')
    with tempfile.TemporaryDirectory() as d:
        p=os.path.join(d,'sub','watchlist.json')
        assert load(p)==([],False)
        assert add(p,'svn1')=='added' and not os.path.exists(p+'.tmp')
        assert add(p,'SVN1')=='exists' and load(p)==(['SVN1'],False)
        assert remove(p,'BLS2')=='absent'
        assert remove(p,'svn1')=='removed' and load(p)==([],False) and not os.path.exists(p+'.tmp')
        for bad in ('["svn1"]','["SVN1","SVN1"]','["BAD CODE"]','[123]','{"a":1}','{'):
            with open(p,'w',encoding='utf-8') as f:
                f.write(bad)
            assert load(p)==([],True) and add(p,'BLS2')=='broken' and remove(p,'SVN1')=='broken'
            with open(p,encoding='utf-8') as f:
                assert f.read()==bad
        raw_bad=b'\xff\xfe'
        with open(p,'wb') as f:
            f.write(raw_bad)
        assert load(p)==([],True) and add(p,'BLS2')=='broken'
        with open(p,'rb') as f:
            assert f.read()==raw_bad
        p2=os.path.join(d,'full.json')
        for i in range(MAX):
            assert add(p2,f'T{i:03d}')=='added'
        assert add(p2,'EXTRA')=='full' and len(load(p2)[0])==MAX and not os.path.exists(p2+'.tmp')
    expected={'added','removed','exists','full','turkish','bad_code','broken'}
    assert set(MESSAGES)==expected and all(isinstance(v,str) and v for v in MESSAGES.values()) and 'absent' not in MESSAGES
    print('self-test ok: 18 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        ap.error('give --self-test')


if __name__=='__main__':
    main()
