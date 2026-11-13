'''Desk e-mails for n8n (rule: docs/n8n_routing_rule.md). Code decides desk, order and text; n8n only sends.

`payload(day, items, sectors, desks)` -> {'day', 'desks': [{'desk', 'to', 'subject', 'text', 'kap_urls'}]}.
Least data: company, look-first / check flags, reason labels without numbers, KAP link, panel link.
No amounts, ratios, currencies or disclosure text (the desk opens the card in the panel).

Self-test: python scripts/desk_mail.py --self-test
'''
import re
import sys

DOMAIN='masa.local'
PANEL='http://127.0.0.1:8765'
# reason codes -> labels without numbers (morning.reason_text carries ratios and amounts; not for e-mail)
REASON_LABEL={'size_vs_history':'şirketin önceki işlerine göre büyük','size_vs_revenue':'şirketin gelirine göre büyük',
              'size_absolute':'TL karşılığına göre büyük','foreign_currency':'dövizli','foreign_counterparty':'yurt dışı karşı taraf',
              'long_contract':'uzun süreli','related_party':'ilişkili taraf (grup içi)','revision':'revizyon',
              'no_amount':'tutar yok','no_rate':'kur yok, büyüklük hesaplanmadı','no_increase':'tutar artmamış'}
FOLD=str.maketrans('çğıöşüâîû','cgiosuaiu')


def mailbox(desk):
    '''"Savunma ve Havacılık" -> savunma-ve-havacilik@masa.local (ASCII, stable).'''
    s=(desk or '').replace('İ','i').replace('I','ı').lower().replace('̇','').translate(FOLD)
    s=re.sub(r'[^a-z0-9]+','-',s).strip('-')[:60].strip('-') or 'atanmamis'
    return f'{s}@{DOMAIN}'


def look_first(item):
    imp=item['importance']
    return bool(imp['needs_review'] or imp['level']=='high')


def item_lines(n,item):
    from morning import REVIEW_TR
    from names import company_label
    imp=item['importance']
    tags=[]
    if imp['level']=='high':
        tags.append('ÖNCE BAK')
    if imp['needs_review']:
        tags.append('KONTROL ET: '+'; '.join(REVIEW_TR.get(c,c) for c in imp['needs_review_reasons']))
    head=f'{n}. {company_label(item["symbol"])}'+(f' - {" | ".join(tags)}' if tags else '')
    lines=[head]
    reasons=[REASON_LABEL[r['code']] for r in imp.get('reasons',[]) if r.get('code') in REASON_LABEL]
    if reasons:
        lines.append('   Neden: '+', '.join(dict.fromkeys(reasons)))
    lines.append(f'   KAP: {item.get("kap_url")}')
    return lines


def payload(day,items,sectors,desks):
    '''One e-mail per desk that has items (morning priority order inside, desks as in the panel).'''
    from panel import by_desk
    out=[]
    for desk,its in by_desk(items,sectors,desks).items():
        k=sum(look_first(i) for i in its)
        m=sum(bool(i['importance']['needs_review']) for i in its)
        lines=[f'Masa: {desk}',f'Gün: {day}',f'{len(its)} bildirim; önce bak {k}, kontrol et {m}.','']
        for n,i in enumerate(its,1):
            lines+=item_lines(n,i)
        lines+=['',f'Panel (tutar, kart, kontrol): {PANEL}/day/{day}',
                'Kaynak: KAP bildirimleri ve Matriks verisi. Sıralama kurallıdır, tahmin değildir; karar öncesi KAP metnini okuyun.',
                'Bu e-posta yerel KAP asistanı tarafından oluşturuldu; masa ataması Matriks sektörüne göredir.']
        out.append({'desk':desk,'to':mailbox(desk),'subject':f'{day} | {desk}: {len(its)} bildirim, {k} önce bak',
                    'text':'\n'.join(lines)+'\n','kap_urls':[i.get('kap_url') for i in its]})
    return {'day':day,'desks':out}


MONEY_LEAK_RE=re.compile(r'\d[\d.,]*\s*(%|tl\b|try\b|usd\b|eur\b|dolar|avro|euro|milyon|milyar|bin\b)|%\s*\d',re.I)


def leaks(text):
    '''docs/n8n_routing_rule.md X: a number with a currency / scale word or a percent sign.'''
    return bool(MONEY_LEAK_RE.search(text))


def _self_test():
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
    print('self-test ok: 12 checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
