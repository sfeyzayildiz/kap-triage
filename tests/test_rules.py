"""Code rules on the disclosure text (kap_triage/analysis/rules.py). All texts are synthetic."""

from kap_triage.analysis.rules import (
    _close,
    amount_is_projection,
    cumulative_total,
    currency_unclear,
    money_values,
    norm_cur,
    parse_number,
)


def test_parse_number():
    # Turkish and English number formats, with a scale word
    assert parse_number('359.580.038,28') == 359580038.28
    assert parse_number('44,490,859') == 44490859
    assert parse_number('1,250.50') == 1250.5
    assert _close(parse_number('6,1', 'Milyon'), 6100000)


def test_amount_is_projection():
    # revenue/budget wording next to the amount -> flag
    assert amount_is_projection(
        'Müşteri ile 2027 yılında 6,1 Milyon EUR ciro büyüklüğünde bütçelenen proje alınmıştır.', 6100000
    )
    # a plain contract -> no flag
    assert not amount_is_projection('Şirketimiz 50.000.000 TL tutarında sözleşme imzalamıştır.', 50000000)
    # 'ciro' far from an amount that is not in the text -> no flag
    assert not amount_is_projection(
        'Ciro hedefimiz yüksektir. Şirketimiz 50.000.000 TL tutarında sözleşme imzalamıştır.', 12345
    )
    # '3 yıllık' (3-year) is not a projection word
    assert not amount_is_projection('3 yıllık sözleşme bedeli 381.600 USD olarak belirlenmiştir.', 381600)


def test_cumulative_total():
    cumul = "Önceki siparişe ek olarak 74.480.297 TL tutarında sipariş alınmış, toplam sipariş tutarı 124.938.460 TL'ye ulaşmıştır."
    assert cumulative_total(cumul, 74480297, 'TRY')  # the new part chosen, a bigger total exists -> flag
    assert not cumulative_total(cumul, 124938460, 'TRY')  # the total itself chosen -> no flag
    fx = (
        '2.600.000,00 USD tutarında (yaklaşık 92.981.720,00 TL) sözleşme imzalanmıştır. '
        'İlave talepler doğrultusunda nihai tutar 4.750.000,00 USD (yaklaşık 173.916.025,00 TL) olmuştur.'
    )
    assert not cumulative_total(fx, 4750000, 'USD')  # TL equivalents are not compared with a USD amount
    assert cumulative_total(fx, 2600000, 'USD')
    # two contracts without cumulative wording -> no flag
    assert not cumulative_total(
        'Şirketimiz 10.000.000 TL ve 5.000.000 TL tutarında iki sözleşme imzalamıştır.', 5000000, 'TRY'
    )
    assert not cumulative_total('Şirketimiz sözleşme imzalamıştır.', None, None)


def test_abd_dolari_is_usd():
    # the v2 change (docs/set_d_rule.md): "ABD Doları" / "Amerikan Doları" are read as USD
    assert money_values('3.867.260 ABD Doları') == [(3867260.0, 'USD')]
    assert money_values('Amerikan Doları 2,5 milyon') == [(2500000.0, 'USD')]
    usd = (
        'Önceki siparişe ek olarak 1.200.000 ABD Doları tutarında sipariş alınmış, '
        'toplam sipariş tutarı 3.867.260 ABD Doları seviyesine ulaşmıştır.'
    )
    assert cumulative_total(usd, 1200000, 'USD')
    assert not cumulative_total(usd, 3867260, 'USD')


def test_currency_unclear():
    # TL amount + foreign amount in parentheses, no equivalence word -> flag
    flagged = [
        '50.000.000 TL (1.500.000 USD) tutarında',
        '50.000.000 TL (güncel kur ile 1.500.000 USD)',
        '₺12.000.000 (300.000 €)',
        '12.000.000 ? (300.000 EUR)',
        'TL 50.000.000 ($1.500.000)',
        '50.000.000 TL\xa0(1.500.000 USD)',
        '5.000.000 TRY (150.000 GBP)',
        '18.602.919,36TL (450.000 USD)',
    ]
    # an equivalence word (any case, even split by a space), foreign first, or no foreign amount -> no flag
    clear = [
        '50.000.000 TL (1.500.000 USD karşılığı)',
        '1.500.000 USD (50.000.000 TL)',
        '50 milyon TL (yaklaşık 1,5 milyon $ eşdeğeri)',
        '50.000.000 TL (KDV hariç)',
        '50.000.000 TL (1.500.000 USD KARŞILIĞI)',
        '50.000.000 TL (1.500.000 USD karşı lığı)',
    ]
    assert all(currency_unclear(t) for t in flagged)
    assert not any(currency_unclear(t) for t in clear)


def test_norm_cur():
    # one code for the names used by Matriks and by the model
    assert norm_cur('tl') == 'TRY' and norm_cur('Türk Lirası') == 'TRY' and norm_cur('ABD Doları') == 'USD'
    assert norm_cur('chf') == 'CHF' and norm_cur('') is None
