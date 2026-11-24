"""kap_triage/assistant/periods.py: the checks of the v1 self-test in periods.py, on made-up data (no network, no real data)."""

from datetime import date
from kap_triage.assistant.periods import months_back, period, question_period


def test_periods():
    t = date(2026, 11, 13)  # Friday
    cases = {
        'Bu hafta hangi bildirimler geldi?': (date(2026, 11, 9), t),
        'ASELS geçen hafta ne aldı?': (date(2026, 11, 2), date(2026, 11, 8)),
        'GEÇTİĞİMİZ HAFTA savunma sözleşmeleri': (date(2026, 11, 2), date(2026, 11, 8)),
        'bu ay enerji ihaleleri': (date(2026, 11, 1), t),
        'gecen ay THYAO': (date(2026, 10, 1), date(2026, 10, 31)),
        'Geçen ayki siparişler': (date(2026, 10, 1), date(2026, 10, 31)),
        'bu çeyrek ihracat': (date(2026, 10, 1), t),
        'geçen çeyrekte hangi işler': (date(2026, 7, 1), date(2026, 9, 30)),
        'bu yıl KONTR': (date(2026, 1, 1), t),
        'Geçen sene imzalananlar': (date(2025, 1, 1), date(2025, 12, 31)),
        'son 3 ayda ASELS': (date(2026, 8, 13), t),
        'Son üç ayda': (date(2026, 8, 13), t),
        'son on iki ayda': (date(2025, 11, 13), t),
        'son 10 gün': (date(2026, 11, 3), t),
        'son iki haftada': (date(2026, 10, 30), t),
        'Aselsan son bir yılda hangi işleri aldı?': (date(2025, 11, 13), t),
        'son ayda gelenler': (date(2026, 10, 13), t),
    }
    for q, want in cases.items():
        assert period(q, t) == want, (q, period(q, t))
    for q in (
        'ASELS son bildirimi ne?',
        'Önceki hafta',
        'birkaç gün önce',
        'son günlerde ne oldu',
        'ayın başında',
        'bu ayrıntı önemli mi',
        'son ayrılık',
        'SON YILLARDA',
        'bu aylarda',
        'bugün neye bakmalıyım',
        'Irak projeleri',
        'son çeyrek',
    ):
        assert period(q, t) is None, q
    assert months_back(date(2026, 3, 31), 1) == date(2026, 2, 28) and months_back(date(2026, 1, 15), 2) == date(
        2025, 11, 15
    )
    assert period('geçen ay ve bu hafta', t) == (date(2026, 10, 1), date(2026, 10, 31))  # first phrase wins
    assert period('geçen hafta', date(2026, 11, 9)) == (date(2026, 11, 2), date(2026, 11, 8))  # on a Monday
    assert period('geçen ay', date(2026, 1, 5)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert question_period('28 Ekim ve geçen hafta', t) is None and question_period('dün geçen hafta', t) is None
    assert question_period('geçen hafta', t) == (date(2026, 11, 2), date(2026, 11, 8))
    print(f'self-test ok: {len(cases) + 18} checks')
