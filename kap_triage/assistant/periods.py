'''Relative periods in a question ("geçen hafta", "bu ay", "son 3 ay"), parsed by code.

Rule: docs/relative_periods_rule.md (phrase table fixed before code and questions).
`period(question, today)` -> (start, end) dates or None. `question_period` adds the rule that a written
single day ("28 Ekim", "dün", ISO) wins over a period. The router prompt is not changed.

'''
import re
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
# a written single day (from v1 route_eval.py): "dün", "bugün", ISO, "28 Ekim [2026]"
MONTHS={'ocak':1,'şubat':2,'subat':2,'mart':3,'nisan':4,'mayıs':5,'mayis':5,'haziran':6,'temmuz':7,
        'ağustos':8,'agustos':8,'eylül':9,'eylul':9,'ekim':10,'kasım':11,'kasim':11,'aralık':12,'aralik':12}
DATE_WORD_RE=re.compile(r'\b(\d{1,2})\s+('+'|'.join(MONTHS)+r')(?:\s+(\d{4}))?',re.I)
ISO_RE=re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')


def fold(text):
    '''Turkish lower case folded to ASCII (İ->i, I->ı->i).'''
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


def word_date(question,today):
    q=question.lower()
    if re.search(r'\bdün\b|\bdun\b',q):
        return today-timedelta(days=1)
    if re.search(r'\bbugün\b|\bbugun\b',q):
        return today
    m=ISO_RE.search(q)
    if m:
        try:
            return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
        except ValueError:
            return None
    m=DATE_WORD_RE.search(q)
    if m:
        try:
            return date(int(m.group(3) or today.year),MONTHS[m.group(2).lower()],int(m.group(1)))
        except ValueError:
            return None
    return None


def question_period(question,today):
    '''The rule's combination: a written single day wins, then the period phrase.'''
    if word_date(question,today):
        return None
    return period(question,today)



