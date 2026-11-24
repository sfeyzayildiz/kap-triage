"""kap_triage/collect/pull_guard.py: the checks of the v1 self-test in pull_guard.py, on made-up data (no network, no real data)."""

import os
import tempfile
from datetime import date
from kap_triage.collect.pull_guard import AlreadyPulled, claim, pulled_today, read_marker


def test_pull_guard():
    d1, d2 = date(2026, 11, 11), date(2026, 11, 12)
    with tempfile.TemporaryDirectory() as tmp:
        p, l = os.path.join(tmp, 'm.txt'), os.path.join(tmp, 'l.txt')
        assert read_marker(p) is None and pulled_today(d1, p) is None
        assert claim('prices', today=d1, path=p, log=l) is None
        assert pulled_today(d1, p) == 'prices' and pulled_today(d2, p) is None
        for kind, kw in (('collector', {}), ('prices', {}), ('prod_refresh', {'after': ('sectors',)})):
            try:
                claim(kind, today=d1, path=p, log=l, **kw)
                raise AssertionError('must refuse')
            except AlreadyPulled as e:
                assert 'prices' in str(e) and p in str(e)
        assert claim('prices', resume=True, today=d1, path=p, log=l) == 'prices'  # resumable same-kind session
        assert claim('sectors', after=('prices',), today=d1, path=p, log=l) == 'prices'  # same approved session
        assert pulled_today(d1, p) == 'sectors'
        assert claim('collector', today=d2, path=p, log=l) is None  # next day is free
        with open(l, encoding='utf-8') as f:
            lines = f.read().splitlines()
        assert len(lines) == 4 and lines[-1].startswith('2026-11-12 collector ')
        with open(p, 'w', encoding='utf-8') as f:
            f.write('garbage')
        assert (
            read_marker(p) is None and claim('collector', today=d1, path=p, log=l) is None
        )  # unreadable marker = none
