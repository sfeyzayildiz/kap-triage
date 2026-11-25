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


def test_recount_matches_results_md():
    p = evidence.published()
    assert p == {'n': 100, 'silent': 1, 'upper': 4.7, 'flagged': 11}
    assert evidence.matches(evidence.recount(evidence.load()), p)


def test_mismatch_is_detected(tmp_path):
    md = tmp_path / 'results.md'
    md.write_text('| x | Set C (held-out, 100) | **2 silent errors (95% upper 6.2%), 11 flagged** | PASS |\n')
    assert not evidence.matches(evidence.recount(evidence.load()), evidence.published(md))


REGEX_KEYS = {'baseline', 'id_hash', 'found', 'reasons', 'error'}


def test_regex_file_has_only_safe_fields():
    # 100 Set C items per baseline, the same items as set_c.jsonl, no numbers outside the hash
    rows = evidence.load(evidence.REGEX_EVIDENCE)
    set_c_ids = {r['id_hash'] for r in evidence.load()}
    assert len(rows) == 200
    for name in ('a', 'b'):
        assert {r['id_hash'] for r in rows if r['baseline'] == name} == set_c_ids
    for r in rows:
        assert set(r) == REGEX_KEYS
        assert isinstance(r['found'], bool)
        assert all(re.fullmatch(r'[a-z_]{1,40}', x) for x in r['reasons'])
        assert r['error'] in ERRORS
        rest = {k: v for k, v in r.items() if k != 'id_hash'}
        assert not re.search(r'\d', json.dumps(rest))


def test_regex_recount_matches_results_md():
    p = evidence.published_regex()
    assert p == {'a': {'silent': 25, 'with_checks': 23, 'n': 100}, 'b': {'silent': 29, 'with_checks': 26, 'n': 100}}
    assert evidence.regex_matches(evidence.recount_regex(evidence.load(evidence.REGEX_EVIDENCE)), p)


def test_regex_mismatch_is_detected(tmp_path):
    md = tmp_path / 'results.md'
    md.write_text(
        '| x (A) / A + all code checks | Set C | 24 / 23 silent errors out of 100 | y |\n'
        '| x (B) / B + all code checks | Set C | 29 / 26 silent errors out of 100 | y |\n'
    )
    c = evidence.recount_regex(evidence.load(evidence.REGEX_EVIDENCE))
    assert not evidence.regex_matches(c, evidence.published_regex(md))


def test_regex_recount_rule():
    # a regex error is always silent; with the code checks only when no reason code was raised
    rows = [
        {'baseline': 'a', 'id_hash': 'x', 'found': True, 'reasons': [], 'error': None},
        {'baseline': 'a', 'id_hash': 'y', 'found': False, 'reasons': [], 'error': 'missed'},
        {'baseline': 'a', 'id_hash': 'z', 'found': True, 'reasons': ['cumulative_total'], 'error': 'wrong_amount'},
    ]
    c = evidence.recount_regex(rows)['a']
    assert (c['n'], c['found'], c['silent'], c['with_checks'], c['flagged']) == (3, 2, 2, 1, 1)


def test_recount_rule():
    rows = [
        {'id_hash': 'a', 'flagged': False, 'reasons': [], 'error': None},
        {'id_hash': 'b', 'flagged': False, 'reasons': [], 'error': 'missed'},
        {'id_hash': 'c', 'flagged': True, 'reasons': ['currency_unclear'], 'error': 'wrong_amount'},
    ]
    c = evidence.recount(rows)
    assert (c['n'], c['silent'], c['flagged'], c['caught']) == (3, 1, 1, 1)


SET_D_KEYS = {'id_hash', 'stratum', 'disagree'} | {f'{k}_{r}' for k in ('flagged', 'reasons', 'error') for r in 'ab'}


def test_set_d_file_has_only_safe_fields():
    # 50 items, 12 census (U) + 38 random (R), none of them in Set C, no numbers outside the hash
    rows = evidence.load(evidence.SET_D_EVIDENCE)
    assert len(rows) == 50 and len({r['id_hash'] for r in rows}) == 50
    assert sum(r['stratum'] == 'R' for r in rows) == 38
    assert not {r['id_hash'] for r in rows} & {r['id_hash'] for r in evidence.load()}
    for r in rows:
        assert set(r) == SET_D_KEYS and r['stratum'] in ('U', 'R')
        for run in 'ab':
            assert isinstance(r[f'flagged_{run}'], bool) and r[f'error_{run}'] in ERRORS
            assert all(re.fullmatch(r'[a-z_]{1,40}', x) for x in r[f'reasons_{run}'])
        rest = {k: v for k, v in r.items() if k != 'id_hash'}
        assert not re.search(r'\d', json.dumps(rest))


def test_set_d_recount_matches_results_md():
    p = evidence.published_set_d()
    assert (p['silent_a'], p['silent_b'], p['disagree'], p['t1'], p['flag_lo'], p['flag_hi']) == (0, 1, 3, 0, 20, 22)
    assert evidence.recount_set_d(evidence.load(evidence.SET_D_EVIDENCE)) == p


def test_set_d_mismatch_is_detected(tmp_path):
    md = tmp_path / 'results.md'
    md.write_text(
        'on Set D: 20-22% of 50 new texts, 21-24% on the random 38\n'
        'disagree 3/50; new flags over run a **0/50** (bar 3); run a silent 0/50, run b silent **0/50**, '
        'caught by the flag (0/0); on the random 38 alone 0/38 (95% upper 7.6%) and 0/38 (7.6%)\n'
    )
    assert evidence.recount_set_d(evidence.load(evidence.SET_D_EVIDENCE)) != evidence.published_set_d(md)


def test_layer_counts_rule():
    # an item counts once per layer it has; "only" when no other layer flagged it
    rows = [
        {'reasons_a': ['currency_unclear', 'cumulative_total']},
        {'reasons_a': ['currency_unclear', 'amount_vs_matriks']},
        {'reasons_a': ['share_unclear']},
        {'reasons_a': []},
    ]
    c = evidence.layer_counts(rows, 'a')
    assert c['code checks'] == {'items': 2, 'only': 1}
    assert c['Matriks cross-check'] == {'items': 1, 'only': 0}
    assert c[evidence.MODEL_LAYER] == {'items': 1, 'only': 1}
