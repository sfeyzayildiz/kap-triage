import json
import re

from kap_triage.analysis import evidence

KEYS = {'id_hash', 'flagged', 'reasons', 'error'}
ERRORS = {None, 'fabricated', 'missed', 'wrong_amount', 'wrong_currency'}


def test_published_file_has_only_safe_fields():
    rows = evidence.load()
    assert len(rows) == 100
    assert len({r['id_hash'] for r in rows}) == 100
    for r in rows:
        assert set(r) == KEYS
        assert re.fullmatch(r'[0-9a-f]{16}', r['id_hash'])
        assert isinstance(r['flagged'], bool) and r['flagged'] == bool(r['reasons'])
        assert all(re.fullmatch(r'[a-z_]{1,40}', x) for x in r['reasons'])
        assert r['error'] in ERRORS


def test_no_numbers_outside_the_hash():
    text = evidence.EVIDENCE.read_text(encoding='utf-8')
    for line in text.splitlines():
        r = json.loads(line)
        r.pop('id_hash')
        assert not re.search(r'\d', json.dumps(r))


def test_recount_matches_published():
    c = evidence.recount(evidence.load())
    assert {k: c[k] for k in evidence.PUBLISHED} == evidence.PUBLISHED


def test_recount_rule():
    rows = [
        {'id_hash': 'a', 'flagged': False, 'reasons': [], 'error': None},
        {'id_hash': 'b', 'flagged': False, 'reasons': [], 'error': 'missed'},
        {'id_hash': 'c', 'flagged': True, 'reasons': ['currency_unclear'], 'error': 'wrong_amount'},
    ]
    c = evidence.recount(rows)
    assert (c['n'], c['silent'], c['flagged'], c['caught']) == (3, 1, 1, 1)
