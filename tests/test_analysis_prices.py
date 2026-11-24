"""kap_triage/analysis/prices.py: the checks of the v1 self-test in price_moves.py, on made-up data (no network, no real data)."""

from datetime import date, datetime, timedelta
import duckdb
from kap_triage.analysis.prices import (
    INDEX,
    Z_ABNORMAL,
    abnormal,
    daily_returns,
    disclosures_before,
    event_reaction,
    reaction_day,
    scan,
)


def test_price_moves():
    days = [date(2026, 1, 1) + timedelta(days=i) for i in range(80)]
    idx = [(d, 100.0) for d in days]
    stock, price = [], 10.0
    for i, d in enumerate(days):
        price *= 1.01 if i % 2 else 0.99
        if i == 70:
            price *= 1.08  # abnormal day
        if i == 75:
            price *= 0.5  # split
        stock.append((d, price))
    series = {INDEX: idx, 'AAA': stock}
    market = daily_returns(idx)
    ar = abnormal(daily_returns(stock), market)

    assert reaction_day(datetime(2026, 1, 5, 17, 59), days) == date(2026, 1, 5)
    assert reaction_day(datetime(2026, 1, 5, 18, 0), days) == date(2026, 1, 6)
    assert reaction_day(datetime(2026, 12, 1, 9), days) is None

    moves, splits = scan(series, days[70])
    assert len(moves) == 1 and moves[0]['symbol'] == 'AAA' and moves[0]['z'] > Z_ABNORMAL and splits == 0
    moves, splits = scan(series, days[75])
    assert moves == [] and splits == 1
    assert scan(series, days[71])[0] == []

    out = event_reaction(ar, days, datetime.combine(days[69], datetime.min.time()).replace(hour=19))
    assert out['status'] == 'ok' and out['t0'] == str(days[70]) and out['car_days'] == 3 and not out['possible_split']
    out = event_reaction(ar, days, datetime.combine(days[74], datetime.min.time()).replace(hour=19))
    assert out['possible_split']
    out = event_reaction(ar, days, datetime.combine(days[10], datetime.min.time()).replace(hour=9))
    assert out['status'] == 'short_history' and out['z0'] is None

    con = duckdb.connect()
    con.execute('CREATE TABLE disclosures (news_id BIGINT, kap_url VARCHAR, symbol VARCHAR, published_at TIMESTAMP)')
    con.executemany(
        'INSERT INTO disclosures VALUES (?,?,?,?)',
        [
            (1, 'u1', 'AAA', datetime(2026, 3, 9, 19, 0)),
            (2, 'u2', 'AAA', datetime(2026, 3, 11, 18, 30)),
            (3, 'u3', 'AAA', datetime(2026, 3, 1, 9, 0)),
            (4, 'u4', 'BBB', datetime(2026, 3, 10, 9, 0)),
        ],
    )
    assert [x['news_id'] for x in disclosures_before(con, 'AAA', date(2026, 3, 11))] == ['1']
    con.close()
