'''The LangGraph assistant (kap_triage/assistant/agent.py) with fake routers, tools and
extractions: no Ollama, no embedding model, no real data.'''
import os
import tempfile
from datetime import date

import duckdb

import kap_triage.analysis.morning as morning
import kap_triage.assistant.agent as agent
import kap_triage.assistant.search as rag_index
from kap_triage.assistant.agent import (BRIEF_HISTORY_LINKS, BRIEF_STEPS, FIELDS_NOTE, NO_INDEX, PERIOD_LIST_MAX, TOOLS,
                                        brief_switch, build_graph, card_lines, compose_brief, detail_answer, detail_switch,
                                        period_switch, render_period_list, route_question, step_similar, tool_morning,
                                        tool_search, tr_pct, validate)
from kap_triage.assistant.names import parse_names

CTX={'symbols':{'ASELS','THYAO','KONTR'},'last_disclosure':date(2026,10,30),'last_bar':date(2026,10,30),'today':date(2026,11,2)}
NAMES,_=parse_names('ASELS: Aselsan\nTHYAO: Türk Hava Yolları; THY\nKONTR: Kontrolmatik\n')
COMPANY={'intent':'company','symbol':'ASELS','date':None,'query':None}


def fake_tools(calls):
    '''Every tool records (name, symbol, day) and answers "answer <name>".'''
    return {k:(lambda name:(lambda s:calls.append((name,s.get('symbol'),s.get('day'))) or f'answer {name}'))(k) for k in TOOLS}


def fake_steps(order):
    '''Brief steps that record their order.'''
    return tuple((n,(lambda name:(lambda st,br:order.append(name) or {'x':name}))(n)) for n,_ in BRIEF_STEPS)


def hit(n):
    return {'news_id':str(n),'symbol':'ASELS','published_at':'2026-09-17 10:00:00','kap_url':f'https://www.kap.org.tr/tr/Bildirim/{n}'}


CARD={'subject':'radar','event_type':'contract','counterparty_name':None,'counterparty_origin':'foreign','duration':'36 ay',
      'amount':1500000.0,'currency':'USD','vat_included':False,'is_revision':False,'related_party':None,
      'needs_review':True,'needs_review_reasons':['currency_unclear']}


def test_validate():
    # the model's route is checked by code: ticker case, unknown ticker, missing ticker, dates after the last data
    v=validate({'intent':'company','symbol':'asels','date':None,'query':None},'asels?',CTX)
    assert v['symbol']=='ASELS' and v['intent']=='company'
    assert validate({'intent':'company','symbol':'XXXX','date':None,'query':None},'THYAO işleri',CTX)['symbol']=='THYAO'
    v=validate({'intent':'why_moved','symbol':None,'date':None,'query':None},'hisse neden düştü',CTX)
    assert v['intent']=='unknown' and 'hisse kodu' in v['note']
    v=validate({'intent':'why_moved','symbol':'KONTR','date':'2026-11-01','query':None},'KONTR',CTX)
    assert v['day']=='2026-10-30' and '2026-10-30' in v['note']
    v=validate({'intent':'morning','symbol':None,'date':'bad','query':None},'bugün',CTX)
    assert v['day']=='2026-10-30' and v['note']
    assert validate({'intent':'nonsense','symbol':None,'date':None,'query':None},'?',CTX)['intent']=='unknown'
    v=validate({'intent':'why_moved','symbol':'ASELS','date':None,'query':None},'Aselsan dün neden yükseldi?',CTX)
    assert v['symbol']=='ASELS' and 'şirket adından' in v['note'] and 'Fiyat verisi' in v['note']
    assert validate(COMPANY,'ASELS işleri',CTX)['note'] is None
    v=validate({'intent':'morning','symbol':None,'date':'2026-11-02','query':None},'Bugün neye bakmalıyım?',CTX)
    assert v['day']=='2026-10-30' and 'henüz toplanmadı' in v['note']
    v=validate({'intent':'morning','symbol':None,'date':'2026-10-28','query':None},'28 Ekim',CTX)
    assert v['day']=='2026-10-28' and v['note'] is None


def test_names_decide_the_ticker():
    # router v2 (docs/router_v2_rule.md): a company name in the question beats the model's guess
    v=validate({'intent':'company','symbol':None,'date':None,'query':None},'Aselsan son işleri',CTX,names=NAMES)
    assert v['intent']=='company' and v['symbol']=='ASELS' and v['note'] is None
    assert validate({**COMPANY,'symbol':'THYAO'},'Aselsan son işleri',CTX,names=NAMES)['symbol']=='ASELS'
    v=validate({**COMPANY,'symbol':'KONTR'},'Aselsan ile KONTR sözleşmesi',CTX,names=NAMES)
    assert v['symbol']=='ASELS' and 'birden fazla' in v['note'] and 'ASELS, KONTR' in v['note']
    assert validate({**COMPANY,'symbol':None},'Aselsan son işleri',CTX)['intent']=='unknown'   # without names
    r={'intent':'company','symbol':None,'date':'2026-10-28','query':None}
    c2={**CTX,'names':NAMES}
    v=route_question(r,'Aselsan\'ın sözleşmesinin süresi kaç ay?',c2,v2=True)
    assert v['intent']=='detail' and v['date_filter'] and v['symbol']=='ASELS'
    v=route_question(r,'Aselsan\'ın sözleşmesinin süresi kaç ay?',c2,v2=False)
    assert v['intent']=='unknown' and not v.get('date_filter')
    r0={'intent':'search','symbol':None,'date':None,'query':None}
    assert route_question(r0,'28 Ekim savunma bildirimleri',c2,v2=True)['day']=='2026-10-28'   # date read by code
    assert route_question(r0,'28 Ekim savunma bildirimleri',c2,v2=False)['day'] is None


def test_graph_routes_to_one_tool():
    calls=[]
    routes={'q1':COMPANY,
            'q2':{'intent':'why_moved','symbol':'THYAO','date':'2026-10-29','query':None},
            'q3':{'intent':'search','symbol':None,'date':None,'query':'Irak'}}
    graph=build_graph(lambda q,today:routes[q],fake_tools(calls),CTX)
    assert graph.invoke({'question':'q1'})['answer'].endswith('answer company')
    assert graph.invoke({'question':'q2'})['answer'].endswith('answer why_moved') and calls[-1]==('why_moved','THYAO','2026-10-29')
    assert graph.invoke({'question':'q3'})['answer']=='answer search'
    assert tr_pct(0.0213)=='+2,1%' and tr_pct(-0.05)=='-5,0%'


def test_guided_form_skips_the_router():
    # a preset intent (the guided form) never calls the router
    calls,routed=[],[]
    g=build_graph(lambda q,t:routed.append(q) or COMPANY,fake_tools(calls),CTX,steps=fake_steps([]))
    out=g.invoke({'question':'ASELS temettü ne kadar?','intent':'why_moved','symbol':'ASELS','day':'2026-10-29','note':None})
    assert routed==[] and out['intent']=='why_moved' and calls[-1]==('why_moved','ASELS','2026-10-29')
    out=g.invoke({'question':'ASELS','intent':'brief','symbol':'ASELS','day':None,'note':None})
    assert routed==[] and ': şirket özeti' in out['answer'] and 'ASELS' in out['answer']


def test_detail_switch_and_card():
    # detail words turn a company/search question into a detail card (docs/detail_card_rule.md)
    base={'intent':'company','symbol':'ASELS','day':None,'query':'q','note':None}
    assert detail_switch(base,'ASELS\'in Irak sözleşmesinin süresi kaç ay?')['intent']=='detail'
    assert detail_switch(base,'ASELS son bir yılda hangi işleri aldı?')['intent']=='company'
    assert detail_switch({**base,'intent':'search','symbol':None},'Hangi ülkeye ihracat sözleşmesi?')['intent']=='detail'
    assert detail_switch({**base,'intent':'why_moved'},'ASELS ne zaman düştü?')['intent']=='why_moved'
    assert detail_switch({**base,'intent':'search'},'savunma ihracat sözleşmeleri')['intent']=='search'
    seen=[]
    t=detail_answer('q',symbol='ASELS',search=lambda q,sym:seen.append(sym) or [hit(1),hit(2)],extract=lambda n:CARD,card=True)['text']
    assert seen==['ASELS'] and 'Süre / teslim: 36 ay' in t and 'Tutar: 1.500.000 USD' in t and 'sözleşme' in t
    assert 'Karşı taraf: belirtilmemiş (yurt dışı)' in t and 'KONTROL ET: para birimi belirsiz' in t
    assert any('(yurt içi/dışı belirtilmemiş)' in line for line in card_lines(hit(1),{**CARD,'counterparty_origin':'unknown'}))
    # the source sentence line: only when the field exists
    assert 'Kaynak cümle' not in t
    assert 'Kaynak cümle: "1.500.000 USD bedelli."' in card_lines(hit(1),{**CARD,'source_sentence':'1.500.000 USD bedelli.'})
    assert 'Kaynak cümle: tutar metinde aynen geçmiyor' in '\n'.join(card_lines(hit(1),{**CARD,'source_sentence':None}))
    assert 'Başka bildirim olabilir:' in t and 'Bildirim/2' in t and t.index('Bildirim/1')<t.index('Bildirim/2')
    off=detail_answer('q',search=lambda q,sym:[hit(1)],extract=lambda n:1/0,card=False)['text']
    assert 'Süre' not in off and 'Bildirim/1' in off             # card off: links only, no extraction
    assert any('çıkarılamadı' in line for line in card_lines(hit(1),{'needs_review':True,'needs_review_reasons':['run_error']}))
    assert detail_answer('q',search=lambda q,sym:[])['text'].startswith('Bu soruya uygun bildirim bulunamadı')


def test_brief():
    # "bir bak" turns a company question into the four-step brief (docs/brief_rule.md)
    bq='Aselsan\'a bir bak'
    assert brief_switch({'intent':'company','symbol':'ASELS'},bq)['intent']=='brief'
    assert brief_switch({'intent':'company','symbol':None},bq)['intent']=='company'
    assert brief_switch({'intent':'search','symbol':'ASELS'},bq)['intent']=='search'
    assert brief_switch({'intent':'company','symbol':'ASELS'},'ASELS son işleri')['intent']=='company'
    assert route_question(COMPANY,'ASELS genel durum',CTX,v2=True)['intent']=='brief'
    order=[]
    fake=fake_steps(order)
    out=build_graph(lambda q,t:COMPANY,fake_tools([]),CTX,steps=fake).invoke({'question':bq})
    assert order==['latest','history','reaction','similar'] and set(out['steps'])==set(order)
    assert ': şirket özeti' in out['answer'] and 'ASELS' in out['answer'] and '## 4.' in out['answer']

    def boom(st,br):
        raise ValueError
    out=build_graph(lambda q,t:COMPANY,fake_tools([]),CTX,steps=(('latest',boom),)+fake[1:]).invoke({'question':bq})
    assert out['brief']['latest']=={'error':'ValueError'} and 'çıkarılamadı' in out['answer'] and '## 3.' in out['answer']
    assert 'Hesaplanamadı.' in out['answer']                     # a failed step gives one line, no crash


def test_compose_brief():
    latest={'news_id':'9','kap_url':'https://www.kap.org.tr/tr/Bildirim/9','symbol':'ASELS','published_at':'2026-10-01 10:00:00'}
    br={'latest':{'hit':latest,'data':{'subject':'radar','event_type':'order','counterparty_origin':'foreign','duration':'2 yıl',
                  'amount':1500000.0,'currency':'USD','related_party':False,'needs_review':False,'needs_review_reasons':[]},
                  'importance':{'level':'high','score':5,'reasons':[{'code':'foreign_currency','currency':'USD'}]}},
        'reaction':{'status':'ok','t0':'2026-10-02','ar0':0.041,'z0':1.2},
        'history':[{'published_at':'2026-10-01','update':False,'amount':1500000.0,'currency':'USD','kap_url':'u1'}]+
                  [{'published_at':'2026-0%d-01'%i,'update':True,'amount':None,'currency':None,'kap_url':'u'} for i in range(1,10)],
        'similar':[{'published_at':'2025-05-05 09:00:00','score':0.91,'kap_url':'u2'}]}
    t=compose_brief('ASELS',br)
    assert 'Tutar: 1.500.000 USD' in t and 'Önem: yüksek (skor 5); döviz (USD)' in t and 'tepki günü 2026-10-02' in t
    assert 'olağandışı mı: hayır' in t and '10 bildirim, 9 güncelleme/düzeltme, 1 Matriks tutar kaydı' in t
    # 8 history links + '... daha' + 1 similar
    assert '... 2 bildirim daha' in t and '(benzerlik 0,91) u2' in t and t.count('\n- ')==BRIEF_HISTORY_LINKS+2
    assert 'Yok.' in compose_brief('X',{'latest':None,'history':[],'reaction':None,'similar':[]})
    assert FIELDS_NOTE in compose_brief('ZZZ',{}) and 'uzun sözleşme' in FIELDS_NOTE and 'ölçülmedi' in FIELDS_NOTE


def test_relative_periods():
    # "geçen ay", "bu hafta", "son 3 ayda" are read by code (docs/relative_periods_rule.md)
    c3={**CTX,'today':date(2026,11,13),'last_disclosure':date(2026,11,12)}
    vc={'intent':'company','symbol':'ASELS','day':None,'query':'q','note':None}
    p=period_switch(vc,'ASELS geçen ay ne aldı',c3)
    assert p['period']==['2026-10-01','2026-10-31'] and p['note']=='Dönem: 2026-10-01 – 2026-10-31.'
    p=period_switch({**vc,'intent':'search','day':'2026-11-13'},'bu hafta savunma',c3)
    assert p['period']==['2026-11-09','2026-11-12'] and 'son toplanan gün' in p['note'] and p['day'] is None
    p=period_switch({**vc,'intent':'why_moved'},'ASELS geçen hafta neden düştü',c3)
    assert 'period' not in p and 'kullanılmıyor' in p['note']
    p=period_switch({**vc,'intent':'morning','note':'Tarih verilmedi; ...'},'geçen hafta neye bakmalıydım',c3)
    assert p['note'].startswith('Dönem: 2026-11-02') and p['period']==['2026-11-02','2026-11-08']
    assert period_switch(vc,'28 Ekim ve geçen hafta',c3) is vc and period_switch(vc,'ASELS son bildirimi',c3) is vc
    assert route_question(COMPANY,'ASELS son 3 ayda',c3)['period']==['2026-08-13','2026-11-12']
    t=render_period_list('2026-11-02','2026-11-08',[])
    assert 'Bu dönemde bildirim yok' in t and '0 yeni iş' in t
    rows=[('2026-11-03 10:00','ZZZZ',False,None,None,f'u{i}') for i in range(PERIOD_LIST_MAX+1)]
    t=render_period_list('2026-11-02','2026-11-08',rows)
    assert t.count('| ZZZZ |')==PERIOD_LIST_MAX and '1 bildirim daha' in t


def test_no_index_message(monkeypatch):
    # no search index (e.g. sample data): a clear message, never "none found"
    monkeypatch.setattr(rag_index,'load_index',lambda path=None:None)
    assert tool_search({'question':'Irak projeleri'})==NO_INDEX and detail_answer('süresi kaç ay')['text']==NO_INDEX
    assert step_similar({},{'latest':{'hit':hit(9)}})=={'error':'no_index'}
    t=compose_brief('X',{'latest':None,'history':[],'reaction':None,'similar':{'error':'no_index'}})
    assert 'Arama indeksi bu bilgisayarda yok' in t and 'Yok.' not in t


def test_empty_morning(monkeypatch):
    # a day with no disclosures: the empty list, without extraction or an index update
    with tempfile.TemporaryDirectory() as d:
        db=os.path.join(d,'t.duckdb')
        con=duckdb.connect(db)
        con.execute('CREATE TABLE disclosures(published_at TIMESTAMP)')
        con.close()

        def no_enrich(items):
            raise AssertionError('enrich called on an empty day')
        monkeypatch.setattr(agent,'DB_PATH',db)
        monkeypatch.setattr(morning,'enrich',no_enrich)
        t=tool_morning({'day':'2031-01-04'})
    assert '0 bildirim' in t and 'Bugün yeni iş ilişkisi bildirimi yok.' in t and 'tek okumayla' not in t
