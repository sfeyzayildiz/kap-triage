"""Code rules on the disclosure text. They never change an amount; they only add a review flag.

  amount_is_projection  revenue/projection wording near the chosen amount
  cumulative_total      cumulative wording in the text, and the chosen amount is smaller
                        than the largest amount written in the same currency
  currency_unclear      a TL amount followed by a foreign amount in parentheses,
                        with no equivalence word ("karşılığı") inside them

These are the live versions: amount_checks v1 with the v2 money regex that also reads
"ABD Doları" (docs/set_d_rule.md), and currency_check (definition frozen in PROJECT_NOTES).
"""

import re

# --- numbers -----------------------------------------------------------------

NUM_TOKEN = r'\d(?:[\d.,]*\d)?'
SCALE_WORDS = {
    'bin': 1e3,
    'thousand': 1e3,
    'milyon': 1e6,
    'million': 1e6,
    'mn': 1e6,
    'milyar': 1e9,
    'billion': 1e9,
    'bn': 1e9,
}
SCALE_ALT = r'bin|thousand|milyon|million|mn|milyar|billion|bn'
NUM_RE = re.compile(rf'({NUM_TOKEN})(?:\s*({SCALE_ALT})\b)?', re.IGNORECASE)
TOL = 0.005


def parse_number(token, scale=None):
    """Parse a number in Turkish (1.234,5) or English (1,234.5) format."""
    mult = SCALE_WORDS.get(scale.lower(), 1) if scale else 1
    dots, commas = token.count('.'), token.count(',')
    if dots and commas:
        dec = '.' if token.rfind('.') > token.rfind(',') else ','
    elif dots + commas == 1:
        # one separator: exactly 3 digits after it means thousands, else decimal
        sep = '.' if dots else ','
        dec = None if len(token) - token.find(sep) - 1 == 3 else sep
    elif dots > 1:
        dec = ','
    elif commas > 1:
        dec = '.'
    else:
        dec = None
    if dec is None:
        s = token.replace('.', '').replace(',', '')
    else:
        thou = ',' if dec == '.' else '.'
        s = token.replace(thou, '').replace(dec, '.')
    try:
        return float(s) * mult
    except ValueError:
        return None


def _close(a, b):
    return a is not None and b is not None and b != 0 and abs(a - b) / abs(b) <= TOL


def _lower(s):
    # Turkish-aware lowercase that keeps string length, so indices still match
    return s.replace('I', 'ı').replace('İ', 'i').lower()


# --- currencies --------------------------------------------------------------

USD_WORDS = r'(?:ABD|Amerikan)\s+Dolar[ıi]?'
MONEY_CUR = rf'{USD_WORDS}|TL|TRY|USD|EUR|GBP|Euro|Avro|Dolar|₺|\$|€|£|\?'
MONEY_RE = re.compile(
    rf'(?P<n1>{NUM_TOKEN})(?:\s*(?P<s1>{SCALE_ALT})\b)?\s*(?P<c1>{MONEY_CUR})'
    rf'|(?P<c2>{MONEY_CUR})\s*(?P<n2>{NUM_TOKEN})(?:\s*(?P<s2>{SCALE_ALT})\b)?',
    re.IGNORECASE,
)
USD_WORDS_RE = re.compile(USD_WORDS, re.IGNORECASE)
CUR_CODES = {
    'tl': 'TRY',
    'try': 'TRY',
    '₺': 'TRY',
    '?': 'TRY',
    'usd': 'USD',
    '$': 'USD',
    'dolar': 'USD',
    'eur': 'EUR',
    '€': 'EUR',
    'euro': 'EUR',
    'avro': 'EUR',
    'gbp': 'GBP',
    '£': 'GBP',
}
# currency names as written in Matriks records and model output (from v1 eval_vs_matriks.py)
CUR_MAP = {
    'tl': 'TRY',
    'try': 'TRY',
    'türk lirası': 'TRY',
    'usd': 'USD',
    'abd doları': 'USD',
    'dolar': 'USD',
    '$': 'USD',
    'eur': 'EUR',
    'euro': 'EUR',
    'avro': 'EUR',
    '€': 'EUR',
}


def cur_code(c):
    """Code of the chosen currency ('TL' -> 'TRY'); unknown -> None."""
    return CUR_CODES.get(c.strip().lower()) if c else None


def written_cur_code(c):
    """Code of a currency written in the text; also reads "ABD Doları" (v2)."""
    return 'USD' if c and USD_WORDS_RE.fullmatch(c.strip()) else cur_code(c)


def norm_cur(c):
    """ "tl" / "TRY" / "Türk Lirası" -> "TRY"; unknown names are upper-cased; empty -> None."""
    if not c:
        return None
    c = str(c).strip().lower()
    return CUR_MAP.get(c, c.upper())


def money_values(text):
    """(value, currency code) for all numbers written next to a currency."""
    out = []
    for m in MONEY_RE.finditer(text):
        if m.group('n1'):
            token, scale, cur = m.group('n1'), m.group('s1'), m.group('c1')
        else:
            token, scale, cur = m.group('n2'), m.group('s2'), m.group('c2')
        v = parse_number(token, scale)
        if v:
            out.append((v, written_cur_code(cur)))
    return out


# --- amount rules ------------------------------------------------------------

# matched on Turkish-lowercased text
# 'yıllık'/'annual' left out: in Turkish it also means 'N-year' (3 yıllık sözleşme)
PROJECTION = re.compile(r'ciro|bütçelen|revenue|turnover|budgeted')
CUMULATIVE = re.compile(r'ek olarak|ilave|toplamda|toplam sipariş|ulaşmıştır|additional|in total|cumulative')
WINDOW = 120


def amount_is_projection(text, amount):
    if not text or amount is None:
        return False
    low = _lower(text)
    for m in NUM_RE.finditer(text):
        if _close(parse_number(m.group(1), m.group(2)), amount):
            if PROJECTION.search(low[max(0, m.start() - WINDOW) : m.end() + WINDOW]):
                return True
    return False


def cumulative_total(text, amount, currency):
    if not text or amount is None:
        return False
    if not CUMULATIVE.search(_lower(text)):
        return False
    code = cur_code(currency)
    # compare only with amounts in the chosen currency (TL conversions of a USD amount are not totals)
    vals = [v for v, c in money_values(text) if code is None or c == code]
    if not vals:
        return False
    biggest = max(vals)
    return amount < biggest and not _close(amount, biggest)


# --- currency rule -----------------------------------------------------------
# Exchange-rate words alone (kur, güncel kur, TCMB) do not resolve it.

NUM = r'(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)'
SCALE = r'(?:\s*(?:milyar|milyon|bin))?'
TL = r'(?:(?:TL|TRY)(?![A-Za-zÇĞİÖŞÜçğıöşü])|₺|\?)'
FX = r'(?:(?:USD|EUR|GBP)(?![A-Za-z])|\$|€|£)'
TL_AMT = rf'(?:{NUM}{SCALE}\s*{TL}|{TL}\s*{NUM}{SCALE})'
FX_AMT = rf'(?:{NUM}{SCALE}\s*{FX}|{FX}\s*{NUM}{SCALE})'
PATTERN = re.compile(rf'{TL_AMT}\s*\(([^()]{{0,300}})\)')
FX_RE = re.compile(FX_AMT)
# matched on lowercased text with all whitespace removed, so 'karşı lığı' and uppercase forms are caught
EQUIV = re.compile(r'karşılığı|karşılıkgelen|eşdeğer')


def find_unclear(text):
    """The matched snippets that trigger currency_unclear."""
    if not text:
        return []
    hits = []
    for m in PATTERN.finditer(text):
        inner = m.group(1)
        if FX_RE.search(inner) and not EQUIV.search(re.sub(r'\s+', '', _lower(inner))):
            hits.append(m.group(0))
    return hits


def currency_unclear(text):
    return len(find_unclear(text)) > 0
