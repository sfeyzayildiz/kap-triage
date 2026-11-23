'''kap_triage/web/watchlist.py: the checks of the v1 self-test in watchlist.py, on made-up data (no network, no real data).'''
import os
import tempfile
from kap_triage.web.watchlist import MAX, MESSAGES, add, load, normalize, remove


def test_watchlist():
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
