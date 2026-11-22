'''Guided question form (panel page /form): the analyst picks the question type, the company and the day.

The request skips the LLM router and goes straight to the measured tools of scripts/agent.py
(morning, company, brief, why_moved, search, detail). Code checks every field: a known ticker,
a real date, the fields each type needs. No JavaScript (plain HTML form, strict CSP in panel.py);
every text is escaped. The latest answer lives only in memory.

Usage:
  python scripts/form.py --self-test
  python scripts/panel.py --serve        # http://127.0.0.1:8765/form
'''
import argparse
import html
import os
import threading
import time
from datetime import date, datetime

NAMES_PATH='data/company_names.txt'
MAX_TEXT=300
# type -> (Turkish label, needs a company, needs a topic text)
TYPES={'morning':('Günün listesi (neye bakmalıyım?)',False,False),
       'company':('Şirketin son 12 ayı',True,False),
       'brief':('Şirket özeti (son bildirim, fiyat, geçmiş, benzerler)',True,False),
       'why_moved':('Hisse neden hareket etti?',True,False),
       'search':('Konu araması',False,True),
       'detail':('Bildirim ayrıntısı (kart)',True,True)}
HINTS={'morning':'Tarih boşsa son toplanan gün.','company':'Tarih boşsa bugün itibarıyla.',
       'brief':'Tarih kullanılmaz.','why_moved':'Tarih boşsa son fiyat günü.',
       'search':'Şirket ve tarih isteğe bağlı (filtre).','detail':'Konu kutusuna ne aradığınızı yazın, ör. "Irak sözleşmesinin süresi".'}
LAST={}  # the latest form answer, this process only
LOCK=threading.Lock()

e=lambda x:html.escape('' if x is None else str(x))


def display_names(path=NAMES_PATH):
    '''symbol -> first name from the frozen name table (for the drop-down only).'''
    out={}
    if not os.path.exists(path):
        return out
    with open(path,encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or ':' not in line:
                continue
            sym,_,rest=line.partition(':')
            names=[n.strip() for n in rest.split(';') if n.strip()]
            if names:
                out[sym.strip().upper()]=max(names,key=len)
    return out


def build_request(form,ctx):
    '''(state for agent.build_graph, None) or (None, Turkish error). Code decides every field.'''
    kind=form.get('type','')
    if kind not in TYPES:
        return None,'Soru türü seçin.'
    _,need_company,need_text=TYPES[kind]
    symbol=(form.get('symbol') or '').strip().upper() or None
    text=' '.join((form.get('text') or '').split())
    raw_day=(form.get('day') or '').strip()
    if symbol and symbol not in ctx['symbols']:
        return None,'Şirket listede yok.'
    if need_company and not symbol:
        return None,'Bu soru türü için şirket seçin.'
    if need_text and not text:
        return None,'Bu soru türü için konu kutusunu doldurun.'
    if len(text)>MAX_TEXT:
        return None,f'Konu en fazla {MAX_TEXT} karakter.'
    try:
        day=date.fromisoformat(raw_day) if raw_day else None
    except ValueError:
        return None,'Tarih geçersiz.'
    note=None
    if kind=='morning':
        if day is None or day>ctx['last_disclosure']:
            note=None if day is None else f'{day} henüz toplanmadı; son toplanan gün gösteriliyor.'
            day=ctx['last_disclosure']
    elif kind=='why_moved':
        if day is None or day>ctx['last_bar']:
            note=f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.'
            day=ctx['last_bar']
    elif kind=='brief':
        day=None
    question=' '.join(filter(None,[symbol,text])) or TYPES[kind][0]
    state={'question':question,'intent':kind,'symbol':symbol,'day':str(day) if day else None,
           'query':text or None,'note':note,'date_filter':day is not None}
    return state,None


def default_runner(state):
    from agent import TOOLS, build_graph, llm_route, load_context
    ctx=load_context()
    return build_graph(llm_route,TOOLS,ctx).invoke(state)


def run(form,ctx,runner=None,now=None,chart=None):
    '''Validate, run once, keep the latest record; never raises.'''
    now=now or datetime.now()
    rec={'form':{k:form.get(k,'') for k in ('type','symbol','day','text')},'at':now.strftime('%H:%M'),
         'seconds':0.0,'error':False,'answer':''}
    from chat import in_collection_window
    if in_collection_window(now):
        rec.update(answer='Gece toplama penceresi (23:40-23:50): veritabanına dokunulmuyor. 23:50\'den sonra tekrar deneyin.',error=True)
    else:
        state,err=build_request(form,ctx)
        if err:
            rec.update(answer=err,error=True)
        else:
            t0=time.time()
            try:
                with LOCK:
                    out=(runner or default_runner)(state)
                rec['answer']=out.get('answer') or ''
                try:  # price chart for why_moved / brief (display only; a failure shows no chart)
                    if chart is None:
                        from price_chart import chart_for_state as chart
                    rec['chart']=chart(state)
                except Exception:
                    rec['chart']=''
            except Exception as ex:
                rec.update(answer=f'Cevap üretilemedi ({type(ex).__name__}). Ollama açık mı?',error=True)
            rec['seconds']=round(time.time()-t0,1)
    LAST.clear()
    LAST.update(rec)
    return rec


# fields each type shows on step 2 (the required ones are checked again in build_request)
FIELDS={'morning':('day',),'company':('symbol','day'),'brief':('symbol',),'why_moved':('symbol','day'),
        'search':('text','symbol','day'),'detail':('symbol','text')}
ICONS={'morning':'☀','company':'▤','brief':'◉','why_moved':'↕','search':'⌕','detail':'▣'}


def render_choices(nav):
    '''Step 1: the question types as large choices, plus "write it myself" (the chat).'''
    cards=''.join(f'<a class="choice" href="/form?type={e(k)}"><span class="ic">{ICONS[k]}</span><b>{e(lbl)}</b>'
                  f'<span class="muted">{e(HINTS[k])}</span></a>' for k,(lbl,_,_) in TYPES.items())
    cards+=('<a class="choice free" href="/"><span class="ic">✎</span><b>Kendim yazayım</b>'
            '<span class="muted">Sorunuzu kendi cümlelerinizle yazın.</span></a>')
    return ''.join([nav,'<h1>Ne sormak istiyorsunuz?</h1>',
                    '<p class="muted">1. adım: soru türünü seçin. 2. adımda yalnızca o tür için gereken alanlar gelir; '
                    'şirket ve tarih seçildiği için soru yanlış anlaşılmaz.</p>',
                    f'<div class="choices">{cards}</div>'])


def render_body(symbols,names,last,nav,render_answer,kind=None):
    '''Step 2 for kind (step 1 if kind is missing or unknown); the latest answer of that kind below.'''
    if kind not in TYPES:
        return render_choices(nav)
    lbl,need_company,need_text=TYPES[kind]
    v=last.get('form',{}) if last and last.get('form',{}).get('type')==kind else {}
    fields=[]
    for f in FIELDS[kind]:
        if f=='symbol':
            syms='<option value="">(seçin)</option>'+''.join(
                f'<option value="{e(s)}"{" selected" if v.get("symbol")==s else ""}>{e(s)}{" · "+e(names[s]) if s in names else ""}</option>'
                for s in sorted(symbols))
            fields.append(f'<label>Şirket{"" if need_company else " (isteğe bağlı)"}'
                          f'<select name="symbol"{" required" if need_company else ""}>{syms}</select></label>')
        elif f=='day':
            fields.append(f'<label>Tarih (isteğe bağlı)<input type="date" name="day" value="{e(v.get("day"))}"></label>')
        else:
            fields.append(f'<label class="wide">Konu / ayrıntı<input type="text" name="text" maxlength="{MAX_TEXT}" '
                          f'value="{e(v.get("text"))}" placeholder="ör. Irak, savunma ihracatı, sözleşme süresi"'
                          f'{" required" if need_text else ""}></label>')
    out=[nav,'<p class="muted"><a href="/form">← Soru türleri</a></p>',f'<h1>{ICONS[kind]} {e(lbl)}</h1>',
         f'<p class="muted">{e(HINTS[kind])}</p>',
         '<form class="guided" method="post" action="/form">',f'<input type="hidden" name="type" value="{e(kind)}">',
         ''.join(fields),'<button>Sorgula</button></form>']
    if v:
        meta=f'{e(last["at"])} · {last["seconds"]:.1f} sn'.replace('.',',')
        out.append(f'<div class="msg a{" err" if last["error"] else ""}" id="son">{render_answer(last["answer"])}'
                   f'<div class="muted">{meta}</div></div>')
        import demo_mode
        out.append('' if demo_mode.ON else (last.get('chart') or ''))  # demo: no price chart
        out.append('<p><a href="/form">Yeni soru</a></p>')
    out.append('<p class="muted">Kaynak: KAP bildirimleri ve Matriks verisi. Karar öncesi KAP metnini okuyun.</p>')
    return ''.join(out)


def _self_test():
    ctx={'symbols':{'ASELS','KONTR'},'last_disclosure':date(2026,11,9),'last_bar':date(2026,11,10)}
    s,err=build_request({'type':'why_moved','symbol':'asels','day':''},ctx)
    assert err is None and s['intent']=='why_moved' and s['symbol']=='ASELS' and s['day']=='2026-11-10' and 'Fiyat verisi' in s['note']
    s,_=build_request({'type':'morning','day':'2026-12-01'},ctx)
    assert s['day']=='2026-11-09' and 'henüz toplanmadı' in s['note']
    s,_=build_request({'type':'morning'},ctx)
    assert s['day']=='2026-11-09' and s['note'] is None
    s,_=build_request({'type':'search','text':'  Irak   projeleri ','day':'2026-10-28'},ctx)
    assert s['question']=='Irak projeleri' and s['day']=='2026-10-28' and s['date_filter'] and s['symbol'] is None
    s,_=build_request({'type':'detail','symbol':'KONTR','text':'süresi kaç ay'},ctx)
    assert s['question']=='KONTR süresi kaç ay' and s['date_filter'] is False
    s,_=build_request({'type':'brief','symbol':'ASELS','day':'2026-10-01'},ctx)
    assert s['day'] is None and s['intent']=='brief'
    assert build_request({'type':'x'},ctx)[1]=='Soru türü seçin.'
    assert build_request({'type':'company'},ctx)[1]=='Bu soru türü için şirket seçin.'
    assert build_request({'type':'company','symbol':'ZZZZ'},ctx)[1]=='Şirket listede yok.'
    assert build_request({'type':'detail','symbol':'ASELS'},ctx)[1]=='Bu soru türü için konu kutusunu doldurun.'
    assert build_request({'type':'company','symbol':'ASELS','day':'2026-13-01'},ctx)[1]=='Tarih geçersiz.'
    assert build_request({'type':'search','text':'x'*301},ctx)[1].startswith('Konu en fazla')
    seen=[]
    rec=run({'type':'company','symbol':'ASELS'},ctx,runner=lambda st:seen.append(st) or {'answer':'# ok'},now=datetime(2026,11,12,10))
    assert rec['answer']=='# ok' and seen[0]['intent']=='company' and LAST['form']['symbol']=='ASELS'
    rec=run({'type':'company'},ctx,runner=lambda st:1/0,now=datetime(2026,11,12,10))
    assert rec['error'] and 'şirket seçin' in rec['answer']
    rec=run({'type':'company','symbol':'ASELS'},ctx,runner=lambda st:1/0,now=datetime(2026,11,12,10))
    assert rec['error'] and 'ZeroDivisionError' in rec['answer']
    assert 'toplama penceresi' in run({'type':'morning'},ctx,now=datetime(2026,11,12,23,45))['answer']
    last={'form':{'type':'search','symbol':'ASELS','day':'2026-10-28','text':'"><b>'},'at':'10:00','seconds':1.25,
          'error':False,'answer':'# A'}
    page=render_body({'ASELS','<X>'},{'ASELS':'Aselsan'},last,'<nav></nav>',lambda t:e(t),kind='search')
    assert '<option value="ASELS" selected>ASELS · Aselsan</option>' in page and '&lt;X&gt;' in page and '"><b>' not in page
    assert 'value="2026-10-28"' in page and 'name="type" value="search"' in page and 'id="son"' in page and 'Yeni soru' in page
    why=render_body({'ASELS'},{},last,'',lambda t:e(t),kind='why_moved')
    assert 'name="text"' not in why and 'name="day"' in why and 'id="son"' not in why   # only its fields; another type's answer hidden
    first=render_body({'ASELS'},{},last,'',lambda t:e(t))
    assert first.count('<a class="choice')==len(TYPES)+1 and 'href="/form?type=detail"' in first and 'Kendim yazayım' in first
    assert render_body(set(),{},None,'',lambda t:t,kind='zzz')==render_choices('')
    assert display_names('/nonexistent')=={}
    r=run({'type':'why_moved','symbol':'ASELS'},ctx,runner=lambda st:{'answer':'# m'},now=datetime(2026,11,12,10),
          chart=lambda st:'<figure class="chart">C</figure>' if st['intent']=='why_moved' else '')
    assert r['chart'].startswith('<figure') and '<figure class="chart">C</figure>' in render_body({'ASELS'},{},r,'',lambda t:t,kind='why_moved')
    r=run({'type':'why_moved','symbol':'ASELS'},ctx,runner=lambda st:{'answer':'# m'},now=datetime(2026,11,12,10),chart=lambda st:1/0)
    assert r['chart']=='' and not r['error']   # a chart failure never hides the answer
    print('self-test ok: 24 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        ap.error('give --self-test (the form is served by panel.py --serve)')


if __name__=='__main__':
    main()
