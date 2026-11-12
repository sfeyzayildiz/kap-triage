'''Triage agent (LangGraph): route an analyst's question to one tool and answer from data.

Graph: route (LLM, structured output) -> validate (code) -> one tool (code) -> END.
(A detail switch + card tool exists but is off: docs/detail_card_rule.md, not adopted 2026-11-10.)
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
os.environ.setdefault('TRANSFORMERS_VERBOSITY','error')
os.environ.setdefault('TORCH_CPP_LOG_LEVEL','ERROR')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS','1')

import logging

logging.getLogger('torch.distributed.elastic.multiprocessing.redirects').setLevel(logging.ERROR)

import warnings


import argparse
import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Literal, Optional, TypedDict

import duckdb
_show,warnings.showwarning=warnings.showwarning,lambda *a,**k:None  # LangChain forces a deprecation notice at import; not ours
from langgraph.graph import END, START, StateGraph  # noqa: E402
warnings.showwarning=_show
from pydantic import BaseModel, ValidationError

DB_PATH='data/kap.duckdb'
INTENTS=('morning','company','why_moved','search','unknown')
TICKER_RE=re.compile(r'\b[A-ZÇĞİÖŞÜ0-9]{3,6}\b')
# docs/detail_card_rule.md (fixed before any question): a question about one disclosure's detail
DETAIL_RE=re.compile(r'\b(kaç|kac|ne kadar|ne zaman|süres|sures|kim|karşı taraf|karsi taraf|tutar|bedel|teslim|'
                     r'hangi (ülke|ulke|şirket|sirket|firma|müşteri|musteri|kurum|para birimi|döviz|doviz)|nerede|nereye|nereden)',re.I)
CARD=True  # docs/detail_card_rule.md: False shows the ticker-filtered search with links only
# docs/detail_card_rule.md result 2026-11-10: REMOVE_SWITCH (routed 5/10, right disclosure 3/10; 0/10 questions
# wrote a ticker). The switch and the detail tool stay in the code as a record; the graph does not use them.
DETAIL_SWITCH=True  # docs/router_v2_rule.md: on for the v2 measurement (card part decided by its C bar)
SHOW_QUANTITIES=False  # docs/card_quantities_rule.md: QUANTITIES_OFF (Feyza review 2026-11-11, 10/15, bar 14)
BRIEF_RE=re.compile(r'\b(bak|bakalım|bakalim|özet|ozet|özetle|ozetle|değerlendir|degerlendir|genel durum|ne durumda|durumu|brief)\b',re.I)
BRIEF_SWITCH=True  # docs/brief_rule.md: on for the measurement; decided by Feyza's 10 questions
BRIEF_HISTORY_LINKS=8
V2=True  # docs/router_v2_rule.md: company names, two-company note, date filter in search, detail switch
# docs/scope_guard_rule.md result 2026-11-12: SCOPE_OFF (A blocked 7/10, bar 9; F_new 0/10, F_old 1/185).
# Code kept as a record; a v2 list needs new questions and its own rule.
SCOPE_SWITCH=False
# docs/scope_guard_rule.md (fixed before any question; ASCII-folded, matched at a word start, suffixes allowed)
SCOPE_PHRASES=('temettu','kar payi','bedelsiz','bedelli','sermaye artirim','geri alim','genel kurul','halka arz',
               'hedef fiyat','tavsiye','alinir mi','alinmali mi','almali miyim','alayim mi','satilir mi','satilmali mi',
               'satmali miyim','satayim mi','al mi sat mi','f/k','fiyat/kazanc','pd/dd','degerleme',
               'bilanco','net kar','finansal tablo','favok','ceyrek sonuc')
SCOPE_RE=re.compile(r'\b('+'|'.join(re.escape(p) for p in SCOPE_PHRASES)+')')
FOLD=str.maketrans('çğıöşüâîû','cgiosuaiu')
SCOPE_TEXT=('Bu soru yeni iş ilişkisi bildirimlerinin dışında görünüyor (ör. temettü, sermaye artırımı, hedef fiyat, '
            'al-sat tavsiyesi, finansal tablolar). Bu asistan yalnızca KAP "Yeni İş İlişkisi" bildirimlerini kapsar '
            've yatırım tavsiyesi vermez.\n\n')

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
    date_filter: bool
    answer: str
    brief: dict
    steps: dict


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
    from names import load_names
    return {'symbols':symbols,'last_disclosure':last_disc,'last_bar':last_bar,'today':date.today(),'names':load_names()}


def validate(route,question,ctx,names=None):
    '''Code checks on the LLM route: known ticker, real date, sensible defaults.
    names (router v2): companies found in the question by code (ticker or name table) decide the ticker.'''
    intent=route.get('intent') if route.get('intent') in INTENTS else 'unknown'
    symbol=(route.get('symbol') or '').strip().upper() or None
    found=None
    if names is not None:
        from names import mentions
        found=mentions(question,ctx['symbols'],names) or None
    note=None
    if found:
        symbol=found[0]
        if len(found)>1:
            note=f'Soruda birden fazla şirket geçiyor ({", ".join(found)}); {symbol} için cevap verildi. Yanlışsa yalnızca istediğiniz şirketi yazın.'
    else:
        if symbol not in ctx['symbols']:
            # the model may miss or invent a ticker: trust only tickers written in the question
            written=[t for t in TICKER_RE.findall(question) if t in ctx['symbols']]
            symbol=written[0] if written else None
        if symbol and symbol not in TICKER_RE.findall(question.upper()):
            note=f'Hisse kodu şirket adından çıkarıldı: {symbol}. Yanlışsa soruda kodu yazın.'
    try:
        day=date.fromisoformat(route['date']) if route.get('date') else None
    except ValueError:
        day=None
    if intent=='morning' and day is None:
        day=ctx['last_disclosure']
        note=f'Tarih verilmedi; veritabanındaki son bildirim günü kullanıldı ({day}).'
    elif intent=='morning' and ctx['last_disclosure'] and day>ctx['last_disclosure']:
        note=(f'{day} günün bildirimleri henüz toplanmadı (toplama her gece 23:43). '
              f'Son toplanan gün gösteriliyor: {ctx["last_disclosure"]}.')
        day=ctx['last_disclosure']
    if intent=='why_moved':
        if day is None or day>ctx['last_bar']:
            note=' '.join(filter(None,[note,f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.']))
            day=ctx['last_bar']
    if intent in ('company','why_moved') and symbol is None:
        intent,note='unknown','Soruda veritabanında olan bir hisse kodu bulamadım (ör. ASELS).'
    query=route.get('query') or question
    return {'intent':intent,'symbol':symbol,'day':str(day) if day else None,'query':query,'note':note}


def route_question(route,question,ctx,v2=None):
    '''Validated route; v2 (docs/router_v2_rule.md) adds names, the date filter flag and the detail switch.'''
    v2=V2 if v2 is None else v2
    if v2 and not route.get('date'):
        from route_eval import word_date
        written=word_date(question,ctx['today'])  # Amendment 1: the router sometimes misses a written date
        if written:
            route={**route,'date':str(written)}
    v=validate(route,question,ctx,names=ctx.get('names',[]) if v2 else None)
    if v2:
        v['date_filter']=True
        if DETAIL_SWITCH:
            v=detail_switch(v,question)
        if BRIEF_SWITCH:
            v=brief_switch(v,question)
    return v


def fold(text):
    '''Turkish lower case folded to ASCII (İ->i, I->ı->i).'''
    return (text or '').replace('İ','i').replace('I','ı').lower().replace('̇','').translate(FOLD)


def out_of_scope(question):
    '''docs/scope_guard_rule.md: a fixed phrase outside new-business disclosures (runs before the LLM router).'''
    return bool(SCOPE_RE.search(fold(question)))


def detail_switch(v,question):
    '''Code rule after validate: a detail question about one disclosure goes to the detail tool.'''
    if v['intent'] in ('company','search') and DETAIL_RE.search(question):
        return {**v,'intent':'detail'}
    return v


def brief_switch(v,question):
    '''Code rule after validate (docs/brief_rule.md): a "look at X" question with a ticker runs the multi-step brief.'''
    if v['intent']=='company' and v.get('symbol') and BRIEF_RE.search(question):
        return {**v,'intent':'brief'}
    return v


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
    day=state.get('day') if state.get('date_filter') else None
    hits=search_question(index,state['question'],symbol=state.get('symbol'),k=5,on_day=day)
    head=f'# Arama: {state.get("query") or state["question"]}'+(f' ({state["symbol"]})' if state.get('symbol') else '')
    lines=[head+(f', {day}' if day and hits else ''),'']
    if day and not hits:
        lines.append(f'{day} tarihinde uygun bildirim bulunamadı; tüm tarihlerde arandı.')
        hits=search_question(index,state['question'],symbol=state.get('symbol'),k=5)
    lines+=[f'{i}. {h["published_at"][:10]} | {h["symbol"]} | {h["kap_url"]}' for i,h in enumerate(hits,1)]
    lines.append('')
    lines.append('Anlam benzerliğiyle 20 aday bulundu, soru ve metni birlikte okuyan bir modelle yeniden sıralandı. '
                 'Bağımsız 20 soruluk testte doğru bildirim ilk 5\'te 20/20, ilk sırada 17/20. KAP metnini okuyarak doğrulayın.')
    return '\n'.join(lines)+'\n'


EVENT_TR={'order':'sipariş','contract':'sözleşme','tender':'ihale','other':'diğer'}
ORIGIN_TR={'domestic':'yurt içi','foreign':'yurt dışı','unknown':'belirtilmemiş'}
_CARDS={}  # news_id -> extraction, this process only (a repeated question is instant)


def extract_card(news_id):
    '''Production extraction of one disclosure (pipeline.analyze: v3 + code checks + layered defence).'''
    if news_id not in _CARDS:
        from pipeline import analyze, defence_context, judge_pass, load_rows
        rows=load_rows(None,[news_id])
        if not rows:
            return None
        text=rows[0][4]
        matriks,judge=defence_context([news_id])
        from quantities import find_quantities
        data=analyze(text,matriks=matriks.get(str(news_id)))
        data=judge_pass([data],[text],judge)[0]
        data['quantities']=find_quantities(text)  # code, not the model; the extraction is unchanged
        _CARDS[news_id]=data
    return _CARDS[news_id]


def card_lines(hit,data):
    '''Card text from the extracted fields; every value comes from code, never written by the model.'''
    from morning import REVIEW_TR, tr_num
    lines=[f'# Bildirim kartı: {hit["symbol"]}, {hit["published_at"][:10]}',f'Kaynak: {hit["kap_url"]}']
    if data is None or 'run_error' in data.get('needs_review_reasons',[]):
        return lines+['Bu bildirimden alan çıkarılamadı; KAP metnini okuyun.']
    v=lambda x:x if x not in (None,'') else 'belirtilmemiş'
    lines.append(f'Konu: {v(data.get("subject"))}')
    lines.append(f'Tür: {EVENT_TR.get(data.get("event_type"),v(data.get("event_type")))}')
    lines.append(f'Karşı taraf: {v(data.get("counterparty_name"))} ({ORIGIN_TR.get(data.get("counterparty_origin"),"belirtilmemiş")})')
    lines.append(f'Süre / teslim: {v(data.get("duration"))}')
    if data.get('amount') is not None:
        amt=f'Tutar: {tr_num(data["amount"],0)} {data.get("currency") or ""}'.rstrip()
        lines.append(amt+(' (KDV dahil)' if data.get('vat_included') else ''))
    else:
        lines.append('Tutar: metinde belirtilmemiş')
    if data.get('is_revision'):
        prev=data.get('previous_amount')
        lines.append('Revizyon: evet'+(f', önceki tutar {tr_num(prev,0)}' if prev is not None else ''))
    if SHOW_QUANTITIES and data.get('quantities'):
        lines.append('Metinde geçen miktarlar (kodla bulundu): '+'; '.join(data['quantities']))
    rp=data.get('related_party')
    lines.append(f'İlişkili taraf: {"evet" if rp is True else "hayır" if rp is False else "belirtilmemiş"}')
    if data.get('needs_review'):
        lines.append('KONTROL ET: '+'; '.join(REVIEW_TR.get(c,c) for c in data['needs_review_reasons']))
    return lines


def detail_answer(question,symbol=None,search=None,extract=None,card=None,on_day=None):
    '''Top hit of the measured search (ticker-filtered) as a card, the other hits as links.'''
    card=CARD if card is None else card
    if search is None:
        from rag_index import load_index, search_question
        index=load_index()
        search=lambda q,sym:search_question(index,q,symbol=sym,k=5,on_day=on_day) or \
            (search_question(index,q,symbol=sym,k=5) if on_day else [])
    hits=search(question,symbol)
    if not hits:
        return {'hits':[],'data':None,'text':'Bu soruya uygun bildirim bulunamadı.\n'}
    data=(extract or extract_card)(hits[0]['news_id']) if card else None
    lines=card_lines(hits[0],data) if card else [f'# Arama: {question}',f'1. {hits[0]["published_at"][:10]} | {hits[0]["symbol"]} | {hits[0]["kap_url"]}']
    rest=hits[1:]
    if rest:
        lines+=['',('Başka bildirim olabilir:' if card else '')]
        lines+=[f'{i}. {h["published_at"][:10]} | {h["symbol"]} | {h["kap_url"]}' for i,h in enumerate(rest,2)]
    lines.append('')
    if card:
        lines.append('Alanlar yerel modelin bu bildirimden çıkardığı değerlerdir; cümleyi model yazmaz. Tutar ve para birimi '
                     'ölçüldü (bağımsız 100 bildirimde 1 sessiz hata), diğer alanlar ölçülmedi. Kart ilk sıradaki bildirime aittir; '
                     'KAP metnini okuyarak doğrulayın.')
    else:
        lines.append('Arama ilk 5\'te doğru bildirimi bağımsız testte 20/20 buldu. KAP metnini okuyarak doğrulayın.')
    return {'hits':hits,'data':data,'text':'\n'.join(l for l in lines if l is not None)+'\n'}


def tool_detail(state):
    day=state.get('day') if state.get('date_filter') else None
    return detail_answer(state['question'],state.get('symbol'),on_day=day)['text']


def tool_help(state):
    return ('Şunları sorabilirsiniz:\n'
            '- "Bugün neye bakmalıyım?" veya "30 Ekim\'deki bildirimler"\n'
            '- "Aselsan son bir yılda hangi işleri aldı?" (şirket adı ya da kodu)\n'
            '- "Fonet\'in Aydın sözleşmesinin süresi kaç ay?" (ayrıntı: bildirim kartı)\n'
            '- "THYAO dün neden düştü?"\n'
            '- "Aselsan\'a bir bak" (şirket özeti: son bildirim, fiyat, 12 ay, benzerleri)\n'
            '- "Irak\'taki projelerle ilgili bildirimler"\n')


def tool_scope(state):
    return SCOPE_TEXT+tool_help(state)


# --- company brief: multi-step flow, docs/brief_rule.md (every value from code; the model writes no sentence) ---
def _timed(name,fn):
    def run(state):
        t=time.time()
        brief=dict(state.get('brief') or {})
        try:
            brief[name]=fn(state,brief)
        except Exception as e:
            brief[name]={'error':type(e).__name__}
        steps=dict(state.get('steps') or {})
        steps[name]=round(time.time()-t,1)
        return {'brief':brief,'steps':steps}
    return run


def step_latest(state,brief):
    from importance import score_result
    day=state.get('day') or str(date.today())
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        rows=con.execute('''SELECT news_id,kap_url,symbol,published_at FROM disclosures
            WHERE symbol=? AND CAST(published_at AS DATE)<=? ORDER BY published_at DESC LIMIT 1''',[state['symbol'],day]).fetchall()
        if not rows:
            return None
        nid,url,sym,pub=rows[0]
        hit={'news_id':str(nid),'kap_url':url,'symbol':sym,'published_at':str(pub)}
        data=extract_card(hit['news_id'])
        imp=score_result(con,{**(data or {}),**hit}) if data else None
    finally:
        con.close()
    return {'hit':hit,'data':data,'importance':imp}


def step_history(state,brief):
    latest=brief.get('latest') or {}
    end=latest['hit']['published_at'][:10] if latest.get('hit') else (state.get('day') or str(date.today()))
    day=date.fromisoformat(end)
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        rows=con.execute('''SELECT d.published_at,d.is_update OR d.is_correction,n.amount,trim(n.cur),d.kap_url
            FROM disclosures d LEFT JOIN new_business n ON n.url=d.kap_url
            WHERE d.symbol=? AND CAST(d.published_at AS DATE)<=? AND CAST(d.published_at AS DATE)>?
            ORDER BY d.published_at DESC''',[state['symbol'],day,day-timedelta(days=365)]).fetchall()
    finally:
        con.close()
    return [{'published_at':str(p)[:10],'update':bool(u),'amount':a,'currency':c,'kap_url':k} for p,u,a,c,k in rows]


def step_reaction(state,brief):
    from morning import reaction
    latest=brief.get('latest') or {}
    if not latest.get('hit'):
        return None
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        return reaction(con,state['symbol'],datetime.fromisoformat(latest['hit']['published_at']))
    finally:
        con.close()


def step_similar(state,brief):
    from rag_index import load_index, similar_earlier
    latest=brief.get('latest') or {}
    if not latest.get('hit'):
        return []
    return similar_earlier(load_index(),latest['hit']['news_id'],k=3)


def compose_brief(symbol,brief):
    '''Brief text from the four steps; a failed or empty step becomes one line, the rest still shows.'''
    from morning import LEVEL_TR, REVIEW_TR, reaction_text, reason_text, tr_num
    lines=[f'# {symbol}: şirket özeti (4 adım, hepsi kodla)','','## 1. Son bildirim']
    latest=brief.get('latest')
    if not latest or latest.get('error') or not latest.get('hit'):
        lines.append('Son bildirim çıkarılamadı (hata).' if latest and latest.get('error') else 'Son bildirim bulunamadı.')
    else:
        lines+=card_lines(latest['hit'],latest['data'])[1:]
        imp=latest.get('importance')
        if imp:
            lines.append(f'Önem: {LEVEL_TR[imp["level"]]} (skor {imp["score"]})'+
                         ('; '+'; '.join(reason_text(r) for r in imp['reasons']) if imp['reasons'] else ''))
    lines+=['','## 2. Fiyat tepkisi']
    rx=brief.get('reaction')
    lines.append('Hesaplanamadı.' if rx is None or rx.get('error') or 'status' not in rx else reaction_text(rx)+
                 (f'; olağandışı mı: {"evet" if abs(rx["z0"])>=3 else "hayır"} (eşik z 3)' if rx.get('z0') is not None else ''))
    lines+=['','## 3. Son 12 ay']
    hist=brief.get('history')
    if hist is None or isinstance(hist,dict):
        lines.append('Hesaplanamadı.')
    else:
        n_amt=sum(1 for h in hist if h['amount'])
        lines.append(f'{len(hist)} bildirim, {sum(h["update"] for h in hist)} güncelleme/düzeltme, {n_amt} Matriks tutar kaydı.')
        for h in hist[:BRIEF_HISTORY_LINKS]:
            amt=f'{tr_num(h["amount"],0)} {h["currency"]}' if h['amount'] else 'tutar kaydı yok'
            lines.append(f'- {h["published_at"]} | {"güncelleme" if h["update"] else "yeni"} | {amt} | {h["kap_url"]}')
        if len(hist)>BRIEF_HISTORY_LINKS:
            lines.append(f'- ... {len(hist)-BRIEF_HISTORY_LINKS} bildirim daha')
    lines+=['','## 4. Benzer eski bildirimler']
    sim=brief.get('similar')
    if sim is None or isinstance(sim,dict):
        lines.append('Hesaplanamadı.')
    elif not sim:
        lines.append('Yok.')
    else:
        lines+=[f'- {x["published_at"][:10]} (benzerlik {tr_num(x["score"],2)}) {x["kap_url"]}' for x in sim]
    lines+=['','Tutar ve para birimi ölçüldü (bağımsız 100 bildirimde 1 sessiz hata); diğer alanlar ölçülmedi. '
            'Önem skoru kurallı bir sıralamadır, tahmin değildir. Karar öncesi KAP metnini okuyun.']
    return '\n'.join(lines)+'\n'


def step_compose(state):
    return {'answer':(state['note']+'\n\n' if state.get('note') else '')+compose_brief(state['symbol'],state.get('brief') or {})}


BRIEF_STEPS=(('latest',step_latest),('history',step_history),('reaction',step_reaction),('similar',step_similar))


TOOLS={'morning':tool_morning,'company':tool_company,'why_moved':tool_why_moved,'search':tool_search,'detail':tool_detail,
       'unknown':tool_help,'out_of_scope':tool_scope}


def build_graph(router,tools,ctx,steps=BRIEF_STEPS):
    '''route -> one tool -> END; intent brief -> the step chain -> compose -> END (docs/brief_rule.md).'''
    def _route(state):
        if SCOPE_SWITCH and out_of_scope(state['question']):  # docs/scope_guard_rule.md: no router call
            return {'intent':'out_of_scope','symbol':None,'day':None,'query':None,'note':None}
        r=router(state['question'],ctx['today'])
        return route_question(r,state['question'],ctx)

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
    targets={name:name for name in tools}
    if steps:
        names=[n for n,_ in steps]
        for n,fn in steps:
            g.add_node(n,_timed(n,fn))
        g.add_node('compose',step_compose)
        for a,b in zip(names,names[1:]+['compose']):
            g.add_edge(a,b)
        g.add_edge('compose',END)
        targets['brief']=names[0]
    g.add_conditional_edges('route',lambda s:s['intent'],targets)
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
    v=validate({'intent':'morning','symbol':None,'date':'2026-11-02','query':None},'Bugün neye bakmalıyım?',ctx)
    assert v['day']=='2026-10-30' and 'henüz toplanmadı' in v['note']
    v=validate({'intent':'morning','symbol':None,'date':'2026-10-28','query':None},'28 Ekim',ctx)
    assert v['day']=='2026-10-28' and v['note'] is None

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

    # detail switch (docs/detail_card_rule.md)
    base={'intent':'company','symbol':'ASELS','day':None,'query':'q','note':None}
    assert detail_switch(base,'ASELS\'in Irak sözleşmesinin süresi kaç ay?')['intent']=='detail'
    assert detail_switch(base,'ASELS son bir yılda hangi işleri aldı?')['intent']=='company'
    assert detail_switch({**base,'intent':'search','symbol':None},'Hangi ülkeye ihracat sözleşmesi?')['intent']=='detail'
    assert detail_switch({**base,'intent':'why_moved'},'ASELS ne zaman düştü?')['intent']=='why_moved'
    assert detail_switch({**base,'intent':'search'},'savunma ihracat sözleşmeleri')['intent']=='search'
    routes['q4']={'intent':'company','symbol':'ASELS','date':None,'query':None}
    assert graph.invoke({'question':'q4'})['answer'].endswith('answer company')  # no detail word -> unchanged
    hit=lambda n:{'news_id':str(n),'symbol':'ASELS','published_at':'2026-09-17 10:00:00','kap_url':f'https://www.kap.org.tr/tr/Bildirim/{n}'}
    data={'subject':'radar','event_type':'contract','counterparty_name':None,'counterparty_origin':'foreign','duration':'36 ay',
          'amount':1500000.0,'currency':'USD','vat_included':False,'is_revision':False,'related_party':None,
          'needs_review':True,'needs_review_reasons':['currency_unclear']}
    seen=[]
    out=detail_answer('q',symbol='ASELS',search=lambda q,sym:seen.append(sym) or [hit(1),hit(2)],extract=lambda n:data,card=True)
    t=out['text']
    assert seen==['ASELS'] and 'Süre / teslim: 36 ay' in t and 'Tutar: 1.500.000 USD' in t and 'sözleşme' in t
    assert 'Karşı taraf: belirtilmemiş (yurt dışı)' in t and 'KONTROL ET: para birimi belirsiz' in t
    assert 'miktarlar' not in t                                                   # no quantities -> no line
    global SHOW_QUANTITIES
    saved,qd=SHOW_QUANTITIES,{**data,'quantities':['20 adet','505 MWm']}
    SHOW_QUANTITIES=False
    assert 'miktarlar' not in card_lines(hit(1),qd)                               # switch off -> no line
    SHOW_QUANTITIES=True
    assert 'Metinde geçen miktarlar (kodla bulundu): 20 adet; 505 MWm' in card_lines(hit(1),qd)
    SHOW_QUANTITIES=saved
    assert 'Başka bildirim olabilir:' in t and 'Bildirim/2' in t and t.index('Bildirim/1')<t.index('Bildirim/2')
    off=detail_answer('q',search=lambda q,sym:[hit(1)],extract=lambda n:1/0,card=False)['text']
    assert 'Süre' not in off and 'Bildirim/1' in off                                    # card off: links only, no extraction
    err=card_lines(hit(1),{'needs_review':True,'needs_review_reasons':['run_error']})
    assert any('çıkarılamadı' in l for l in err)
    assert detail_answer('q',search=lambda q,sym:[])['text'].startswith('Bu soruya uygun bildirim bulunamadı')

    # router v2 (docs/router_v2_rule.md): names decide the ticker, two companies get a note
    from names import parse_names
    nm,_=parse_names('ASELS: Aselsan\nTHYAO: Türk Hava Yolları; THY\nKONTR: Kontrolmatik\n')
    v=validate({'intent':'company','symbol':None,'date':None,'query':None},'Aselsan son işleri',ctx,names=nm)
    assert v['intent']=='company' and v['symbol']=='ASELS' and v['note'] is None   # was unknown without names
    v=validate({'intent':'company','symbol':'THYAO','date':None,'query':None},'Aselsan son işleri',ctx,names=nm)
    assert v['symbol']=='ASELS'                                                     # code match beats the model's guess
    v=validate({'intent':'company','symbol':'KONTR','date':None,'query':None},'Aselsan ile KONTR sözleşmesi',ctx,names=nm)
    assert v['symbol']=='ASELS' and 'birden fazla' in v['note'] and 'ASELS, KONTR' in v['note']
    v=validate({'intent':'company','symbol':None,'date':None,'query':None},'Aselsan son işleri',ctx)
    assert v['intent']=='unknown'                                                   # v1 unchanged
    r={'intent':'company','symbol':None,'date':'2026-10-28','query':None}
    c2={**ctx,'names':nm}
    v=route_question(r,'Aselsan\'ın sözleşmesinin süresi kaç ay?',c2,v2=True)
    assert v['intent']=='detail' and v['date_filter'] and v['symbol']=='ASELS'
    v=route_question(r,'Aselsan\'ın sözleşmesinin süresi kaç ay?',c2,v2=False)
    assert v['intent']=='unknown' and not v.get('date_filter')
    r0={'intent':'search','symbol':None,'date':None,'query':None}
    assert route_question(r0,'28 Ekim savunma bildirimleri',c2,v2=True)['day']=='2026-10-28'   # date read by code
    assert route_question(r0,'28 Ekim savunma bildirimleri',c2,v2=False)['day'] is None
    # brief (docs/brief_rule.md): switch, step chain in the graph, compose from code
    bq='Aselsan\'a bir bak'
    assert brief_switch({'intent':'company','symbol':'ASELS'},bq)['intent']=='brief'
    assert brief_switch({'intent':'company','symbol':None},bq)['intent']=='company'
    assert brief_switch({'intent':'search','symbol':'ASELS'},bq)['intent']=='search'
    assert brief_switch({'intent':'company','symbol':'ASELS'},'ASELS son işleri')['intent']=='company'
    assert route_question({'intent':'company','symbol':'ASELS','date':None,'query':None},'ASELS genel durum',ctx,v2=True)['intent']=='brief'
    order=[]
    fake=tuple((n,(lambda name:(lambda st,br:order.append(name) or {'x':name}))(n)) for n,_ in BRIEF_STEPS)
    g2=build_graph(lambda q,t:{'intent':'company','symbol':'ASELS','date':None,'query':None},tools,ctx,steps=fake)
    out=g2.invoke({'question':bq})
    assert order==['latest','history','reaction','similar'] and set(out['steps'])==set(order)
    assert '# ASELS: şirket özeti' in out['answer'] and '## 4.' in out['answer']   # a validate note may precede it
    def boom(st,br):
        raise ValueError
    g3=build_graph(lambda q,t:{'intent':'company','symbol':'ASELS','date':None,'query':None},tools,ctx,steps=(('latest',boom),)+fake[1:])
    o3=g3.invoke({'question':bq})
    assert o3['brief']['latest']=={'error':'ValueError'} and 'çıkarılamadı' in o3['answer'] and '## 3.' in o3['answer']
    assert 'Hesaplanamadı.' in o3['answer']                                    # odd step output -> one line, no crash
    hitb={'news_id':'9','kap_url':'https://www.kap.org.tr/tr/Bildirim/9','symbol':'ASELS','published_at':'2026-10-01 10:00:00'}
    br={'latest':{'hit':hitb,'data':{'subject':'radar','event_type':'order','counterparty_origin':'foreign','duration':'2 yıl',
                  'amount':1500000.0,'currency':'USD','related_party':False,'needs_review':False,'needs_review_reasons':[]},
                  'importance':{'level':'high','score':5,'reasons':[{'code':'foreign_currency','currency':'USD'}]}},
        'reaction':{'status':'ok','t0':'2026-10-02','ar0':0.041,'z0':1.2},
        'history':[{'published_at':'2026-10-01','update':False,'amount':1500000.0,'currency':'USD','kap_url':'u1'}]+
                  [{'published_at':'2026-0%d-01'%i,'update':True,'amount':None,'currency':None,'kap_url':'u'} for i in range(1,10)],
        'similar':[{'published_at':'2025-05-05 09:00:00','score':0.91,'kap_url':'u2'}]}
    t=compose_brief('ASELS',br)
    assert 'Tutar: 1.500.000 USD' in t and 'Önem: yüksek (skor 5); döviz (USD)' in t and 'tepki günü 2026-10-02' in t
    assert 'olağandışı mı: hayır' in t and '10 bildirim, 9 güncelleme/düzeltme, 1 Matriks tutar kaydı' in t
    assert '... 2 bildirim daha' in t and '(benzerlik 0,91) u2' in t and t.count('\n- ')==BRIEF_HISTORY_LINKS+2   # 8 history + '... daha' + 1 similar
    assert 'Yok.' in compose_brief('X',{'latest':None,'history':[],'reaction':None,'similar':[]})
    # scope guard (docs/scope_guard_rule.md): folded, word start, suffixes allowed, before the router
    assert fold('İŞ BİLANÇOSU Iğdır')=='is bilancosu igdir'
    assert out_of_scope('ASELS temettüsü ne kadar?') and out_of_scope('THYAO HEDEF FİYATI kaç?')
    assert out_of_scope('Aselsan alınır mı') and out_of_scope('KONTR sermaye artırımı yapacak mı') and out_of_scope('F/K oranı')
    assert not out_of_scope('ASELS son bir yılda hangi işleri aldı?') and not out_of_scope('Irak\'taki projelerle ilgili bildirimler')
    assert not out_of_scope('Fonet\'in Aydın sözleşmesinin süresi kaç ay?') and not out_of_scope('THYAO dün neden düştü?')
    assert not out_of_scope('karşı taraf kim') and not out_of_scope('ihale bedeli')   # 'kar' / 'bedel' inside other words
    global SCOPE_SWITCH
    saved,routed=SCOPE_SWITCH,[]
    try:
        SCOPE_SWITCH=True  # the guard's path is tested even while it is off in production
        g4=build_graph(lambda q,t:routed.append(q) or {'intent':'company','symbol':'ASELS','date':None,'query':None},tools,ctx,steps=fake)
        o4=g4.invoke({'question':'ASELS temettü ne kadar?'})
        assert routed==[] and o4['intent']=='out_of_scope' and calls[-1][0]=='out_of_scope'
    finally:
        SCOPE_SWITCH=saved
    assert tool_scope({}).startswith('Bu soru yeni iş ilişkisi') and 'Şunları sorabilirsiniz' in tool_scope({})
    print('self-test ok: 63 checks')


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
