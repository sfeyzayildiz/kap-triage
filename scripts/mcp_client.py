'''Local MCP client (rule: docs/mcp_rule.md): list the tools, call one, or run the M1/M2 measurement.

The client starts scripts/mcp_server.py as a child process (stdio); nothing listens on the network.

Usage:
  python scripts/mcp_client.py --list
  python scripts/mcp_client.py --call company_history --args '{"symbol":"ASELS","period":"son 3 ay"}'
  python scripts/mcp_client.py --call ... --quiet      # length and hash only (safe to paste)
  python scripts/mcp_client.py --parity                # M1 + M2, counts only
  python scripts/mcp_client.py --self-test
'''
import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time

SERVER=[sys.executable,'scripts/mcp_server.py']
OUT='data/mcp_parity.jsonl'
BAR_OVERHEAD=0.5
# docs/mcp_rule.md M1: fixed before any run
CALLS=[('morning_list',{'day':'2026-09-17'}),('morning_list',{'day':'2026-04-22'}),
       ('company_history',{'symbol':'SARAE'}),('company_history',{'symbol':'ASELS','period':'son 3 ay'}),
       ('company_history',{'symbol':'KONTR','period':'geçen yıl'}),
       ('search_disclosures',{'query':'Irak projeleri'}),('search_disclosures',{'query':'savunma ihracat sözleşmesi'}),
       ('search_disclosures',{'query':'enerji santrali','symbol':'SARAE'}),
       ('why_moved',{'symbol':'SARAE','day':'2026-09-18'}),('why_moved',{'symbol':'KONTR','day':'2026-10-28'}),
       ('company_brief',{'symbol':'SARAE'}),('company_brief',{'symbol':'ASELS'})]


# docs/mcp_v2_rule.md: fixed before the v2 run
CALLS_V2=[('morning_list',{'day':'2026-11-12'}),('morning_list',{'day':'2026-08-17'}),
          ('company_history',{'symbol':'KONTR'}),('company_history',{'symbol':'SARAE','period':'bu yıl'}),
          ('company_history',{'symbol':'ASELS','period':'geçen ay'}),
          ('search_disclosures',{'query':'doğalgaz'}),('search_disclosures',{'query':'yazılım lisans sözleşmesi'}),
          ('search_disclosures',{'query':'elektrik','symbol':'KONTR'}),
          ('why_moved',{'symbol':'KONTR','day':'2026-09-17'}),('why_moved',{'symbol':'ASELS','day':'2026-10-15'})]
BRIEFS_V2=[('company_brief',{'symbol':'KONTR'}),('company_brief',{'symbol':'ASELS'})]
OUT_V2='data/mcp_parity_v2.jsonl'


def sections(text):
    '''{"head": ..., "1. Son bildirim": ..., ...}: the answer split at its "## " headings.'''
    out,name,buf={},'head',[]
    for line in text.splitlines():
        if line.startswith('## '):
            out[name]='\n'.join(buf)
            name,buf=line[3:].strip(),[]
        else:
            buf.append(line)
    out[name]='\n'.join(buf)
    return out


def brief_same(direct,via):
    '''(code sections identical, LLM card section identical): code = head + every section except the first numbered one.'''
    a,b=sections(direct),sections(via)
    numbered=[k for k in a if k!='head']
    card=numbered[0] if numbered else None
    code_keys=[k for k in set(a)|set(b) if k!=card]
    return all(a.get(k)==b.get(k) for k in code_keys),(a.get(card)==b.get(card))


def decide_v2(exact,n_exact,brief_ok,n_brief,over):
    return 'ADOPT_MCP_V2' if (exact==n_exact==len(CALLS_V2) and brief_ok==n_brief==len(BRIEFS_V2)
                              and over<=BAR_OVERHEAD) else 'MCP_V2_OFF'


def text_of(result):
    return ''.join(getattr(c,'text','') for c in (result.content or []))


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


async def with_session(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params=StdioServerParameters(command=SERVER[0],args=SERVER[1:])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            return await fn(session)


async def list_tools(session):
    tools=(await session.list_tools()).tools
    for t in tools:
        props=list((t.inputSchema or {}).get('properties',{}))
        print(f'- {t.name}({", ".join(props)}): {(t.description or "").splitlines()[0].strip()}')
    return len(tools)


def compare(rows):
    '''rows: dicts with same (bool) and overhead (warm pass seconds). -> (same, n, median overhead)'''
    warm=[r for r in rows if r['pass']==2]
    same=sum(r['same'] for r in warm)
    over=statistics.median(r['mcp_s']-r['direct_s'] for r in warm) if warm else 0.0
    return same,len(warm),over


def decide(same,n,over):
    return 'ADOPT_MCP' if n==len(CALLS) and same==n and over<=BAR_OVERHEAD else 'MCP_OFF'


async def parity(session):
    sys.path.insert(0,'scripts')
    from mcp_server import run_tool
    from agent import load_context
    ctx=load_context()
    rows=[]
    for p in (1,2):
        for k,(tool,args) in enumerate(CALLS):
            t=time.time()
            direct=run_tool(tool,args,ctx)
            d=time.time()-t
            t=time.time()
            via=text_of(await session.call_tool(tool,args))
            m=time.time()-t
            rows.append({'pass':p,'i':k,'tool':tool,'same':direct==via,'direct_s':round(d,3),'mcp_s':round(m,3),
                         'direct_sha':digest(direct),'mcp_sha':digest(via),'chars':len(direct)})
        print(f'pass {p} done',flush=True)
    with open(OUT,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r)+'\n')
    same,n,over=compare(rows)
    diff=[r['i'] for r in rows if r['pass']==2 and not r['same']]
    print(f'M1 parity {same}/{n} (bar {len(CALLS)}/{len(CALLS)}); different at {diff}')
    print(f'M2 median overhead {over:.3f} s (bar <= {BAR_OVERHEAD})')
    print(f'decision={decide(same,n,over)}')


async def parity_v2(session):
    sys.path.insert(0,'scripts')
    from mcp_server import run_tool
    from agent import load_context
    ctx=load_context()
    rows=[]
    for p in (1,2):
        for k,(tool,args) in enumerate(CALLS_V2+BRIEFS_V2):
            t=time.time()
            direct=run_tool(tool,args,ctx)
            d=time.time()-t
            t=time.time()
            via=text_of(await session.call_tool(tool,args))
            m=time.time()-t
            row={'pass':p,'i':k,'tool':tool,'direct_s':round(d,3),'mcp_s':round(m,3),'chars':len(direct),
                 'direct_sha':digest(direct),'mcp_sha':digest(via)}
            if tool=='company_brief':
                row['same_code'],row['same_card']=brief_same(direct,via)
                row['same']=row['same_code']
            else:
                row['same']=direct==via
            rows.append(row)
        print(f'pass {p} done',flush=True)
    with open(OUT_V2,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r)+'\n')
    warm=[r for r in rows if r['pass']==2]
    ex=[r for r in warm if r['tool']!='company_brief']
    br=[r for r in warm if r['tool']=='company_brief']
    exact,brief_ok=sum(r['same'] for r in ex),sum(r['same_code'] for r in br)
    over=statistics.median(r['mcp_s']-r['direct_s'] for r in warm)
    print(f'M1a exact {exact}/{len(ex)} (bar {len(CALLS_V2)}/{len(CALLS_V2)}); different at {[r["i"] for r in ex if not r["same"]]}')
    print(f'M1b brief code sections {brief_ok}/{len(br)} (bar {len(BRIEFS_V2)}/{len(BRIEFS_V2)}); LLM card section same {sum(r["same_card"] for r in br)}/{len(br)} (reported)')
    print(f'M2 median overhead {over:.3f} s (bar <= {BAR_OVERHEAD})')
    print(f'decision={decide_v2(exact,len(ex),brief_ok,len(br),over)}')


def _self_test():
    t1='# X: şirket özeti\n\n## 1. Son bildirim\nkart A\n\n## 2. Fiyat tepkisi\nr\n## 3. Son 12 ay\nh\n## 4. Benzer\ns\n\nalt'
    t2=t1.replace('kart A','kart A\nfazla satır')
    assert brief_same(t1,t1)==(True,True) and brief_same(t1,t2)==(True,False)
    assert brief_same(t1,t1.replace('\nh\n','\nh2\n'))==(False,True)
    assert list(sections(t1))==['head','1. Son bildirim','2. Fiyat tepkisi','3. Son 12 ay','4. Benzer']
    assert decide_v2(10,10,2,2,0.1)=='ADOPT_MCP_V2' and decide_v2(9,10,2,2,0.1)=='MCP_V2_OFF' and decide_v2(10,10,1,2,0.1)=='MCP_V2_OFF'
    assert len(CALLS_V2)==10 and len(BRIEFS_V2)==2 and not set(map(str,CALLS_V2))&set(map(str,CALLS))
    rows=[{'pass':1,'same':False,'direct_s':5,'mcp_s':9}]+[{'pass':2,'same':True,'direct_s':1.0,'mcp_s':1.2} for _ in CALLS]
    same,n,over=compare(rows)
    assert (same,n)==(12,12) and abs(over-0.2)<1e-9 and decide(same,n,over)=='ADOPT_MCP'
    assert decide(11,12,0.1)=='MCP_OFF' and decide(12,12,0.6)=='MCP_OFF' and decide(11,11,0.1)=='MCP_OFF'
    assert len(CALLS)==12 and {t for t,_ in CALLS}=={'morning_list','company_history','search_disclosures','why_moved','company_brief'}
    assert digest('a')==digest('a') and len(digest('a'))==12
    print('self-test ok: 13 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--list',action='store_true')
    g.add_argument('--call')
    g.add_argument('--parity',action='store_true')
    g.add_argument('--parity-v2',action='store_true')
    g.add_argument('--self-test',action='store_true')
    ap.add_argument('--args',default='{}')
    ap.add_argument('--quiet',action='store_true')
    a=ap.parse_args()
    if a.self_test:
        return _self_test()
    if a.list:
        n=asyncio.run(with_session(list_tools))
        print(f'{n} tools')
    elif a.call:
        async def one(session):
            return text_of(await session.call_tool(a.call,json.loads(a.args)))
        text=asyncio.run(with_session(one))
        print(f'chars {len(text)} sha {digest(text)}' if a.quiet else text)
    elif a.parity_v2:
        asyncio.run(with_session(parity_v2))
    else:
        asyncio.run(with_session(parity))


if __name__=='__main__':
    main()
