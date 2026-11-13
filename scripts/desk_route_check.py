'''n8n desk routing measurement (rule: docs/n8n_routing_rule.md). Local HTTP only (n8n 127.0.0.1:5678, Mailpit 127.0.0.1:8025).

For each day with a saved morning list: clear Mailpit, trigger the n8n webhook once, read the e-mails from Mailpit's
local API and compare them with desk_mail.payload (code). stdout: counts and day ids only, never e-mail text.

Usage:
  python scripts/desk_route_check.py --self-test
  python scripts/desk_route_check.py --day 2026-11-12     # one day, a smoke test (not the measurement)
  python scripts/desk_route_check.py --all                # the measured run, once
'''
import argparse
import json
import re
import statistics
import time
import urllib.request
from collections import Counter

N8N='http://127.0.0.1:5678/webhook/desk-routing'
MAILPIT='http://127.0.0.1:8025/api/v1'
OUT='data/desk_route_results.jsonl'
BAR_T=10.0
KAP_LINE_RE=re.compile(r'^\s*KAP: (\S+)\s*$',re.M)


def http(url,method='GET',timeout=60):
    req=urllib.request.Request(url,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        body=r.read()
        ctype=r.headers.get('Content-Type') or ''
    if 'json' in ctype and body.strip():
        return json.loads(body)
    return None   # Mailpit's DELETE answers plain "ok"; n8n may answer an empty body


def mailpit_clear():
    http(f'{MAILPIT}/messages',method='DELETE')


def mailpit_messages():
    '''[(to address, subject, text)] for every message in Mailpit.'''
    lst=http(f'{MAILPIT}/messages?limit=1000') or {}
    out=[]
    for m in lst.get('messages',[]):
        full=http(f'{MAILPIT}/message/{m["ID"]}')
        for to in full.get('To') or [{}]:
            out.append((to.get('Address','').lower(),full.get('Subject',''),full.get('Text','')))
    return out


def compare(expected,messages):
    '''expected: desk_mail.payload; messages: [(to, subject, text)]. Rule counts L, D, W, X.'''
    from desk_mail import leaks
    want={}
    for d in expected['desks']:
        for u in d['kap_urls']:
            want[u]=d['to']
    seen=Counter()
    wrong=0
    per_box=Counter(to for to,_,_ in messages)
    for to,subject,text in messages:
        for u in KAP_LINE_RE.findall(text):
            seen[u]+=1
            if u in want and want[u]!=to:
                wrong+=1
    lost=sum(1 for u in want if seen[u]==0)
    dup=sum(c-1 for c in seen.values() if c>1)+sum(c-1 for c in per_box.values() if c>1)
    extra=sum(1 for u in seen if u not in want)   # an item that belongs to no desk of the day counts as wrong
    leak=sum(leaks(subject+'\n'+text) for _,subject,text in messages)
    return {'emails':len(messages),'expected_emails':len(expected['desks']),'items':len(want),
            'L':lost,'D':dup,'W':wrong+extra,'X':leak}


def run_day(day,sectors,wait=15.0):
    from desk_mail import payload
    from panel import DESKS, load_day
    expected=payload(day,load_day(day),sectors,DESKS)
    mailpit_clear()
    t0=time.time()
    try:
        http(f'{N8N}?day={day}',timeout=60)
        err=None
    except Exception as e:   # a day without items ends the workflow early; the e-mail comparison still decides
        err=type(e).__name__
    while len(mailpit_messages())<len(expected['desks']) and time.time()-t0<wait:
        time.sleep(0.3)
    secs=time.time()-t0
    time.sleep(1.0)   # a late duplicate would arrive here
    s=compare(expected,mailpit_messages())
    s.update({'day':day,'seconds':round(secs,2),'webhook_error':err})
    return s


def decide(rows):
    t=statistics.median(r['seconds'] for r in rows) if rows else 0.0
    ok=rows and all(r['L']==0 and r['D']==0 and r['W']==0 and r['X']==0 for r in rows) and \
        all(r['emails']==r['expected_emails'] for r in rows) and t<=BAR_T
    return ('ADOPT_N8N' if ok else 'N8N_OFF'),t


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--self-test',action='store_true')
    g.add_argument('--day')
    g.add_argument('--all',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        return _self_test()
    from panel import available_days, load_sectors
    sectors=load_sectors()
    days=[args.day] if args.day else sorted(available_days())
    rows=[]
    for d in days:
        r=run_day(d,sectors)
        rows.append(r)
        print(f'{d}: emails {r["emails"]}/{r["expected_emails"]} items {r["items"]} L {r["L"]} D {r["D"]} W {r["W"]} X {r["X"]} '
              f'{r["seconds"]:.1f} s'+(f' (webhook {r["webhook_error"]})' if r['webhook_error'] else ''),flush=True)
    if args.all:
        with open(OUT,'w',encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r)+'\n')
    tot={k:sum(r[k] for r in rows) for k in ('emails','expected_emails','items','L','D','W','X')}
    d,t=decide(rows)
    print(f'days {len(rows)}; emails {tot["emails"]}/{tot["expected_emails"]}; items {tot["items"]}; '
          f'L lost {tot["L"]} (bar 0); D dup {tot["D"]} (bar 0); W wrong desk {tot["W"]} (bar 0); X leak {tot["X"]} (bar 0); '
          f'T median {t:.1f} s (bar <= {BAR_T})')
    print(f'decision={d}' if args.all else 'smoke test only (the decision comes from --all)')


def _self_test():
    exp={'day':'d','desks':[{'to':'a@masa.local','kap_urls':['u1','u2']},{'to':'b@masa.local','kap_urls':['u3']}]}
    msg=lambda to,urls,extra='':(to,'d | x: 1 bildirim',''.join(f'1. X\n   KAP: {u}\n' for u in urls)+extra)
    s=compare(exp,[msg('a@masa.local',['u1','u2']),msg('b@masa.local',['u3'])])
    assert (s['L'],s['D'],s['W'],s['X'],s['emails'],s['items'])==(0,0,0,0,2,3)
    s=compare(exp,[msg('a@masa.local',['u1']),msg('b@masa.local',['u3','u2'])])
    assert (s['L'],s['W'])==(0,1)                                  # u2 in the wrong desk
    s=compare(exp,[msg('a@masa.local',['u1','u2'])])
    assert s['L']==1                                               # u3 lost
    s=compare(exp,[msg('a@masa.local',['u1','u2']),msg('a@masa.local',['u1','u2']),msg('b@masa.local',['u3'])])
    assert s['D']==3                                               # 2 repeated items + 1 extra e-mail to the same desk
    s=compare(exp,[msg('a@masa.local',['u1','u2'],'tutar 5 milyon USD'),msg('b@masa.local',['u3','u9'])])
    assert s['X']==1 and s['W']==1                                 # leak; an item of no desk
    rows=[{'L':0,'D':0,'W':0,'X':0,'emails':2,'expected_emails':2,'seconds':s_} for s_ in (2.0,3.0,4.0)]
    assert decide(rows)==('ADOPT_N8N',3.0)
    assert decide(rows+[{**rows[0],'X':1}])[0]=='N8N_OFF' and decide([{**rows[0],'seconds':11.0}])[0]=='N8N_OFF'
    assert decide([{**rows[0],'emails':1}])[0]=='N8N_OFF' and decide([])[0]=='N8N_OFF'
    print('self-test ok: 10 checks')


if __name__=='__main__':
    main()
