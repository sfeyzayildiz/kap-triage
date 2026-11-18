'''Post-hoc code checks on the chosen amount (designed after the Set B error analysis).

They never change the amount; they only add a needs_review flag.
  amount_is_projection: revenue/projection wording near the chosen amount
  cumulative_total:     cumulative wording in the text and the chosen amount is
                        smaller than the largest amount in the same currency
Any Set B number that uses these checks is optimistic (leaked).
'''
import re

NUM_TOKEN=r'\d(?:[\d.,]*\d)?'
SCALE_WORDS={'bin':1e3,'thousand':1e3,'milyon':1e6,'million':1e6,'mn':1e6,'milyar':1e9,'billion':1e9,'bn':1e9}
SCALE_ALT=r'bin|thousand|milyon|million|mn|milyar|billion|bn'
CUR=r'TL|TRY|USD|EUR|GBP|Euro|Avro|Dolar|₺|\$|€|£|\?'
NUM_RE=re.compile(rf'({NUM_TOKEN})(?:\s*({SCALE_ALT})\b)?',re.IGNORECASE)
MONEY_RE=re.compile(
    rf'(?P<n1>{NUM_TOKEN})(?:\s*(?P<s1>{SCALE_ALT})\b)?\s*(?P<c1>{CUR})'
    rf'|(?P<c2>{CUR})\s*(?P<n2>{NUM_TOKEN})(?:\s*(?P<s2>{SCALE_ALT})\b)?',
    re.IGNORECASE)
CUR_CODES={'tl':'TRY','try':'TRY','₺':'TRY','?':'TRY',
           'usd':'USD','$':'USD','dolar':'USD',
           'eur':'EUR','€':'EUR','euro':'EUR','avro':'EUR',
           'gbp':'GBP','£':'GBP'}

# matched on Turkish-lowercased text
# 'yıllık'/'annual' left out: in Turkish it also means 'N-year' (3 yıllık sözleşme)
PROJECTION=re.compile(r'ciro|bütçelen|revenue|turnover|budgeted')
CUMULATIVE=re.compile(r'ek olarak|ilave|toplamda|toplam sipariş|ulaşmıştır|additional|in total|cumulative')
WINDOW=120
TOL=0.005


def _lower(s):
    # Turkish-aware lowercase that keeps string length, so indices still match
    return s.replace('I','ı').replace('İ','i').lower()


def cur_code(c):
    return CUR_CODES.get(c.strip().lower()) if c else None


def parse_number(token,scale=None):
    '''Parse a number in Turkish (1.234,5) or English (1,234.5) format.'''
    mult=SCALE_WORDS.get(scale.lower(),1) if scale else 1
    dots,commas=token.count('.'),token.count(',')
    if dots and commas:
        dec='.' if token.rfind('.')>token.rfind(',') else ','
    elif dots+commas==1:
        # one separator: exactly 3 digits after it means thousands, else decimal
        sep='.' if dots else ','
        dec=None if len(token)-token.find(sep)-1==3 else sep
    elif dots>1:
        dec=','
    elif commas>1:
        dec='.'
    else:
        dec=None
    if dec is None:
        s=token.replace('.','').replace(',','')
    else:
        thou=',' if dec=='.' else '.'
        s=token.replace(thou,'').replace(dec,'.')
    try:
        return float(s)*mult
    except ValueError:
        return None


def _close(a,b):
    return a is not None and b is not None and b!=0 and abs(a-b)/abs(b)<=TOL


def _positions(text,amount):
    '''Spans in the text where the chosen amount is written.'''
    return [(m.start(),m.end()) for m in NUM_RE.finditer(text)
            if _close(parse_number(m.group(1),m.group(2)),amount)]


def money_values(text):
    '''(value, currency code) for all numbers written next to a currency.'''
    out=[]
    for m in MONEY_RE.finditer(text):
        if m.group('n1'):
            token,scale,cur=m.group('n1'),m.group('s1'),m.group('c1')
        else:
            token,scale,cur=m.group('n2'),m.group('s2'),m.group('c2')
        v=parse_number(token,scale)
        if v:
            out.append((v,cur_code(cur)))
    return out


def amount_is_projection(text,amount):
    if not text or amount is None:
        return False
    low=_lower(text)
    for s,e in _positions(text,amount):
        if PROJECTION.search(low[max(0,s-WINDOW):e+WINDOW]):
            return True
    return False


def cumulative_total(text,amount,currency):
    if not text or amount is None:
        return False
    if not CUMULATIVE.search(_lower(text)):
        return False
    code=cur_code(currency)
    # compare only with amounts in the chosen currency (TL conversions of a USD amount are not totals)
    vals=[v for v,c in money_values(text) if code is None or c==code]
    if not vals:
        return False
    biggest=max(vals)
    return amount<biggest and not _close(amount,biggest)
