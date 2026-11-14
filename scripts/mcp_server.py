'''MCP server for the agent's tools (rule: docs/mcp_rule.md). Read-only, stdio only, local clients only.

Each MCP tool builds the same state the guided form builds and runs it through the same LangGraph
graph (intent preset, so no router call): the text is the measured tool's own output.
Tool results contain licensed Matriks data: never connect a cloud client (Claude Desktop, ChatGPT ...).

Usage:
  python scripts/mcp_server.py               # stdio server (started by a client, not by hand)
  python scripts/mcp_server.py --self-test
'''
import contextlib
import re
import sys
from datetime import date

INSTRUCTIONS=('KAP "Yeni İş İlişkisi" disclosures, local tools. Results contain licensed Matriks data: '
              'use only with a local client; never send them to a cloud service. Read-only.')
TOOL_INTENT={'morning_list':'morning','company_history':'company','search_disclosures':'search',
             'why_moved':'why_moved','company_brief':'brief'}
DAY_RE=re.compile(r'^\d{4}-\d{2}-\d{2}$')


def build_state(tool,args,ctx):
    '''(state, None) or (None, error text). Same checks as the guided form; periods via agent.period_switch.'''
    from agent import period_switch
    intent=TOOL_INTENT.get(tool)
    if intent is None:
        return None,f'unknown tool {tool}'
    symbol=(args.get('symbol') or '').strip().upper() or None
    if symbol and symbol not in ctx['symbols']:
        return None,f'{symbol}: bu hisse kodunun bildirimi yok.'
    if intent in ('company','why_moved','brief') and not symbol:
        return None,'Bu araç için hisse kodu gerekli (ör. ASELS).'
    raw=(args.get('day') or '').strip()
    if raw and not DAY_RE.match(raw):
        return None,'Tarih YYYY-AA-GG biçiminde olmalı.'
    day=date.fromisoformat(raw) if raw else None
    note=None
    if intent=='morning' and (day is None or day>ctx['last_disclosure']):
        note=None if day is None else f'{day} henüz toplanmadı; son toplanan gün gösteriliyor.'
        day=ctx['last_disclosure']
    if intent=='why_moved' and (day is None or day>ctx['last_bar']):
        note=f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.'
        day=ctx['last_bar']
    query=(args.get('query') or '').strip() or None
    if intent=='search' and not query:
        return None,'Arama için konu gerekli.'
    question=' '.join(filter(None,[symbol,query])) or tool
    state={'question':question,'intent':intent,'symbol':symbol,'day':str(day) if day else None,
           'query':query,'note':note,'date_filter':False}
    phrase=(args.get('period') or '').strip()
    if phrase and intent=='company':
        state=period_switch(state,phrase,ctx)
        if not state.get('period'):
            return None,f'Dönem okunamadı: "{phrase}" (ör. "geçen ay", "son 3 ay", "bu yıl").'
    return state,None


def run_tool(tool,args,ctx=None,runner=None):
    '''Answer text of one tool call; never raises. stdout is kept free (it is the MCP channel).'''
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from agent import TOOLS, build_graph, llm_route, load_context
            ctx=ctx or load_context()
            state,err=build_state(tool,args,ctx)
            if err:
                return err
            out=(runner or (lambda st:build_graph(llm_route,TOOLS,ctx).invoke(st)))(state)
            return out.get('answer') or ''
    except Exception as e:
        return f'Araç hatası: {type(e).__name__}'


def make_server():
    from mcp.server.fastmcp import FastMCP
    mcp=FastMCP('kap-triage',instructions=INSTRUCTIONS,log_level='WARNING')

    @mcp.tool()
    def morning_list(day: str = '') -> str:
        '''Ranked morning list of new-business disclosures for a day (YYYY-MM-DD; empty = last collected day).
        Look-first and check-flagged items on top, each with its KAP link.'''
        return run_tool('morning_list',{'day':day})

    @mcp.tool()
    def company_history(symbol: str, period: str = '') -> str:
        '''A company's new-business disclosures: last 12 months, or a Turkish period phrase
        such as "geçen ay", "son 3 ay", "bu yıl". symbol = BIST ticker, e.g. ASELS.'''
        return run_tool('company_history',{'symbol':symbol,'period':period})

    @mcp.tool()
    def search_disclosures(query: str, symbol: str = '') -> str:
        '''Semantic search over all disclosures (embedding top 20, cross-encoder rerank, top 5 with KAP links).
        Optional symbol restricts it to one company.'''
        return run_tool('search_disclosures',{'query':query,'symbol':symbol})

    @mcp.tool()
    def why_moved(symbol: str, day: str = '') -> str:
        '''Why did a stock move on a day: return vs XU100, whether it was unusual, and new-business disclosures
        in the 4 days before (or an honest "no disclosure"). day = YYYY-MM-DD; empty = last price day.'''
        return run_tool('why_moved',{'symbol':symbol,'day':day})

    @mcp.tool()
    def company_brief(symbol: str) -> str:
        '''Multi-step company brief: latest disclosure with its card and importance, price reaction,
        12-month history, similar earlier disclosures.'''
        return run_tool('company_brief',{'symbol':symbol})

    return mcp


def _self_test():
    ctx={'symbols':{'ASELS','SARAE'},'last_disclosure':date(2026,11,12),'last_bar':date(2026,11,10),'today':date(2026,11,14)}
    s,e=build_state('company_history',{'symbol':'asels','period':'son 3 ay'},ctx)
    assert e is None and s['intent']=='company' and s['symbol']=='ASELS' and s['period']==['2026-08-14','2026-11-12']
    assert build_state('company_history',{'symbol':'XXXX'},ctx)[1].startswith('XXXX')
    assert build_state('company_history',{'symbol':'ASELS','period':'önceki hafta'},ctx)[1].startswith('Dönem okunamadı')
    s,_=build_state('morning_list',{'day':''},ctx)
    assert s['intent']=='morning' and s['day']=='2026-11-12' and s['note'] is None
    s,_=build_state('morning_list',{'day':'2026-12-01'},ctx)
    assert s['day']=='2026-11-12' and 'henüz toplanmadı' in s['note']
    s,_=build_state('why_moved',{'symbol':'SARAE','day':'2026-09-18'},ctx)
    assert s['day']=='2026-09-18' and s['note'] is None
    assert build_state('why_moved',{'symbol':'SARAE','day':'18.09.2026'},ctx)[1].startswith('Tarih')
    assert build_state('search_disclosures',{'query':' '},ctx)[1].startswith('Arama')
    assert build_state('company_brief',{},ctx)[1].startswith('Bu araç')
    assert build_state('nope',{},ctx)[1]=='unknown tool nope'
    got=[]
    out=run_tool('search_disclosures',{'query':'Irak'},ctx,runner=lambda st:got.append(st) or {'answer':'ok'})
    assert out=='ok' and got[0]['intent']=='search' and got[0]['query']=='Irak'
    assert run_tool('search_disclosures',{'query':'Irak'},ctx,runner=lambda st:1/0)=='Araç hatası: ZeroDivisionError'
    print('self-test ok: 13 checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
    else:
        make_server().run()   # stdio
