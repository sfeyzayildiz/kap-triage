'''Triage agent (LangGraph): route an analyst's question to one tool and answer from data.

Graph: route (LLM, structured output) -> validate (code) -> one tool (code) -> END.
The LLM only reads the question: intent, symbol, date, topic. Every number and link in
the answer comes from the database through code, so the model cannot invent them.
Tracing to LangSmith is switched off; nothing leaves the machine.

Usage:
  python scripts/agent.py --self-test
  python scripts/agent.py "Bugün neye bakmalıyım?"
  python scripts/agent.py --quiet "ASELS son bir yılda hangi işleri aldı?"   # route and line count only
'''
import os

os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'

import argparse
import json
import re
from datetime import date, datetime, timedelta
from typing import Literal, Optional, TypedDict

import duckdb
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ValidationError

DB_PATH='data/kap.duckdb'
INTENTS=('morning','company','why_moved','search','unknown')
TICKER_RE=re.compile(r'\b[A-ZÇĞİÖŞÜ0-9]{3,6}\b')

ROUTER_PROMPT='''You route a Turkish equity analyst's question to exactly one tool. Return JSON only.
intent:
- "morning": what to look at on a day, or a day's new business disclosures ("Bugün neye bakmalıyım?", "30 Ekim'deki bildirimler")
- "company": one company's recent new business disclosures ("ASELS son bir yılda hangi işleri aldı?")
- "why_moved": why a stock moved on a day ("THYAO dün neden düştü?", "KONTR 28 Ekim'de neden yükseldi?")
- "search": find disclosures about a topic, not one company's list ("Irak'taki projeler", "savunma ihracat sözleşmeleri")
- "unknown": anything else
symbol: the BIST ticker in capitals if the question writes one, else null. Do not guess a ticker from a company name.
date: YYYY-MM-DD if the question gives a day; "bugün" is {today}, "dün" is {yesterday}; else null.
query: for "search", the topic words in Turkish; else null.
Question: '''


class Route(BaseModel):
    intent: Literal['morning','company','why_moved','search','unknown']
    symbol: Optional[str]
    date: Optional[str]
    query: Optional[str]


class State(TypedDict,total=False):
    question: str
    intent: str
    symbol: Optional[str]
    day: Optional[str]
    query: Optional[str]
    note: Optional[str]
    answer: str


def llm_route(question,today):
    from llm_extract import CLIENT, MODEL
    prompt=ROUTER_PROMPT.format(today=today,yesterday=today-timedelta(days=1))
    resp=CLIENT.chat(model=MODEL,messages=[{'role':'user','content':prompt+question}],
                     format=Route.model_json_schema(),options={'temperature':0,'num_ctx':4096})
    try:
        return Route.model_validate_json(resp.message.content).model_dump()
    except ValidationError:
        return {'intent':'unknown','symbol':None,'date':None,'query':None}


def load_context():
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        symbols={r[0] for r in con.execute('SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL').fetchall()}
        last_disc=con.execute('SELECT max(CAST(published_at AS DATE)) FROM disclosures').fetchall()[0][0]
        last_bar=con.execute("SELECT max(date) FROM daily_bars WHERE symbol='XU100'").fetchall()[0][0]
    finally:
        con.close()
    return {'symbols':symbols,'last_disclosure':last_disc,'last_bar':last_bar,'today':date.today()}


def validate(route,question,ctx):
    '''Code checks on the LLM route: known ticker, real date, sensible defaults.'''
    intent=route.get('intent') if route.get('intent') in INTENTS else 'unknown'
    symbol=(route.get('symbol') or '').strip().upper() or None
    if symbol not in ctx['symbols']:
        # the model may miss or invent a ticker: trust only tickers written in the question
        written=[t for t in TICKER_RE.findall(question) if t in ctx['symbols']]
        symbol=written[0] if written else None
    try:
        day=date.fromisoformat(route['date']) if route.get('date') else None
    except ValueError:
        day=None
    note=None
    if symbol and symbol not in TICKER_RE.findall(question.upper()):
        note=f'Hisse kodu şirket adından çıkarıldı: {symbol}. Yanlışsa soruda kodu yazın.'
    if intent=='morning' and day is None:
        day=ctx['last_disclosure']
        note=f'Tarih verilmedi; veritabanındaki son bildirim günü kullanıldı ({day}).'
    if intent=='why_moved':
        if day is None or day>ctx['last_bar']:
            note=' '.join(filter(None,[note,f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.']))
            day=ctx['last_bar']
    if intent in ('company','why_moved') and symbol is None:
        intent,note='unknown','Soruda veritabanında olan bir hisse kodu bulamadım (ör. ASELS).'
    query=route.get('query') or question
    return {'intent':intent,'symbol':symbol,'day':str(day) if day else None,'query':query,'note':note}


def tr_pct(x):
    return ('+' if x>=0 else '')+f'{x*100:.1f}'.replace('.',',')+'%'


def tool_morning(state):
    from morning import enrich, extract_day, load_saved, render, save
    day=date.fromisoformat(state['day'])
    items=load_saved(day)
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        n=con.execute('SELECT count(*) FROM disclosures WHERE CAST(published_at AS DATE)=?',[day]).fetchall()[0][0]
    finally:
        con.close()
    if items is None or len(items)!=n:  # a list saved before that night's collection is stale
        items=enrich(extract_day(day))
        save(day,items)
    return render(str(day),items)


def tool_company(state):
    day=date.fromisoformat(state['day']) if state.get('day') else date.today()
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        rows=con.execute('''SELECT d.published_at,d.is_update OR d.is_correction,n.amount,trim(n.cur),d.kap_url
            FROM disclosures d LEFT JOIN new_business n ON n.url=d.kap_url
            WHERE d.symbol=? AND CAST(d.published_at AS DATE)<=? AND CAST(d.published_at AS DATE)>?
            ORDER BY d.published_at DESC''',[state['symbol'],day,day-timedelta(days=365)]).fetchall()
    finally:
        con.close()
    lines=[f'# {state["symbol"]}: son 12 ayda {len(rows)} yeni iş ilişkisi bildirimi ({day} itibarıyla)','']
    for pub,upd,amount,cur,url in rows:
        amt=f'{amount:,.0f}'.replace(',','.')+f' {cur} (Matriks kaydı)' if amount else 'tutar kaydı yok'
        lines.append(f'- {str(pub)[:10]} | {"güncelleme/düzeltme" if upd else "yeni"} | {amt} | {url}')
    if not rows:
        lines.append('Bu dönemde bildirim yok.')
    return '\n'.join(lines)+'\n'


def tool_why_moved(state):
    from price_moves import INDEX, Z_ABNORMAL, SPLIT_JUMP, abnormal, daily_returns, disclosures_before, load_closes, sigma_before
    sym=state['symbol']
    day=date.fromisoformat(state['day'])
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        series=load_closes(con,day-timedelta(days=150),day,[sym])
        if sym not in series:
            return f'{sym} için fiyat verisi yok.\n'
        ar=abnormal(daily_returns(series[sym]),daily_returns(series[INDEX]))
        days=[d for d in sorted(ar) if d<=day]
        if not days:
            return f'{sym} için {day} öncesinde fiyat verisi yok.\n'
        d=days[-1]
        a,r=ar[d]
        sigma,_=sigma_before(ar,d)
        disc=disclosures_before(con,sym,d)
    finally:
        con.close()
    lines=[f'# {sym}, {d}: hisse {tr_pct(r)}, XU100\'e göre {tr_pct(a)}']
    if d!=day:
        lines.append(f'({day} işlem günü değil; ondan önceki son işlem günü kullanıldı.)')
    if abs(r)>SPLIT_JUMP:
        lines.append('Hareket borsa günlük limitinin üstünde: büyük ihtimalle bölünme veya bedelsiz. '
                     'Fiyatlar düzeltilmemiş olduğu için bu bir haber etkisi olarak yorumlanmamalı.')
        return '\n'.join(lines)+'\n'
    if sigma:
        z=a/sigma
        lines.append(f'Olağandışı mı: {"evet" if abs(z)>=Z_ABNORMAL else "hayır"} (z {z:.1f}'.replace('.',',')+
                     f', eşik {Z_ABNORMAL:.0f}; önceki 60 işlem gününe göre)')
    else:
        lines.append('Olağandışı mı: hesaplanamadı (fiyat geçmişi kısa).')
    if disc:
        lines.append(f'Önceki 4 günde {len(disc)} yeni iş ilişkisi bildirimi var:')
        lines+=[f'- {x["published_at"][:16]} {x["kap_url"]}' for x in disc]
        lines.append('Bildirim hareketin sebebi olabilir; tek sebep olduğu kanıtlanmış değildir.')
    else:
        lines.append('Önceki 4 günde yeni iş ilişkisi bildirimi yok. Sebep başka bir yerde olabilir '
                     '(bu sistem yalnızca yeni iş ilişkisi bildirimlerine bakar).')
    return '\n'.join(lines)+'\n'


def tool_search(state):
    # the full question is searched, as in the evaluation (docs/rerank_rule.md); the router's topic is only shown
    from rag_index import load_index, search_question
    index=load_index()
    hits=search_question(index,state['question'],symbol=state.get('symbol'),k=5)
    lines=[f'# Arama: {state.get("query") or state["question"]}'+(f' ({state["symbol"]})' if state.get('symbol') else ''),'']
    lines+=[f'{i}. {h["published_at"][:10]} | {h["symbol"]} | {h["kap_url"]}' for i,h in enumerate(hits,1)]
    lines.append('')
    lines.append('Anlam benzerliğiyle 20 aday bulundu, soru ve metni birlikte okuyan bir modelle yeniden sıralandı. '
                 'Bağımsız 20 soruluk testte doğru bildirim ilk 5\'te 20/20, ilk sırada 17/20. KAP metnini okuyarak doğrulayın.')
    return '\n'.join(lines)+'\n'


def tool_help(state):
    return ('Şunları sorabilirsiniz:\n'
            '- "Bugün neye bakmalıyım?" veya "30 Ekim\'deki bildirimler"\n'
            '- "ASELS son bir yılda hangi işleri aldı?"\n'
            '- "THYAO dün neden düştü?"\n'
            '- "Irak\'taki projelerle ilgili bildirimler"\n')


TOOLS={'morning':tool_morning,'company':tool_company,'why_moved':tool_why_moved,'search':tool_search,'unknown':tool_help}


def build_graph(router,tools,ctx):
    def _route(state):
        r=router(state['question'],ctx['today'])
        return validate(r,state['question'],ctx)

    def tool_node(name):
        def run(state):
            answer=tools[name](state)
            if state.get('note'):
                answer=state['note']+'\n\n'+answer
            return {'answer':answer}
        return run

    g=StateGraph(State)
    g.add_node('route',_route)
    for name in tools:
        g.add_node(name,tool_node(name))
    g.add_edge(START,'route')
    g.add_conditional_edges('route',lambda s:s['intent'],{name:name for name in tools})
    for name in tools:
        g.add_edge(name,END)
    return g.compile()


def _self_test():
    ctx={'symbols':{'ASELS','THYAO','KONTR'},'last_disclosure':date(2026,10,30),
         'last_bar':date(2026,10,30),'today':date(2026,11,2)}
    v=validate({'intent':'company','symbol':'asels','date':None,'query':None},'asels?',ctx)
    assert v['symbol']=='ASELS' and v['intent']=='company'
    v=validate({'intent':'company','symbol':'XXXX','date':None,'query':None},'THYAO işleri',ctx)
    assert v['symbol']=='THYAO'
    v=validate({'intent':'why_moved','symbol':None,'date':None,'query':None},'hisse neden düştü',ctx)
    assert v['intent']=='unknown' and 'hisse kodu' in v['note']
    v=validate({'intent':'why_moved','symbol':'KONTR','date':'2026-11-01','query':None},'KONTR',ctx)
    assert v['day']=='2026-10-30' and '2026-10-30' in v['note']
    v=validate({'intent':'morning','symbol':None,'date':'bad','query':None},'bugün',ctx)
    assert v['day']=='2026-10-30' and v['note']
    v=validate({'intent':'nonsense','symbol':None,'date':None,'query':None},'?',ctx)
    assert v['intent']=='unknown'
    v=validate({'intent':'why_moved','symbol':'ASELS','date':None,'query':None},'Aselsan dün neden yükseldi?',ctx)
    assert v['symbol']=='ASELS' and 'şirket adından' in v['note'] and 'Fiyat verisi' in v['note']
    v=validate({'intent':'company','symbol':'ASELS','date':None,'query':None},'ASELS işleri',ctx)
    assert v['note'] is None

    calls=[]
    tools={k:(lambda name:(lambda s:calls.append((name,s.get('symbol'),s.get('day'))) or f'answer {name}'))(k) for k in TOOLS}
    routes={'q1':{'intent':'company','symbol':'ASELS','date':None,'query':None},
            'q2':{'intent':'why_moved','symbol':'THYAO','date':'2026-10-29','query':None},
            'q3':{'intent':'search','symbol':None,'date':None,'query':'Irak'}}
    graph=build_graph(lambda q,today:routes[q],tools,ctx)
    assert graph.invoke({'question':'q1'})['answer'].endswith('answer company')
    out=graph.invoke({'question':'q2'})
    assert out['answer'].endswith('answer why_moved') and calls[-1]==('why_moved','THYAO','2026-10-29')
    assert graph.invoke({'question':'q3'})['answer']=='answer search'
    assert tr_pct(0.0213)=='+2,1%' and tr_pct(-0.05)=='-5,0%'
    print('self-test ok: 13 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('question',nargs='?')
    ap.add_argument('--quiet',action='store_true',help='print only the route and the answer length')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    if not args.question:
        ap.error('give a question or --self-test')
    now=datetime.now()
    if now.hour==23 and 40<=now.minute<=50:
        raise SystemExit('collection window, try after 23:50')
    ctx=load_context()
    graph=build_graph(llm_route,TOOLS,ctx)
    out=graph.invoke({'question':args.question})
    if args.quiet:
        print(json.dumps({k:out.get(k) for k in ('intent','symbol','day')},ensure_ascii=False),
              f'answer_lines={out["answer"].count(chr(10))}')
    else:
        print(out['answer'])


if __name__=='__main__':
    main()
