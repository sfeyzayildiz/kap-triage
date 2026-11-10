'''Agent routing: LLM router vs. keyword router (rule: docs/route_rule.md). Run by Feyza.

--run    route every question in data/route_questions.jsonl with both routers (+ agent.validate),
         results -> data/route_results.jsonl; stdout counts only.
--score  counts only and the decision.

Usage:
  python scripts/route_eval.py --self-test
  python scripts/route_eval.py --run
  python scripts/route_eval.py --score
'''
import argparse
import json
import os
import re
import statistics
import time
from datetime import datetime

QUESTIONS='data/route_questions.jsonl'
OUT='data/route_results.jsonl'
N_EXPECTED=20
MARGIN=2
WEAK=16

MONTHS={'ocak':1,'şubat':2,'subat':2,'mart':3,'nisan':4,'mayıs':5,'mayis':5,'haziran':6,'temmuz':7,
        'ağustos':8,'agustos':8,'eylül':9,'eylul':9,'ekim':10,'kasım':11,'kasim':11,'aralık':12,'aralik':12}
DATE_WORD_RE=re.compile(r'\b(\d{1,2})\s+('+'|'.join(MONTHS)+r')(?:\s+(\d{4}))?',re.I)
ISO_RE=re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
MOVE_RE=re.compile(r'\b(neden|niye|niçin|nicin|sebeb|sebep)\w*\b.*\b(düş|dus|yüksel|yuksel|art|geriled|değer kayb|tavan|taban|hareket|oyna)',re.I)
MOVE_RE2=re.compile(r'\b(düş|dus|yüksel|yuksel|art|geriled|tavan|taban)\w*\b.*\b(neden|niye|niçin|sebep|sebeb)',re.I)
MORNING_RE=re.compile(r'\b(bugün|bugun|dün|dun|sabah)\b.*\b(bak|bildirim|liste|önemli|onemli|ne var|neler)|\bneye bak',re.I)
DAY_LIST_RE=re.compile(r'\b(bildirim|açıklama|aciklama)\w*\b',re.I)
COMPANY_RE=re.compile(r'\b(iş|is|işler|sözleşme|sozlesme|sipariş|siparis|ihale|anlaşma|anlasma|aldı|aldi|kazandı|kazandi|bildirim)\w*',re.I)


def word_date(question,today):
    from datetime import date, timedelta
    q=question.lower()
    if re.search(r'\bdün\b|\bdun\b',q):
        return today-timedelta(days=1)
    if re.search(r'\bbugün\b|\bbugun\b',q):
        return today
    m=ISO_RE.search(q)
    if m:
        try:
            return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
        except ValueError:
            return None
    m=DATE_WORD_RE.search(q)
    if m:
        try:
            return date(int(m.group(3) or today.year),MONTHS[m.group(2).lower()],int(m.group(1)))
        except ValueError:
            return None
    return None


def rule_route(question,today,symbols):
    '''Keyword router (written before the questions). Same output shape as agent.llm_route.'''
    from agent import TICKER_RE
    tickers=[t for t in TICKER_RE.findall(question.upper()) if t in symbols]
    symbol=tickers[0] if tickers else None
    day=word_date(question,today)
    if MOVE_RE.search(question) or MOVE_RE2.search(question):
        intent='why_moved'
    elif MORNING_RE.search(question) or (day and not symbol and DAY_LIST_RE.search(question)):
        intent='morning'
    elif symbol and COMPANY_RE.search(question):
        intent='company'
    elif len(question.split())>=2:
        intent='search'
    else:
        intent='unknown'
    return {'intent':intent,'symbol':symbol,'date':str(day) if day else None,
            'query':question if intent=='search' else None}


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path,encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def score(rows):
    out={'n':len(rows)}
    for router in ('llm','rule'):
        out[f'{router}_intent']=sum(r[router]['intent']==r['want_intent'] for r in rows)
        sym=[r for r in rows if r['want_intent'] in ('company','why_moved') and r.get('want_symbol')]
        out[f'{router}_symbol']=(sum(r[router]['symbol']==r['want_symbol'] for r in sym),len(sym))
        secs=[r[router]['seconds'] for r in rows]
        out[f'{router}_seconds']=statistics.median(secs) if secs else None
    out['by_intent']={}
    for r in rows:
        b=out['by_intent'].setdefault(r['want_intent'],{'n':0,'llm':0,'rule':0})
        b['n']+=1
        b['llm']+=r['llm']['intent']==r['want_intent']
        b['rule']+=r['rule']['intent']==r['want_intent']
    out['decision']='KEEP_LLM' if out['llm_intent']>=out['rule_intent']+MARGIN else 'SWITCH_TO_RULES'
    out['llm_weak']=out['llm_intent']<WEAK
    return out


def run():
    from agent import llm_route, load_context, validate
    now=datetime.now()
    if now.hour==23 and 40<=now.minute<=50:
        raise SystemExit('collection window, try after 23:50')
    qs=read_jsonl(QUESTIONS)
    if len(qs)!=N_EXPECTED:
        raise SystemExit(f'{len(qs)} questions, rule needs {N_EXPECTED}')
    if os.path.exists(OUT):
        raise SystemExit(f'{OUT} exists: the rule allows one run')
    ctx=load_context()
    rows=[]
    for q in qs:
        row={'want_intent':q['intent'],'want_symbol':q.get('symbol')}
        for name,router in (('llm',llm_route),('rule',lambda x,t:rule_route(x,t,ctx['symbols']))):
            t=time.time()
            v=validate(router(q['question'],ctx['today']),q['question'],ctx)
            row[name]={'intent':v['intent'],'symbol':v['symbol'],'seconds':time.time()-t}
        rows.append(row)
    with open(OUT,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(f'routed {len(rows)} questions -> {OUT}; score with --score')


def print_score():
    rows=read_jsonl(OUT)
    if len(rows)!=N_EXPECTED:
        raise SystemExit(f'INCOMPLETE {len(rows)}/{N_EXPECTED}')
    s=score(rows)
    for r in ('llm','rule'):
        sy=s[f'{r}_symbol']
        print(f'{r:4} intent {s[f"{r}_intent"]}/{s["n"]}  ticker {sy[0]}/{sy[1]}  median {s[f"{r}_seconds"]:.2f}s')
    print('by intent: '+' '.join(f'{k} llm {v["llm"]}/{v["n"]} rule {v["rule"]}/{v["n"]}' for k,v in sorted(s['by_intent'].items())))
    print(f'decision: {s["decision"]}'+(' (LLM router below 16/20: weak)' if s['llm_weak'] else ''))


def _self_test():
    from datetime import date
    sym={'ASELS','THYAO','KONTR'}
    t=date(2026,11,10)
    r=lambda q:rule_route(q,t,sym)
    assert r('Bugün neye bakmalıyım?')['intent']=='morning'
    assert r('30 Ekim\'deki bildirimler')['intent']=='morning' and r('30 Ekim\'deki bildirimler')['date']=='2026-10-30'
    assert r('ASELS son bir yılda hangi işleri aldı?')=={'intent':'company','symbol':'ASELS','date':None,'query':None}
    assert r('THYAO dün neden düştü?')['intent']=='why_moved' and r('THYAO dün neden düştü?')['date']=='2026-11-09'
    assert r('KONTR 28 Ekim\'de neden yükseldi?')['date']=='2026-10-28'
    assert r('Irak\'taki projelerle ilgili bildirimler')['intent']=='search'
    assert r('merhaba')['intent']=='unknown'
    assert r('Aselsan dün neden yükseldi?')['intent']=='why_moved' and r('Aselsan dün neden yükseldi?')['symbol'] is None
    rows=[{'want_intent':'company','want_symbol':'ASELS','llm':{'intent':'company','symbol':'ASELS','seconds':2.0},
           'rule':{'intent':'company','symbol':'ASELS','seconds':0.0}},
          {'want_intent':'search','want_symbol':None,'llm':{'intent':'search','symbol':None,'seconds':3.0},
           'rule':{'intent':'company','symbol':None,'seconds':0.0}},
          {'want_intent':'why_moved','want_symbol':'THYAO','llm':{'intent':'why_moved','symbol':'THYAO','seconds':2.0},
           'rule':{'intent':'search','symbol':None,'seconds':0.0}}]
    s=score(rows)
    assert (s['llm_intent'],s['rule_intent'])==(3,1) and s['decision']=='KEEP_LLM'
    assert s['llm_symbol']==(2,2) and s['rule_symbol']==(1,2) and s['llm_seconds']==2.0
    assert score(rows[:1])['decision']=='SWITCH_TO_RULES'                      # tie -> rules
    assert s['by_intent']['search']=={'n':1,'llm':1,'rule':0}
    print('self-test ok: 12 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--run',action='store_true')
    g.add_argument('--score',action='store_true')
    g.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.run:
        run()
    else:
        print_score()


if __name__=='__main__':
    main()
