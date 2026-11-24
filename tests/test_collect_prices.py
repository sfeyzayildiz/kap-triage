"""kap_triage/collect/prices.py: the checks of the v1 self-test in price_collect.py, on made-up data (no network, no real data)."""

import gzip
import json
from datetime import date, datetime
import duckdb
from kap_triage.collect.prices import SCHEMA, count_jumps, decode, done_symbols, in_collection_window, parse_bars


def test_price_collect():
    bars = [
        {
            'date': '2026-10-01',
            'time': 1,
            'open': 10,
            'high': 11,
            'low': 9,
            'close': 10,
            'volume': 5,
            'totalQuantity': 1,
            'weightedAverage': 10,
        },
        {'date': '2026-10-02', 'time': 2, 'close': 5},
        {'date': '2026-10-03', 'time': 3, 'close': 0},
        {'time': 4, 'close': 7},
    ]
    raw = json.dumps(bars).encode()
    assert decode(raw) == bars and decode(gzip.compress(raw)) == bars
    try:
        decode(b'{"err":"x"}')
        raise AssertionError('dict must be rejected')
    except ValueError:
        pass
    rows = parse_bars('ABC', bars)
    assert len(rows) == 2 and rows[0][1] == date(2026, 10, 1) and rows[0][5] == 10 and rows[1][2] is None
    assert count_jumps(rows) == 1
    assert count_jumps(rows[:1]) == 0
    assert in_collection_window(datetime(2026, 11, 2, 23, 43)) and in_collection_window(datetime(2026, 11, 2, 23, 30))
    assert not in_collection_window(datetime(2026, 11, 2, 23, 29)) and not in_collection_window(
        datetime(2026, 11, 2, 0, 5)
    )
    con = duckdb.connect()
    con.execute(SCHEMA)
    con.executemany('INSERT OR REPLACE INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?)', rows + rows)
    assert con.execute('SELECT count(*) FROM daily_bars').fetchall()[0][0] == 2
    con.close()
    man = [
        {'symbol': 'A', 'status': 'ok', 'end': '2026-11-01'},
        {'symbol': 'B', 'status': 'http_503', 'end': '2026-11-01'},
        {'symbol': 'C', 'status': 'ok', 'end': '2026-11-11'},
    ]
    assert done_symbols(man, date(2026, 11, 11)) == {'C'}  # a refresh re-pulls A (older end) and B (failed)
    assert done_symbols(man, date(2026, 11, 1)) == {'A'}  # a resumed pull with the same end skips A
