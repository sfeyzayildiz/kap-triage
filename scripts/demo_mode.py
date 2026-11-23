'''Demo mode (docs/demo_mode_rule.md): a panel display flag that hides Matriks-licensed values.

On: every panel page shows "Matriks verisi, lisans gereği gizli" in place of the revenue ratio, results of
the Matriks FX rate (TL size, "kur yok"), the company-history size ratio, prices and price reactions (line,
chart, why-moved answer), the numeric importance score, Matriks new_business amounts, and sector names
(desks become "Masa 1", "Masa 2", ...; numbered over the whole sector table, so a sector keeps its number
every day). The KAP link, headline, company, the amount and currency extracted from the KAP text, the
source sentence, flags, the review buttons, the importance level and the list order stay visible.
Off (default): every page is byte-identical to before (the self-test compares a hash of the fixture pages).
Display only: the nightly job, the saved morning lists and /api/desks (n8n) never read this flag.

Usage:
  python scripts/demo_mode.py --self-test
  python scripts/panel.py --serve --demo           # or PANEL_DEMO=1 (e.g. in Docker)
'''
import argparse
import hashlib
import os
import re

ON=os.environ.get('PANEL_DEMO')=='1'
PLACEHOLDER='[gizli]'   # 19 Nov UI polish: short tag; the banner says once what it means (was the full sentence on every line)
BANNER=('<p class="muted"><span class="badge">Demo modu</span> Matriks verileri (gelir oranı, kur, fiyat, sektör, '
        'Matriks tutarları) lisans gereği gizli ve <b>[gizli]</b> olarak gösteriliyor; KAP metni ve ondan çıkarılanlar açık.</p>')
# importance reasons computed from Matriks values (importance.py): history ratio and TL size use Matriks
# amounts and its FX rate, the revenue ratio uses its revenue, "kur yok" says Matriks gave no rate
HIDDEN_REASONS=('size_vs_history','size_vs_revenue','size_absolute','no_rate')
REASON_RE=re.compile(r'^(şirketin önceki işlerinin medyanının |tutar / şirketin yıllık geliri|TL karşılığına göre büyüklük|'
                     r'.* için kur yok, büyüklük hesaplanmadı$)')
NEDEN_RE=re.compile(r'^- Neden: (.*)$')                                    # morning list text
ONEM_RE=re.compile(r'^Önem: (\S+) \(skor -?\d+\)(?:; (.*))?$')             # brief
LINE_RULES=[
    (re.compile(r'^(# .+, \d{4}-\d{2}-\d{2}): hisse .*$'),r'\1: fiyat hareketi: '+PLACEHOLDER),       # why-moved head
    (re.compile(r'^Olağandışı mı: .*$'),'Olağandışı mı: '+PLACEHOLDER),
    (re.compile(r'^Hareket borsa günlük limitinin üstünde.*$'),PLACEHOLDER),
    (re.compile(r'^\S+ için (?:\S+ öncesinde )?fiyat verisi yok\.$'),PLACEHOLDER),
    (re.compile(r'^- Fiyat: .*$'),'- Fiyat: '+PLACEHOLDER),                                            # morning list text
    (re.compile(r'^(## \d+\. .*) \(skor -?\d+\)$'),r'\1'),                                            # morning list heading
    (re.compile(r'^(\d+ bildirim, \d+ güncelleme/düzeltme), \d+ Matriks tutar kaydı\.$'),r'\1.'),     # brief history count
    # company / period / brief history lines: the amount field is the Matriks new_business record
    (re.compile(r'^(- \d{4}-\d{2}-\d{2} \| (?:[^|]+ \| )?(?:yeni|güncelleme|güncelleme/düzeltme)) \| [^|]+ \| (\S+)$'),
     r'\1 | '+PLACEHOLDER+r' | \2'),
]
PRICE_SECTION='## 2. Fiyat tepkisi'  # brief


def desk_map(sectors,desks):
    '''sector -> "Masa N"; N from the sorted desk names of the whole sector table (stable across days).'''
    names=sorted({desks.get(s,s) for s in sectors.values() if s})
    number={d:f'Masa {i}' for i,d in enumerate(names,1)}
    return {s:number[desks.get(s,s)] for s in set(sectors.values()) if s}


def reasons(texts):
    '''Reason texts with every Matriks-based one replaced by one placeholder (order kept).'''
    out=[]
    for t in texts:
        if REASON_RE.match(t):
            if PLACEHOLDER in out:
                continue
            t=PLACEHOLDER
        out.append(t)
    return out


def redact_answer(text):
    '''Agent answer text (chat, guided form) with the Matriks-based lines replaced; other lines unchanged.'''
    out,in_price=[],False
    for line in (text or '').split('\n'):
        if in_price:
            if line.strip() and not line.startswith('## '):
                if out[-1]!=PLACEHOLDER:
                    out.append(PLACEHOLDER)
                continue
            in_price=False
        m=NEDEN_RE.match(line)
        if m:
            out.append('- Neden: '+'; '.join(reasons(m.group(1).split('; '))))
            continue
        m=ONEM_RE.match(line)
        if m:
            out.append(f'Önem: {m.group(1)}'+('; '+'; '.join(reasons(m.group(2).split('; '))) if m.group(2) else ''))
            continue
        for rx,repl in LINE_RULES:
            if rx.match(line):
                line=rx.sub(repl,line)
                break
        out.append(line)
        if line==PRICE_SECTION:
            in_price=True
            out.append(PLACEHOLDER)
    return '\n'.join(out)


# --- synthetic test (measurement 1): marker values for every hidden field ---
MARKERS={  # field -> marker text as rendered (searched in <body> only)
    'sector':'Sektörmarker','revenue_ratio':'yıllık geliri','revenue_value':'13,6','history_ratio':'7,7 katı',
    'no_rate':'kur yok','try_size':'TL karşılığına göre','index':'XU100','reaction':'+8,6%','reaction_z':'z 4,4',
    'chart':'CHARTMARK','score':'skor 7','matriks_amount':'4.242.424','matriks_label':'(Matriks kaydı)',
    'matriks_count':'Matriks tutar kaydı','why_moved':'hisse +6,3','why_moved_z':'z 3,8',
    'review_note':'NOTMARKER',  # the analyst's free-text note on /kontroller (22 Nov): may hold anything, so hidden
}
URL='https://www.kap.org.tr/tr/Bildirim/'


def fixtures():
    '''Morning items, sector table, answer texts: every hidden field carries a marker value.'''
    from datetime import datetime
    imp=lambda score,level,flags,rs:{'score':score,'level':level,'kind':'new','needs_review':bool(flags),
                                     'needs_review_reasons':flags,'reasons':rs,'amount_try':None}
    hist={'n':3,'n_updates':1,'last':'2026-10-01'}
    items=[{'news_id':'1','symbol':'ZQXA','kap_url':URL+'1','published_at':'2026-11-16 09:00:00','amount':1500000.0,
            'currency':'USD','subject':'Savunma sözleşmesi','duration':'3 yıl',
            'importance':imp(7,'high',[],[{'code':'size_vs_history','ratio':7.7,'n_history':5,'points':3},
                                          {'code':'size_vs_revenue','ratio':0.1357,'source':'own','points':0},
                                          {'code':'foreign_currency','currency':'USD','points':1},
                                          {'code':'long_contract','years':3.0,'points':1}]),
            'reaction':{'status':'ok','t0':'2026-11-17','ar0':0.0864,'z0':4.37,'possible_split':False},'history':hist,
            'similar':[{'published_at':'2026-05-01 09:00:00','score':0.91,'kap_url':URL+'9'}]},
           {'news_id':'2','symbol':'ZQXB','kap_url':URL+'2','published_at':'2026-11-16 10:00:00','amount':250000.0,
            'currency':'EUR','importance':imp(1,'low',['currency_unclear'],[{'code':'no_rate','currency':'EUR','points':0},
                                                                          {'code':'foreign_currency','currency':'EUR','points':1}]),
            'reaction':{'status':'too_early'},'history':hist,'similar':[]},
           {'news_id':'3','symbol':'ZQXC','kap_url':URL+'3','published_at':'2026-11-16 11:00:00','amount':9000000.0,
            'currency':'TRY','importance':imp(2,'medium',[],[{'code':'size_absolute','n_history':1,'points':2}]),
            'reaction':{'status':'no_bar'},'history':hist,'similar':[]},
           {'news_id':'4','symbol':'ZQXD','kap_url':URL+'4','published_at':'2026-11-16 12:00:00','amount':None,
            'importance':imp(0,'low',[],[{'code':'no_amount','points':0}]),'reaction':{'status':'no_symbol_bars'},
            'history':hist,'similar':[]}]
    # ZQXZ is not on the day: its sector still takes a number, so numbers do not depend on the day
    sectors={'ZQXA':'Sektörmarker Alfa','ZQXB':'Sektörmarker Gama','ZQXC':'Sektörmarker Alfa','ZQXZ':'Sektörmarker Beta'}
    sentence='ZQXA ile 1.500.000 USD bedelli sözleşme imzalandı.'
    a=sentence.index('1.500.000')
    sources={'1':(sentence,[(a,a+len('1.500.000'))])}
    charts={'1':'<figure class="chart">CHARTMARK</figure>'}
    data={'subject':'Savunma sözleşmesi','event_type':'contract','counterparty_name':'Alıcı A.Ş.','counterparty_origin':'foreign',
          'duration':'3 yıl','amount':1500000.0,'currency':'USD','source_sentence':sentence,'related_party':False,
          'needs_review':False,'needs_review_reasons':[]}
    hit={'news_id':'1','kap_url':URL+'1','symbol':'ZQXA','published_at':'2026-11-16 09:00:00'}
    brief={'latest':{'hit':hit,'data':data,'importance':items[0]['importance']},'reaction':items[0]['reaction'],
           'history':[{'published_at':'2026-10-01','update':False,'amount':4242424.0,'currency':'USD','kap_url':URL+'7'},
                      {'published_at':'2026-09-01','update':True,'amount':None,'currency':None,'kap_url':URL+'8'}],
           'similar':items[0]['similar']}
    period_rows=[(datetime(2026,11,16,9),'ZQXA',False,4242424.0,'USD',URL+'1'),(datetime(2026,11,17,9),'ZQXB',True,None,None,URL+'2')]
    # same shape as agent.tool_company / tool_why_moved (they read the DB; demo_leak_check.py runs the real ones)
    company=('# ZQXA: son 12 ayda 2 yeni iş ilişkisi bildirimi (2026-11-16 itibarıyla)\n\n'
             f'- 2026-10-01 | yeni | 4.242.424 USD (Matriks kaydı) | {URL}7\n'
             f'- 2026-09-01 | güncelleme/düzeltme | tutar kaydı yok | {URL}8\n')
    why=('# ZQXA, 2026-11-17: hisse +6,3%, XU100\'e göre +5,9%\n'
         'Olağandışı mı: evet (z 3,8, eşik 3; önceki 60 işlem gününe göre)\n'
         'Önceki 4 günde 1 yeni iş ilişkisi bildirimi var:\n'
         f'- 2026-11-16 09:00 {URL}1\n'
         'Bildirim hareketin sebebi olabilir; tek sebep olduğu kanıtlanmış değildir.\n')
    return {'items':items,'sectors':sectors,'sources':sources,'charts':charts,'brief':brief,'hit':hit,'data':data,
            'period_rows':period_rows,'company':company,'why':why}


def fixture_pages():
    '''name -> full HTML of every panel page, rendered from the fixtures with the current ON value.'''
    import chat
    import form
    import names
    import panel
    import reliability
    from agent import card_lines, compose_brief, render_period_list
    from morning import render
    names._DISPLAY.clear()
    names._DISPLAY.update({'':''})  # tickers only: the local name table never changes the fixture pages
    f=fixtures()
    day='2026-11-16'
    answers=[('Bugün neye bakmalıyım?',render(day,f['items']),'morning'),
             ('ZQXA son bir yılda hangi işleri aldı?',f['company'],'company'),
             ('bu hafta',render_period_list('2026-11-16','2026-11-22',f['period_rows']),'morning'),
             ('ZQXA neden yükseldi?',f['why'],'why_moved'),
             ('ZQXA\'ya bir bak',compose_brief('ZQXA',f['brief']),'brief'),
             ('ZQXA sözleşmesinin süresi',
              '\n'.join(card_lines(f['hit'],f['data']))+'\n','detail')]
    history=[{'q':q,'a':a,'at':'09:00','seconds':1.5,'intent':i,'error':False} for q,a,i in answers]
    last={'form':{'type':'brief','symbol':'ZQXA','day':'','text':''},'at':'09:01','seconds':2.0,'error':False,
          'answer':answers[4][1],'chart':f['charts']['1']}
    view=[{'cluster':0,'n':3,'words':['savunma','teslimat'],'companies_week':3,'companies_all':9,'avg_per_week':1.5,'ratio':2.0,
           'items':[{'news_id':str(n),'symbol':s,'published_at':'2026-11-16 09:00:00'} for n,s in ((1,'ZQXA'),(2,'ZQXB'),(4,'ZQXD'))]}]
    reviews={'2':{'news_id':'2','day':day,'decision':'reject','note':'NOTMARKER 4.242.424','at':'2026-11-16T10:00:00',
                  'reasons':['currency_unclear']}}
    rows=panel.review_rows(reviews,load=lambda d:f['items'])
    rstats=panel.reason_stats(reviews,load=lambda d:f['items'])
    return {
        'overview':panel.render_overview({day:panel.day_counts(f['items'],reviews)},f['items'],reviews,rows,rstats),
        'reviews':panel.render_reviews(rows,rstats),
        'day':panel.render_day(day,f['items'],f['sectors'],{},{},f['charts'],f['sources']),
        'day_watch':panel.render_day(day,f['items'],f['sectors'],{},{},f['charts'],f['sources'],
                                     watch=['ZQXA'],query=f'{panel.MSG_PARAM}=added'),
        'overview_watch':panel.render_overview({day:panel.day_counts(f['items'],reviews)},f['items'],reviews,rows,rstats,
                                               watch=['ZQXA'],query=f'{panel.MSG_PARAM}=added'),
        'days':panel.render_index([day]),
        'chat':panel.page('KAP asistanı',chat.render_body(history)),
        'form':panel.page('Rehberli sorgu',form.render_body({'ZQXA'},{},last,chat.NAV,chat.render_answer,kind='brief')),
        'themes':panel.render_themes_index([(day,3)],'2026-11-16 09:00:00',0),
        'week':panel.render_week(day,view,f['sectors'],{str(n):URL+str(n) for n in (1,2,4)}),
        'reliability':panel.page('Güvenilirlik',reliability.render_body(chat.NAV)),
    }


def body(page):
    return page.split('<body>',1)[-1]


def pages_hash(pages):
    return hashlib.sha256('\x00'.join(f'{k}\x01{v}' for k,v in sorted(pages.items())).encode('utf-8')).hexdigest()[:16]


# demo-off fixture pages rendered by main 6bf5e9c (before demo mode); change only with a change meant to alter the pages
# 98f6bf3fc8ea3057 = code before demo mode (measurement 1, ADOPT round 1). 19 Nov UI polish (headings, green
# "kontrol edildi", Turkish review time, counterparty origin wording) changed demo-off pages on purpose (065ed4472500212a);
# 19 Nov UI polish 2/2 ("Önce bak" box, card anchors, wider charts with label halo) again on purpose:
# 19 Nov review fixes: reliability tile says 'proje sahibinin kör seçimi' (was 'analistin'): 92e18915f63b1d79 ->
# 19 Nov: chart label halo removed (it drew light blobs over the labels in the dark theme): 324bb603b3585996 ->
# 22 Nov: overview (/genel) and review history (/kontroller) added as fixture pages, and two menu links on every page;
# the 7 earlier pages with the two links removed still hash to aab4a6dc9387972c (checked, PROJECT_NOTES 22 Nov) ->
# 22 Nov outside review: brief/card name the measured fields (agent.FIELDS_NOTE); with the old sentence put back the
# pages hash to 9b10fac6b84d4d9e (checked) ->
# 22 Nov watchlist (4b): day_watch fixture page added; the 9 earlier pages still hash to 551d570425036047 ->
# 22 Nov watchlist UX: neutral "takipte" badge, secondary button (only day_watch changed; 9 pages still 551d570425036047) ->
# 22 Nov watchlist (Feyza): own WATCH_CSS for the card button (day_watch changed again: 10 pages de1d687f01efac36), then
# 4c overview_watch page added; the 9 pages before the watchlist still hash to 551d570425036047 (checked) ->
# ec99f5a881d4a55e -> 22 Nov second outside review: reliability tiles name the live flag rate (Set D) and the 12/12
# amount-only order, limits line 100/48/20/18; with reliability.py put back the pages hash to ec99f5a881d4a55e (checked) ->
# 9627515c0eb5328f -> 23 Nov audit: "En iyi regex" -> "Repodaki en güçlü regex" on the reliability page (README wording);
# with reliability.py put back the pages hash to 9627515c0eb5328f (checked) ->
OFF_SHA256='74722eb763ca586d'


def _self_test():
    from morning import reason_text
    samples={'size_vs_history':{'ratio':2.0,'n_history':4},'size_vs_revenue':{'ratio':0.2,'source':'own','extreme':True},
             'size_absolute':{'n_history':1},'no_rate':{'currency':'XAU'},'foreign_currency':{'currency':'USD'},
             'foreign_counterparty':{},'long_contract':{'years':2.5},'related_party':{},'revision':{},'no_amount':{},
             'no_increase':{}}
    for code,extra in samples.items():   # the text rule hides exactly the Matriks-based codes
        assert bool(REASON_RE.match(reason_text({'code':code,**extra})))==(code in HIDDEN_REASONS),code
    assert reason_text({'code':'no_rate','currency':None}).endswith('kur yok, büyüklük hesaplanmadı') and REASON_RE.match(reason_text({'code':'no_rate','currency':None}))
    assert reasons(['a','TL karşılığına göre büyüklük (x)','tutar / şirketin yıllık geliri: %1','b'])==['a',PLACEHOLDER,'b']
    m=desk_map({'X':'Gama','Y':'Alfa','Z':'Alfa','W':'Beta'},{})
    assert m=={'Alfa':'Masa 1','Beta':'Masa 2','Gama':'Masa 3'}
    assert desk_map({'X':'Gama','Y':'Alfa'},{'Gama':'Ortak','Alfa':'Ortak'})=={'Gama':'Masa 1','Alfa':'Masa 1'}
    plain='# Arama: Irak\n\n1. 2026-11-16 | ZQXA | https://www.kap.org.tr/tr/Bildirim/1\nTutar: 1.500.000 USD\n'
    assert redact_answer(plain)==plain   # lines that carry no Matriks value are untouched
    import demo_mode as dm   # the module panel/chat/form read (this file may run as __main__)
    saved=dm.ON
    try:
        dm.ON=False
        off=fixture_pages()
        dm.ON=True
        on=fixture_pages()
    finally:
        dm.ON=saved
    for field,marker in MARKERS.items():
        assert any(marker in body(p) for p in off.values()),f'fixture does not show {field}'   # the test can see it
        leaks=[k for k,p in on.items() if marker in body(p)]
        assert not leaks,f'{field} leaks in demo mode: {leaks}'
    assert pages_hash(off)==OFF_SHA256,'demo-off pages changed: '+pages_hash(off)
    d,c,w=body(on['day']),body(on['chat']),body(on['week'])
    for visible in (URL+'1','1.500.000 USD','<mark>1.500.000</mark>','KONTROL ET:','yüksek','döviz (USD)','süre 3,0 yıl',
                    'name="decision" value="confirm"','Masa 1 (2)','Masa 3 (1)',PLACEHOLDER,'Demo modu'):
        assert visible in d,visible
    assert 'Masa 2' not in d   # Beta (not on the day) keeps number 2: Gama is 3 on every day
    assert 'masalar: Masa 1 (1), Masa 3 (1), Atanmamış (1)' in w and PLACEHOLDER in body(on['form'])
    for visible in ('Tutar: 1.500.000 USD','Kaynak cümle:','Önem: yüksek; '+PLACEHOLDER+'; döviz (USD); süre 3,0 yıl',
                    f'| yeni | {PLACEHOLDER} |','Olağandışı mı: '+PLACEHOLDER,'<div class="ah">1. ZQXA - yüksek</div>',
                    '2 bildirim, 1 güncelleme/düzeltme.','Önceki 4 günde 1 yeni iş ilişkisi bildirimi var'):
        assert visible in c,visible
    assert on['reliability']==off['reliability'].replace('<main>','<main>'+BANNER,1)   # no licensed value on it
    print(f'self-test ok: {len(samples)+9+2*len(MARKERS)} checks ({len(on)} pages, {len(MARKERS)} markers, leaks 0, off hash {OFF_SHA256})')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--off-hash',action='store_true',help='print the demo-off fixture hash (to fill OFF_SHA256 from main)')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.off_hash:
        print(pages_hash(fixture_pages()))
    else:
        ap.error('give --self-test')


if __name__=='__main__':
    main()
