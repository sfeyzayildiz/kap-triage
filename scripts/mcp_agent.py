'''Tool-calling agent over MCP (rule: docs/mcp_rule.md, M3). The local model sees the MCP tool list and
chooses the tool and its arguments itself (native tool calling); the tool runs through MCP and its text
is the answer (the model writes no number). A comparison with the constrained router, not a replacement.

Usage:
  python scripts/mcp_agent.py --ask "ASELS son 3 ayda hangi işleri aldı?"
  python scripts/mcp_agent.py --eval        # M3: 16 route questions with a gold intent, counts only
  python scripts/mcp_agent.py --self-test
'''
import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import date

MODEL='gemma4:e4b'
QUESTIONS='data/route_questions.jsonl'
ROUTE_RESULTS='data/route_results.jsonl'
OUT='data/mcp_agent_results.jsonl'
EXPECTED={'morning':'morning_list','company':'company_history','why_moved':'why_moved','search':'search_disclosures'}
SYSTEM=('You help a Turkish equity analyst with KAP "Yeni İş İlişkisi" disclosures. Today is {today}. '
        'Call exactly one of the tools. Use BIST tickers in capitals (ASELS). Dates as YYYY-MM-DD.')


def read_jsonl(path):
    with open(path,encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def ollama_tools(mcp_tools):
    return [{'type':'function','function':{'name':t.name,'description':t.description or '',
             'parameters':t.inputSchema or {'type':'object','properties':{}}}} for t in mcp_tools]


def choose(question,tools,today,chat=None):
    '''(tool name or None, arguments dict, seconds).'''
    if chat is None:
        from ollama import chat
    t=time.time()
    resp=chat(model=MODEL,messages=[{'role':'system','content':SYSTEM.format(today=today)},{'role':'user','content':question}],
              tools=tools,think=False,options={'temperature':0,'num_ctx':4096})
    calls=getattr(resp.message,'tool_calls',None) or []
    if not calls:
        return None,{},time.time()-t
    fn=calls[0].function
    return fn.name,dict(fn.arguments or {}),time.time()-t


def score(rows):
    right=sum(r['tool']==r['want'] for r in rows)
    none=sum(r['tool'] is None for r in rows)
    secs=statistics.median(r['seconds'] for r in rows) if rows else 0.0
    return right,len(rows)-right-none,none,secs


async def run_eval(session):
    tools=ollama_tools((await session.list_tools()).tools)
    qs=[(i,q) for i,q in enumerate(read_jsonl(QUESTIONS)) if q.get('intent') in EXPECTED]
    rows=[]
    for i,q in qs:
        name,args,s=choose(q['question'],tools,date.today())
        rows.append({'i':i,'want':EXPECTED[q['intent']],'tool':name,'args':args,'seconds':round(s,2)})
    with open(OUT,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r,ensure_ascii=False)+'\n')
    right,wrong,none,secs=score(rows)
    router=[r for r in read_jsonl(ROUTE_RESULTS) if r['want_intent'] in EXPECTED]
    rr=sum(r['llm']['intent']==r['want_intent'] for r in router)
    miss=[r['i'] for r in rows if r['tool']!=r['want']]
    print(f'M3 tool-calling agent: right tool {right}/{len(rows)}, wrong {wrong}, no tool call {none}, median {secs:.1f} s; misses at {miss}')
    print(f'    constrained router (10 Nov run, same questions): right intent {rr}/{len(router)}')


async def ask(session,question):
    tools=ollama_tools((await session.list_tools()).tools)
    name,args,s=choose(question,tools,date.today())
    if name is None:
        return f'(model called no tool, {s:.1f} s)'
    from mcp_client import text_of
    out=text_of(await session.call_tool(name,args))
    return f'[model chose {name}({json.dumps(args,ensure_ascii=False)}) in {s:.1f} s]\n\n{out}'


def _self_test():
    class T:
        def __init__(self,n):
            self.name,self.description,self.inputSchema=n,'d',{'type':'object','properties':{'symbol':{'type':'string'}}}
    tl=ollama_tools([T('why_moved')])
    assert tl[0]['function']['name']=='why_moved' and tl[0]['type']=='function'
    class F:
        name='company_history'; arguments={'symbol':'ASELS'}
    class C:
        function=F()
    class M:
        tool_calls=[C()]
    class R:
        message=M()
    assert choose('q',tl,'2026-11-14',chat=lambda **k:R())[:2]==('company_history',{'symbol':'ASELS'})
    class M0:
        tool_calls=None
    class R0:
        message=M0()
    assert choose('q',tl,'d',chat=lambda **k:R0())[0] is None
    rows=[{'tool':'a','want':'a','seconds':1},{'tool':'b','want':'a','seconds':3},{'tool':None,'want':'a','seconds':2}]
    assert score(rows)==(1,1,1,2)
    print('self-test ok: 5 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--ask')
    g.add_argument('--eval',action='store_true')
    g.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:
        return _self_test()
    sys.path.insert(0,'scripts')
    from mcp_client import with_session
    if a.eval:
        asyncio.run(with_session(run_eval))
    else:
        print(asyncio.run(with_session(lambda s:ask(s,a.ask))))


if __name__=='__main__':
    main()
