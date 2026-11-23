'''kap_triage/web/form.py: the checks of the v1 self-test in form.py, on made-up data (no network, no real data).'''
from datetime import date, datetime
from kap_triage.web.form import LAST, TYPES, build_request, display_names, e, render_body, render_choices, run


def test_form():
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
