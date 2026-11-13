'''Relative periods in a question ("geçen hafta", "bu ay", "son 3 ay"), parsed by code.

Rule: docs/relative_periods_rule.md (phrase table fixed before code and questions).
`period(question, today)` -> (start, end) dates or None. `question_period` adds the rule that a written
single day ("28 Ekim", "dün", ISO) wins over a period. The router prompt is not changed.

Self-test: python scripts/periods.py --self-test
'''
import re
import sys
from calendar import monthrange
from datetime import date, timedelta

FOLD=str.maketrans('çğıöşüâîû','cgiosuaiu')
NUMBERS={'bir':1,'iki':2,'uc':3,'dort':4,'bes':5,'alti':6,'yedi':7,'sekiz':8,'dokuz':9,'on':10,
         'on bir':11,'onbir':11,'on iki':12,'oniki':12}
# Turkish case / plural endings after the unit word (folded): "ayda", "yılın", "haftalık", "ayki"
SUF=r'(?:daki|deki|da|de|ta|te|dir|dur|nin|nun|in|un|si|i|u|lik|luk|ki)?\b'
UNIT=r'(gun|hafta|ay|ceyrek|yil|sene)'
NUM=r'(\d{1,2}|'+'|'.join(sorted(NUMBERS,key=len,reverse=True))+r')'
LAST_RE=re.compile(r'\bson\s+(?:'+NUM+r'\s+)?'+UNIT+SUF)
NAMED_RE=re.compile(r'\b(bu|gecen|gectigimiz)\s+'+UNIT+SUF)


def fold(text):
    '''Turkish lower case folded to ASCII (İ->i, I->ı->i); same as agent.fold.'''
    return (text or '').replace('İ','i').replace('I','ı').lower().replace('̇','').translate(FOLD)


def months_back(day,n):
    '''Same day number n months earlier, clipped to that month's last day.'''
    y,m=divmod(day.year*12+day.month-1-n,12)
    return date(y,m+1,min(day.day,monthrange(y,m+1)[1]))


def quarter_start(day):
    return date(day.year,(day.month-1)//3*3+1,1)


def named(which,unit,today):
    if unit=='gun':
        return None   # "bu gün" / "geçen gün" are not in the table
    if unit=='hafta':
        monday=today-timedelta(days=today.weekday())
        return (monday,today) if which=='bu' else (monday-timedelta(days=7),monday-timedelta(days=1))
    if unit=='ay':
        first=today.replace(day=1)
        if which=='bu':
            return first,today
        last=first-timedelta(days=1)
        return last.replace(day=1),last
    if unit=='ceyrek':
        first=quarter_start(today)
        if which=='bu':
            return first,today
        last=first-timedelta(days=1)
        return quarter_start(last),last
    first=date(today.year,1,1)   # yil / sene
    return (first,today) if which=='bu' else (date(today.year-1,1,1),date(today.year-1,12,31))


def last_n(n,unit,today):
    if unit=='gun':
        return today-timedelta(days=n),today
    if unit=='hafta':
        return today-timedelta(days=7*n),today
    if unit=='ay':
        return months_back(today,n),today
    if unit=='ceyrek':
        return None   # "son N çeyrek" is not in the table
    return months_back(today,12*n),today   # yil / sene


def period(question,today):
    '''(start, end) for the first period phrase in the question, else None.'''
    q=' '.join(fold(question).split())
    found=[]
    for m in LAST_RE.finditer(q):
        num,unit=m.group(1),m.group(2)
        n=1 if num is None else (int(num) if num.isdigit() else NUMBERS[num])
        if n>0:
            found.append((m.start(),last_n(n,unit,today)))
    for m in NAMED_RE.finditer(q):
        which='bu' if m.group(1)=='bu' else 'gecen'
        found.append((m.start(),named(which,m.group(2),today)))
    found=[f for f in found if f[1]]
    return min(found)[1] if found else None


def question_period(question,today):
    '''The rule's combination: a written single day wins, then the period phrase.'''
    from route_eval import word_date
    if word_date(question,today):
        return None
    return period(question,today)


def _self_test():
    t=date(2026,11,13)   # Friday
    cases={
        'Bu hafta hangi bildirimler geldi?':(date(2026,11,9),t),
        'ASELS geçen hafta ne aldı?':(date(2026,11,2),date(2026,11,8)),
        'GEÇTİĞİMİZ HAFTA savunma sözleşmeleri':(date(2026,11,2),date(2026,11,8)),
        'bu ay enerji ihaleleri':(date(2026,11,1),t),
        'gecen ay THYAO':(date(2026,10,1),date(2026,10,31)),
        'Geçen ayki siparişler':(date(2026,10,1),date(2026,10,31)),
        'bu çeyrek ihracat':(date(2026,10,1),t),
        'geçen çeyrekte hangi işler':(date(2026,7,1),date(2026,9,30)),
        'bu yıl KONTR':(date(2026,1,1),t),
        'Geçen sene imzalananlar':(date(2025,1,1),date(2025,12,31)),
        'son 3 ayda ASELS':(date(2026,8,13),t),
        'Son üç ayda':(date(2026,8,13),t),
        'son on iki ayda':(date(2025,11,13),t),
        'son 10 gün':(date(2026,11,3),t),
        'son iki haftada':(date(2026,10,30),t),
        'Aselsan son bir yılda hangi işleri aldı?':(date(2025,11,13),t),
        'son ayda gelenler':(date(2026,10,13),t),
    }
    for q,want in cases.items():
        assert period(q,t)==want,(q,period(q,t))
    for q in ('ASELS son bildirimi ne?','Önceki hafta','birkaç gün önce','son günlerde ne oldu','ayın başında',
              'bu ayrıntı önemli mi','son ayrılık','SON YILLARDA','bu aylarda','bugün neye bakmalıyım','Irak projeleri','son çeyrek'):
        assert period(q,t) is None,q
    assert months_back(date(2026,3,31),1)==date(2026,2,28) and months_back(date(2026,1,15),2)==date(2025,11,15)
    assert period('geçen ay ve bu hafta',t)==(date(2026,10,1),date(2026,10,31))   # first phrase wins
    assert period('geçen hafta',date(2026,11,9))==(date(2026,11,2),date(2026,11,8))   # on a Monday
    assert period('geçen ay',date(2026,1,5))==(date(2025,12,1),date(2025,12,31))
    assert question_period('28 Ekim ve geçen hafta',t) is None and question_period('dün geçen hafta',t) is None
    assert question_period('geçen hafta',t)==(date(2026,11,2),date(2026,11,8))
    print(f'self-test ok: {len(cases)+18} checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
