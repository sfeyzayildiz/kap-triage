"""Importance score (kap_triage/analysis/importance.py): duration parsing, FX rate and company
history from a small in-memory DuckDB, then the points for each kind of item."""

from datetime import date

import duckdb

from kap_triage.analysis.importance import company_baseline, duration_years, fx_rate, revenue_base, score

BASE = {
    'amount': 700.0,
    'currency': 'TRY',
    'counterparty_origin': 'unknown',
    'related_party': None,
    'is_revision': False,
    'previous_amount': None,
    'duration': None,
    'needs_review': False,
}


def test_duration_years():
    assert duration_years('3 yıl') == 3 and duration_years('36 ay') == 3
    assert duration_years('2 yıl 6 ay') == 2 and duration_years('teslim tarihi 31.12.2027') is None
    assert abs(duration_years('18 months') - 1.5) < 1e-9 and duration_years(None) is None
    assert duration_years('2026 yılı sonuna kadar') is None and duration_years('730 gün') == 2


def test_rate_and_history():
    con = duckdb.connect()
    con.execute('CREATE TABLE new_business (sym VARCHAR, date DATE, cur VARCHAR, amount DOUBLE, tcmb_ex_rt DOUBLE)')
    con.executemany(
        'INSERT INTO new_business VALUES (?,?,?,?,?)',
        [
            ('AAA', date(2026, 1, 5), 'TRY', 100.0, 1.0),
            ('AAA', date(2026, 2, 5), 'USD', 10.0, 20.0),
            ('AAA', date(2026, 3, 5), 'TRY', 300.0, 1.0),
            ('AAA', date(2026, 10, 1), 'TRY', 9999.0, 1.0),
            ('AAA', date(2026, 9, 25), ' USD', 1.0, 40.0),
            ('BBB', date(2026, 3, 5), 'TRY', 50.0, 1.0),
        ],
    )
    assert fx_rate(con, 'USD', date(2026, 9, 30)) == 40.0  # latest Matriks rate before the day
    assert fx_rate(con, 'USD', date(2026, 10, 20)) is None  # too old -> no rate
    assert fx_rate(con, 'TRY', date(2026, 10, 20)) == 1.0
    assert company_baseline(con, 'AAA', date(2026, 9, 1)) == (200.0, 3)  # median of earlier amounts, count
    assert company_baseline(con, 'BBB', date(2026, 9, 1))[1] == 1
    con.close()


def test_score_points():
    out = score(BASE, 1.0, 200.0, 3)
    assert out['score'] == 3 and out['level'] == 'medium' and out['reasons'][0]['ratio'] == 3.5
    out = score({**BASE, 'currency': 'USD', 'counterparty_origin': 'foreign', 'duration': '3 yıl'}, 40.0, 200.0, 3)
    assert out['score'] == 5 and out['level'] == 'high'
    # foreign counterparty and related party give no points (docs/fields_rule.md)
    assert 'foreign_counterparty' not in {r['code'] for r in out['reasons']}
    out = score({**BASE, 'related_party': True}, 1.0, 200.0, 3)
    assert out['score'] == 3 and 'related_party' not in {r['code'] for r in out['reasons']}
    out = score({**BASE, 'amount': None}, 1.0, 200.0, 3)
    assert out['score'] == 0 and out['reasons'][0]['code'] == 'no_amount'
    out = score({**BASE, 'currency': 'XYZ'}, None, 200.0, 3)
    assert out['reasons'][0]['code'] == 'no_rate' and out['score'] == 1
    out = score({**BASE, 'is_revision': True, 'previous_amount': 650.0}, 1.0, 200.0, 3)
    assert out['kind'] == 'revision' and out['score'] == 0
    out = score({**BASE, 'amount': 2e9}, 1.0, None, 0)
    assert out['score'] == 2 and out['reasons'][0]['code'] == 'size_absolute'
    # a review flag is passed through, it does not change the points
    out = score({**BASE, 'needs_review': True, 'needs_review_reasons': ['currency_unclear']}, 1.0, 200.0, 3)
    assert out['score'] == 3 and out['needs_review'] and out['needs_review_reasons'] == ['currency_unclear']


def test_score_with_revenue():
    out = score(BASE, 1.0, 200.0, 3, revenue=1000.0, revenue_source='own')  # history 3.5x -> 3, revenue 0.7 -> 3
    assert (
        out['score'] == 3 and [r['points'] for r in out['reasons'][:2]] == [3, 0] and out['reasons'][1]['ratio'] == 0.7
    )
    out = score(
        {**BASE, 'amount': 50.0}, 1.0, 200.0, 3, revenue=1000.0, revenue_source='december'
    )  # history 0, revenue 5% -> 2
    assert out['score'] == 2 and out['reasons'][0]['points'] == 0
    assert out['reasons'][1] == {'code': 'size_vs_revenue', 'ratio': 0.05, 'source': 'december', 'points': 2}
    out = score({**BASE, 'amount': 6000.0}, 1.0, None, 0, revenue=1000.0, revenue_source='own')
    assert out['reasons'][1].get('extreme') is True and not out['needs_review']
    assert (
        score(BASE, 1.0, 200.0, 3, revenue=None)['reasons'][0]['points'] == 3
        and len(score(BASE, 1.0, 200.0, 3)['reasons']) == 1
    )


def test_revenue_base():
    con = duckdb.connect()
    con.execute('CREATE TABLE new_business (url VARCHAR, sym VARCHAR, date DATE, per INTEGER, shf_ret DOUBLE)')
    con.executemany(
        'INSERT INTO new_business VALUES (?,?,?,?,?)',
        [
            ('u1', 'AAA', date(2026, 5, 1), 202603, -50.0),
            ('u0', 'AAA', date(2026, 3, 1), 202512, 800.0),
            ('u9', 'AAA', date(2026, 9, 1), 202606, 900.0),
            ('u8', 'AAA', date(2026, 11, 1), 202612, 999.0),
            ('u2', 'AAA', date(2026, 6, 1), 202603, 700.0),
        ],
    )
    assert revenue_base(con, 'u2', 'AAA', date(2026, 6, 1)) == (700.0, 'own')
    assert revenue_base(con, 'u1', 'AAA', date(2026, 5, 1)) == (800.0, 'december')  # own negative -> December fallback
    assert revenue_base(con, 'none', 'AAA', date(2026, 10, 1)) == (800.0, 'december')  # a later December is not used
    assert revenue_base(con, 'none', 'BBB', date(2026, 10, 1)) == (None, None)
    con.close()
