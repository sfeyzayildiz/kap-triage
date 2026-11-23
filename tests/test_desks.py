'''kap_triage/analysis/desks.py: the checks of the v1 self-test in desk_mail.py, on made-up data (no network, no real data).'''
from kap_triage.analysis.desks import leaks, mailbox, payload


def test_desk_mail():
    item=lambda nid,sym,level,flag,codes:{'news_id':nid,'symbol':sym,'kap_url':f'https://www.kap.org.tr/tr/Bildirim/{nid}',
        'amount':1500000.0,'currency':'USD',
        'importance':{'level':level,'score':5,'needs_review':flag,'needs_review_reasons':['currency_unclear'] if flag else [],
                      'reasons':[{'code':c,'ratio':0.18,'years':3,'currency':'USD','n_history':4} for c in codes],
                      'amount_try':50000000.0}}
    items=[item('1','AAA','low',False,[]),item('2','BBB','high',False,['size_vs_revenue','foreign_currency','long_contract']),
           item('3','AAA','medium',True,['foreign_currency']),item('4','ZZZ','low',False,['no_amount'])]
    sectors={'AAA':'Savunma','BBB':'Enerji'}
    p=payload('2026-11-12',items,sectors,{})
    desks=[d['desk'] for d in p['desks']]
    assert sorted(desks)==['Atanmamış','Enerji','Savunma'] and len(p['desks'])==3
    sav=next(d for d in p['desks'] if d['desk']=='Savunma')
    assert sav['to']=='savunma@masa.local' and sav['kap_urls'][0].endswith('/3')   # flagged first (priority)
    assert sav['subject']=='2026-11-12 | Savunma: 2 bildirim, 1 önce bak' and 'KONTROL ET: para birimi belirsiz' in sav['text']
    en=next(d for d in p['desks'] if d['desk']=='Enerji')
    assert 'ÖNCE BAK' in en['text'] and 'şirketin gelirine göre büyük, dövizli, uzun süreli' in en['text']
    assert all(not leaks(d['text']+d['subject']) for d in p['desks'])   # the amount and the ratio never reach the text
    assert sorted(u for d in p['desks'] for u in d['kap_urls'])==sorted(i['kap_url'] for i in items)
    assert mailbox('Savunma ve Havacılık')=='savunma-ve-havacilik@masa.local' and mailbox('İLAÇ, Kimya')=='ilac-kimya@masa.local'
    assert mailbox('Atanmamış')=='atanmamis@masa.local' and mailbox('')=='atanmamis@masa.local'
    assert leaks('tutar 1.500.000 USD') and leaks('gelirin %18,0') and leaks('3 milyon') and leaks('18 %')
    assert not leaks('2026-11-12 | Savunma: 2 bildirim, 1 önce bak') and not leaks('https://www.kap.org.tr/tr/Bildirim/1503392')
    assert payload('2026-11-12',[],sectors,{})=={'day':'2026-11-12','desks':[]}
