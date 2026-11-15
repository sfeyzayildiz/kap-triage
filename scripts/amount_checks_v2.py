'''amount_checks v2 (rule: docs/set_d_rule.md). v1 (amount_checks.py) stays frozen.

Only change: the money regex also reads "ABD Doları" / "Amerikan Doları" as USD, so
cumulative_total can compare USD amounts written that way (known issue B5).
amount_is_projection does not use the money regex, so it is v1's.
'''
import re

from amount_checks import CUMULATIVE,NUM_TOKEN,SCALE_ALT,_close,_lower,amount_is_projection,cur_code,parse_number

USD_WORDS=r'(?:ABD|Amerikan)\s+Dolar[ıi]?'
CUR=rf'{USD_WORDS}|TL|TRY|USD|EUR|GBP|Euro|Avro|Dolar|₺|\$|€|£|\?'
MONEY_RE=re.compile(
    rf'(?P<n1>{NUM_TOKEN})(?:\s*(?P<s1>{SCALE_ALT})\b)?\s*(?P<c1>{CUR})'
    rf'|(?P<c2>{CUR})\s*(?P<n2>{NUM_TOKEN})(?:\s*(?P<s2>{SCALE_ALT})\b)?',
    re.IGNORECASE)
USD_WORDS_RE=re.compile(USD_WORDS,re.IGNORECASE)

__all__=['amount_is_projection','cumulative_total','money_values']


def cur_code_v2(c):
    return 'USD' if c and USD_WORDS_RE.fullmatch(c.strip()) else cur_code(c)


def money_values(text):
    out=[]
    for m in MONEY_RE.finditer(text):
        if m.group('n1'):
            token,scale,cur=m.group('n1'),m.group('s1'),m.group('c1')
        else:
            token,scale,cur=m.group('n2'),m.group('s2'),m.group('c2')
        v=parse_number(token,scale)
        if v:
            out.append((v,cur_code_v2(cur)))
    return out


def cumulative_total(text,amount,currency):
    '''Same logic as v1, with the v2 money regex.'''
    if not text or amount is None:
        return False
    if not CUMULATIVE.search(_lower(text)):
        return False
    code=cur_code(currency)
    vals=[v for v,c in money_values(text) if code is None or c==code]
    if not vals:
        return False
    biggest=max(vals)
    return amount<biggest and not _close(amount,biggest)


def _self_test():
    import amount_checks as v1
    usd=('Önceki siparişe ek olarak 1.200.000 ABD Doları tutarında sipariş alınmış, '
         'toplam sipariş tutarı 3.867.260 ABD Doları seviyesine ulaşmıştır.')
    assert money_values('3.867.260 ABD Doları')==[(3867260.0,'USD')]
    assert money_values('Amerikan Doları 2,5 milyon')==[(2500000.0,'USD')]
    assert v1.money_values('3.867.260 ABD Doları')==[]                       # the v1 gap
    assert cumulative_total(usd,1200000,'USD') and not v1.cumulative_total(usd,1200000,'USD')
    assert not cumulative_total(usd,3867260,'USD')
    same=['Şirketimiz 50.000.000 TL tutarında sözleşme imzalamıştır.',
          "Önceki siparişe ek olarak 74.480.297 TL tutarında sipariş alınmış, toplam sipariş tutarı 124.938.460 TL'ye ulaşmıştır.",
          '2.600.000,00 USD tutarında (yaklaşık 92.981.720,00 TL) sözleşme. İlave talepler ile nihai tutar 4.750.000,00 USD olmuştur.']
    for t in same:                                                             # no 'ABD Doları': identical to v1
        assert money_values(t)==v1.money_values(t)
        for a,c in ((74480297,'TRY'),(2600000,'USD'),(50000000,'TRY')):
            assert cumulative_total(t,a,c)==v1.cumulative_total(t,a,c)
    print('self-test ok: 8 checks')


if __name__=='__main__':
    _self_test()
