'''Seal the nightly morning list before the market opens (rule: docs/forward_test_rule.md).

seal(day): canonical snapshot data/seals/<day>.json (never overwritten) + SHA-256 in data/seal_log.jsonl;
returns the first 16 hex characters for the phone alert. verify(): recompute every snapshot hash.
No amounts and no text in the snapshot; the hash itself carries no data.

Usage:
  python scripts/forward_seal.py --self-test
  python scripts/forward_seal.py --verify      # counts only
'''
import hashlib
import json
import os
import sys
from datetime import datetime

SEAL_DIR='data/seals'
LOG='data/seal_log.jsonl'
FIRST_DAY,LAST_DAY='2026-11-15','2026-11-25'


def look_first(item):
    imp=item['importance']
    return bool(imp['needs_review'] or imp['level']=='high')


def canonical(items):
    rows=[{'news_id':str(i['news_id']),'symbol':i.get('symbol'),'published_at':str(i.get('published_at')),
           'look_first':look_first(i),'level':i['importance']['level'],'score':i['importance']['score']} for i in items]
    rows.sort(key=lambda r:r['news_id'])
    return json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def seal(day,items,seal_dir=SEAL_DIR,log=LOG,now=None):
    '''Write the snapshot once and log its hash; a later different list for the same day is logged, not sealed.'''
    os.makedirs(seal_dir,exist_ok=True)
    path=os.path.join(seal_dir,f'{day}.json')
    data=canonical(items)
    h=sha(data)
    status='sealed'
    if os.path.exists(path):
        with open(path,'rb') as f:
            first=sha(f.read())
        status='same' if first==h else 'reseal_mismatch'
        h=first
    else:
        with open(path,'wb') as f:
            f.write(data)
    with open(log,'a',encoding='utf-8') as f:
        f.write(json.dumps({'day':day,'sha256':h,'status':status,'n':len(items),
                            'n_look_first':sum(look_first(i) for i in items),
                            'at':(now or datetime.now()).isoformat(timespec='seconds')})+'\n')
    return h[:16],status


def seal_day(day):
    '''Called by morning_job after a successful list; returns the alert suffix or '' (never raises).'''
    try:
        if not (FIRST_DAY<=day<=LAST_DAY):
            return ''
        with open(f'data/morning_{day}.jsonl',encoding='utf-8') as f:
            items=[json.loads(l) for l in f if l.strip()]
        h,status=seal(day,items)
        return f' | mühür {h}'+('' if status!='reseal_mismatch' else ' (ilk mühür korundu)')
    except Exception as e:
        return f' | mühür HATA {type(e).__name__}'


def verify(seal_dir=SEAL_DIR,log=LOG):
    '''(days ok, days total, bad days): snapshot hash equals the first logged hash of that day.'''
    first={}
    if os.path.exists(log):
        with open(log,encoding='utf-8') as f:
            for l in f:
                if l.strip():
                    r=json.loads(l)
                    first.setdefault(r['day'],r['sha256'])
    bad=[]
    for day,h in sorted(first.items()):
        p=os.path.join(seal_dir,f'{day}.json')
        if not os.path.exists(p):
            bad.append(day)
            continue
        with open(p,'rb') as f:
            if sha(f.read())!=h:
                bad.append(day)
    return len(first)-len(bad),len(first),bad


def _self_test():
    import tempfile
    it=lambda nid,lvl,flag:{'news_id':nid,'symbol':'AAA','published_at':'2026-11-16 10:00:00','amount':5.0,
                            'importance':{'level':lvl,'score':3,'needs_review':flag}}
    items=[it('2','low',False),it('1','high',False),it('3','low',True)]
    data=canonical(items)
    assert data==canonical(list(reversed(items))) and b'amount' not in data and b'"look_first":true' in data
    assert [r['look_first'] for r in json.loads(data)]==[True,False,True]
    with tempfile.TemporaryDirectory() as d:
        sd,lg=os.path.join(d,'s'),os.path.join(d,'l.jsonl')
        h1,s1=seal('2026-11-16',items,sd,lg)
        assert s1=='sealed' and len(h1)==16 and h1==sha(data)[:16]
        h2,s2=seal('2026-11-16',items,sd,lg)
        assert (h2,s2)==(h1,'same')
        h3,s3=seal('2026-11-16',items[:1],sd,lg)
        assert (h3,s3)==(h1,'reseal_mismatch')                        # the first seal is kept
        assert verify(sd,lg)==(1,1,[])
        with open(os.path.join(sd,'2026-11-16.json'),'ab') as f:
            f.write(b' ')
        assert verify(sd,lg)==(0,1,['2026-11-16'])                    # tampering is visible
    assert seal_day('2026-11-01')=='' and seal_day('2026-11-30')==''   # outside the sealed window
    print('self-test ok: 10 checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
    elif sys.argv[1:]==['--verify']:
        ok,n,bad=verify()
        print(f'seals ok {ok}/{n}; bad days {bad}')
    else:
        print(__doc__)
