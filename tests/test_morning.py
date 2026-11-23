'''Tests moved from morning.py (v1 self-test).'''
from datetime import datetime
import duckdb
from kap_triage.analysis.morning import history, priority, render


def test_morning():
    con=duckdb.connect()
    con.execute('CREATE TABLE disclosures (symbol VARCHAR, published_at TIMESTAMP, is_update BOOLEAN, is_correction BOOLEAN)')
    con.executemany('INSERT INTO disclosures VALUES (?,?,?,?)',[
        ('AAA',datetime(2026,5,1,9),False,False),('AAA',datetime(2026,9,1,9),True,False),
        ('AAA',datetime(2025,1,1,9),False,False),('BBB',datetime(2026,9,1,9),False,False)])
    h=history(con,'AAA',datetime(2026,10,1,9))
    assert h=={'n':2,'n_updates':1,'last':'2026-09-01'}
    assert history(con,'CCC',datetime(2026,10,1,9))=={'n':0,'n_updates':0,'last':None}
    con.close()

    imp={'score':5,'level':'high','kind':'new','needs_review':False,'needs_review_reasons':[],'amount_try':6.3e7,
         'reasons':[{'code':'size_vs_history','ratio':3.5,'n_history':4,'points':3},{'code':'foreign_currency','currency':'USD','points':1}]}
    low={'score':0,'level':'low','kind':'new','needs_review':True,'needs_review_reasons':['currency_unclear'],
         'reasons':[{'code':'no_amount','points':0}]}
    hist={'n':0,'n_updates':0,'last':None}
    items=[{'symbol':'LOW','kap_url':'u2','amount':None,'importance':{**low,'needs_review':False,'needs_review_reasons':[]},
            'reaction':{'status':'too_early'},'history':hist},
           {'symbol':'FLAG','kap_url':'u3','amount':None,'importance':low,'reaction':{'status':'no_bar'},'history':hist},
           {'symbol':'BIG','kap_url':'u1','amount':1500000.0,'currency':'USD','importance':imp,
            'reaction':{'status':'ok','t0':'2026-10-30','ar0':0.021,'z0':2.4,'possible_split':False},'history':hist,
            'similar':[{'published_at':'2026-05-01 09:00:00','score':0.914,'kap_url':'u9'}]}]
    text=render('2026-10-30',items)
    assert '3 bildirim; önce bakılacak: 2' in text
    assert text.index('BIG')<text.index('FLAG')<text.index('LOW')
    assert '1.500.000 USD' in text and 'medyanının 3,5 katı' in text and '+2,1%' in text
    assert 'KONTROL ET: para birimi belirsiz' in text
    assert 'Benzer eski bildirim: 2026-05-01 (benzerlik 0,91) u9' in text
    assert 'Bugün yeni iş ilişkisi bildirimi yok.' in render('2026-11-01',[])
    # ordering v2: inside a group, a long contract first, then the larger TRY amount; no amount last
    mk=lambda a,long=False:{'importance':{'needs_review':False,'level':'low','score':9 if a is None else 0,'amount_try':a,
                                          'reasons':[{'code':'long_contract'}] if long else []}}
    order=sorted([mk(None),mk(5e6),mk(9e8),mk(1e6,long=True)],key=priority)
    assert [i['importance']['amount_try'] for i in order]==[1e6,9e8,5e6,None]
