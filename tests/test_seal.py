"""kap_triage/collect/seal.py: the checks of the v1 self-test in forward_seal.py, on made-up data (no network, no real data)."""

import json
import os
from kap_triage.collect.seal import canonical, seal, seal_day, sha, verify


def test_forward_seal():
    import tempfile

    it = lambda nid, lvl, flag: {
        'news_id': nid,
        'symbol': 'AAA',
        'published_at': '2026-11-16 10:00:00',
        'amount': 5.0,
        'importance': {'level': lvl, 'score': 3, 'needs_review': flag},
    }
    items = [it('2', 'low', False), it('1', 'high', False), it('3', 'low', True)]
    data = canonical(items)
    assert data == canonical(list(reversed(items))) and b'amount' not in data and b'"look_first":true' in data
    assert [r['look_first'] for r in json.loads(data)] == [True, False, True]
    with tempfile.TemporaryDirectory() as d:
        sd, lg = os.path.join(d, 's'), os.path.join(d, 'l.jsonl')
        h1, s1 = seal('2026-11-16', items, sd, lg)
        assert s1 == 'sealed' and len(h1) == 16 and h1 == sha(data)[:16]
        h2, s2 = seal('2026-11-16', items, sd, lg)
        assert (h2, s2) == (h1, 'same')
        h3, s3 = seal('2026-11-16', items[:1], sd, lg)
        assert (h3, s3) == (h1, 'reseal_mismatch')  # the first seal is kept
        assert verify(sd, lg) == (1, 1, [])
        with open(os.path.join(sd, '2026-11-16.json'), 'ab') as f:
            f.write(b' ')
        assert verify(sd, lg) == (0, 1, ['2026-11-16'])  # tampering is visible
    assert seal_day('2026-11-01') == '' and seal_day('2026-11-30') == ''  # outside the sealed window
