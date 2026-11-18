'''Rule-based currency_unclear check (definition frozen in PROJECT_NOTES).

Flags a TL amount (TL, TRY, ₺, broken '?') that is immediately followed by a
foreign-currency amount (USD, $, EUR, €, GBP, £) in parentheses, when the
parentheses contain no explicit equivalence word (karşılığı, karşılık gelen,
eşdeğer). Exchange-rate words alone (kur, güncel kur, TCMB) do not resolve it.
Action elsewhere: needs_review=true + flag currency_unclear; amount unchanged.
'''
import re

NUM=r'(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)'
SCALE=r'(?:\s*(?:milyar|milyon|bin))?'
TL=r'(?:(?:TL|TRY)(?![A-Za-zÇĞİÖŞÜçğıöşü])|₺|\?)'
FX=r'(?:(?:USD|EUR|GBP)(?![A-Za-z])|\$|€|£)'
TL_AMT=rf'(?:{NUM}{SCALE}\s*{TL}|{TL}\s*{NUM}{SCALE})'
FX_AMT=rf'(?:{NUM}{SCALE}\s*{FX}|{FX}\s*{NUM}{SCALE})'

PATTERN=re.compile(rf'{TL_AMT}\s*\(([^()]{{0,300}})\)')
FX_RE=re.compile(FX_AMT)
# Matched on lowercased text with all whitespace removed, so split
# characters ('karşı lığı') and uppercase forms are still caught.
EQUIV=re.compile(r'karşılığı|karşılıkgelen|eşdeğer')


def _norm(s):
    # Turkish-aware lowercase: Python maps 'I' to 'i', Turkish needs 'ı'.
    s=s.replace('I','ı').replace('İ','i').lower()
    return re.sub(r'\s+','',s)


def find_unclear(text):
    '''Return the matched snippets that trigger currency_unclear.'''
    if not text:
        return []
    hits=[]
    for m in PATTERN.finditer(text):
        inner=m.group(1)
        if FX_RE.search(inner) and not EQUIV.search(_norm(inner)):
            hits.append(m.group(0))
    return hits


def currency_unclear(text):
    return len(find_unclear(text))>0


def _self_test():
    cases=[
        ('50.000.000 TL (1.500.000 USD) tutarında',True),
        ('50.000.000 TL (1.500.000 USD karşılığı)',False),
        ('50.000.000 TL (güncel kur ile 1.500.000 USD)',True),
        ('1.500.000 USD (50.000.000 TL)',False),
        ('₺12.000.000 (300.000 €)',True),
        ('12.000.000 ? (300.000 EUR)',True),
        ('50 milyon TL (yaklaşık 1,5 milyon $ eşdeğeri)',False),
        ('50.000.000 TL (KDV hariç)',False),
        ('TL 50.000.000 ($1.500.000)',True),
        ('50.000.000 TL (1.500.000 USD KARŞILIĞI)',False),
        ('50.000.000 TL (1.500.000 USD karşı lığı)',False),
        ('50.000.000 TL\xa0(1.500.000 USD)',True),
        ('5.000.000 TRY (150.000 GBP)',True),
        ('18.602.919,36TL (450.000 USD)',True),
    ]
    for text,expected in cases:
        got=currency_unclear(text)
        assert got==expected,f'{text!r}: expected {expected}, got {got}'
    print(f'self-test OK ({len(cases)} cases)')


if __name__=='__main__':
    _self_test()