import json
import re
import sys

import pytest

import main
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


def test_attribution_removes_only_recorded_layer_reasons():
    def row(*reasons, error=None):
        return {'reasons_a': reasons, 'flagged_a': bool(reasons), 'error_a': error}

    rows = [
        row('currency_unclear', 'cumulative_total', error='wrong_amount'),
        row('currency_unclear', 'amount_vs_matriks'),
        row('currency_unclear', 'run_error', error='missed'),
        row('amount_not_in_text', 'judge_error', error='wrong_amount'),
        row(error='wrong_currency'),
        row(),
    ]
    result = evidence.attribution_view(rows, 'a')
    baseline = result['baseline']
    assert (baseline['reviewed'], baseline['flagged_errors'], baseline['silent_errors']) == (4, 3, 1)
    assert (baseline['review_rate'], baseline['automatic_coverage']) == (4 / 6, 2 / 6)
    assert (baseline['silent_error_rate'], baseline['selective_risk']) == (1 / 6, 1 / 2)
    assert (baseline['reviewed_no_recorded_error'], baseline['automatic_no_recorded_error']) == (1, 1)
    layers = result['layers']
    code = layers['code checks']
    assert (code['flagged'], code['unique_flags'], code['unique_catches']) == (3, 1, 1)
    assert (code['marginal_reviewed'], code['marginal_catches']) == (1, 1)
    assert code['leave_one_out']['selective_risk'] == 2 / 3
    assert layers['source check (judge)']['leave_one_out'] == baseline
    for layer in ('run error', 'judge error'):
        assert layers[layer]['protected'] and 'leave_one_out' not in layers[layer]
        with pytest.raises(ValueError, match='Mandatory review sources'):
            evidence.policy_metrics([({layer}, True)], removed=layer)
    pair = next(p for p in result['pairwise_overlap'] if (p['a'], p['b']) == ('Matriks cross-check', 'code checks'))
    assert (pair['intersection'], pair['p_b_given_a'], pair['p_a_given_b']) == (1, 1, 1 / 3)
    assert any(p['p_b_given_a'] is None for p in result['pairwise_overlap'])
    assert result['coverage_multiplicity'] == [
        {'review_sources': 0, 'cases': 2, 'recorded_errors': 1},
        {'review_sources': 1, 'cases': 1, 'recorded_errors': 1},
        {'review_sources': 2, 'cases': 3, 'recorded_errors': 2},
    ]


def test_attribution_undefined_denominators_and_unattributed_flag():
    assert evidence.attribution_view([])['baseline']['automatic_coverage'] is None
    row = {'flagged': True, 'reasons': ['other'], 'error': None}
    report = evidence.attribution_view([row])
    assert report['baseline']['selective_risk'] is None
    layer = report['layers'][evidence.UNAVAILABLE_LAYER]
    assert layer['status'] == 'UNAVAILABLE' and layer['protected'] and 'leave_one_out' not in layer


def test_shared_codes_keep_frozen_group_with_unknown_producer():
    row = {'flagged': True, 'reasons': ['currency_unclear', 'total_lt_amount'], 'error': 'missed'}
    report = evidence.attribution_view([row])
    assert report['attribution_unit'] == 'recorded_reason_code_group'
    for code, group in (('currency_unclear', 'code checks'), ('total_lt_amount', 'extraction code')):
        assert report['shared_reason_code_producers'][code] == 'UNAVAILABLE'
        assert evidence.layer_of(code) == group
        assert report['layers'][group]['flagged'] == 1
        assert report['layers'][group]['marginal_catches'] == 0


def test_attribution_cli_matches_frozen_evidence(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['main.py', 'layer-attribution'])
    main.main()
    stdout = capsys.readouterr().out
    report = json.loads(stdout)
    c_rows = evidence.load()
    d_rows = evidence.load(evidence.SET_D_EVIDENCE)
    assert all(row['id_hash'] not in stdout for row in c_rows + d_rows)

    def check_metrics(metrics, rows):
        frozen = evidence.recount(rows)
        assert (metrics['n'], metrics['reviewed'], metrics['flagged_errors'], metrics['silent_errors']) == (
            frozen['n'], frozen['flagged'], frozen['caught'], frozen['silent']
        )

    check_metrics(report['set_c']['baseline'], c_rows)
    for layer in ('Matriks cross-check', 'source check (judge)'):
        assert report['set_c']['layers'][layer] == {'status': 'NOT_RUN_IN_EXPERIMENT'}
    for group, n in (('all', 50), ('R', 38), ('U', 12)):
        rows = [row for row in d_rows if group == 'all' or row['stratum'] == group]
        for run in 'ab':
            views = report['set_d'][group]
            assert views[run]['baseline']['n'] == n
            for key, two_read in ((run, False), (f'two_read_{run}', True)):
                scoring_rows = [
                    {
                        'flagged': row[f'flagged_{run}'] or (two_read and row['disagree']),
                        'error': row[f'error_{run}'],
                        'reasons': row[f'reasons_{run}'],
                    }
                    for row in rows
                ]
                check_metrics(views[key]['baseline'], scoring_rows)
            without_disagreement = views[f'two_read_{run}']['layers'][evidence.DISAGREE_LAYER]['leave_one_out']
            assert without_disagreement == views[run]['baseline']


def test_verify_results_cli_still_has_five_matches(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['main.py', 'verify-results'])
    main.main()
    stdout = capsys.readouterr().out
    assert len(re.findall(r'\bMATCH\b', stdout)) == 5
    assert 'MISMATCH' not in stdout


INJECTION_KEYS = {
    'id_hash',
    'attack',
    'counts',
    'success',
    'flagged',
    'matriks_record',
    'caught_layer1',
    'caught_layer2',
}


def test_injection_file_has_only_safe_fields():
    # 18 Set C texts x 4 attacks; layer results only on silent successes; no numbers in the values
    rows = evidence.load(evidence.INJECTION_EVIDENCE)
    assert len(rows) == 72 and len({r['id_hash'] for r in rows}) == 18
    assert {r['id_hash'] for r in rows} <= {r['id_hash'] for r in evidence.load()}
    assert {r['attack'] for r in rows} == {'amount', 'currency', 'review', 'format'}
    for r in rows:
        assert set(r) == INJECTION_KEYS
        silent = r['counts'] and r['success'] and not r['flagged']
        for k in ('caught_layer1', 'caught_layer2'):
            assert isinstance(r[k], bool) if silent else r[k] is None
        values = [v for k, v in r.items() if k != 'id_hash']
        assert not re.search(r'\d', json.dumps(values))


def test_injection_recount_matches_results_md():
    p = evidence.published_injection()
    assert p == {'n': 18, 'silent': 9, 'both': 0, 'upper': 15.3, 'layer_alone': 0}
    assert evidence.injection_matches(evidence.recount_injection(evidence.load(evidence.INJECTION_EVIDENCE)), p)


def test_injection_mismatch_is_detected(tmp_path):
    md = tmp_path / 'results.md'
    md.write_text(
        '| Layered: x | texts 61-78 | silent **9 → 1** (95% upper 24.5%); y | z |\n'
        'On 61-78 each layer alone also reached 0/18\n'
    )
    c = evidence.recount_injection(evidence.load(evidence.INJECTION_EVIDENCE))
    assert not evidence.injection_matches(c, evidence.published_injection(md))


def test_injection_recount_rule():
    # silent = counted, succeeded and not flagged; "both" leaves only what neither layer catches
    def row(attack, counts, success, flagged, l1=None, l2=None):
        return {
            'attack': attack,
            'counts': counts,
            'success': success,
            'flagged': flagged,
            'caught_layer1': l1,
            'caught_layer2': l2,
        }

    rows = [
        row('amount', True, True, False, False, True),
        row('amount', True, True, True),
        row('amount', True, False, False),
        row('review', False, False, False),
    ]
    c = evidence.recount_injection(rows)
    assert c['amount'] == {'n': 3, 'success': 2, 'silent': 1, 'layer1': 1, 'layer2': 0, 'both': 0}
    assert c['review']['n'] == 0


def test_rag_file_has_only_safe_fields():
    # 20 questions; ranks are 1-10 or null (not in the top 10); no question or text
    rows = evidence.load(evidence.RAG_EVIDENCE)
    assert len(rows) == 20 and len({r['id_hash'] for r in rows}) == 20
    for r in rows:
        assert set(r) == {'id_hash', 'rank_embed', 'rank_rerank', 'same_company_top1'}
        assert re.fullmatch(r'[0-9a-f]{16}', r['id_hash'])
        for k in ('rank_embed', 'rank_rerank'):
            assert r[k] is None or (isinstance(r[k], int) and 1 <= r[k] <= 10)
        assert isinstance(r['same_company_top1'], bool)


def test_rag_recount_matches_results_md():
    p = evidence.published_rag()
    assert p == {'n': 20, 'embed_at1': 15, 'rerank_at1': 17, 'rerank_at5': 20}
    assert evidence.recount_rag(evidence.load(evidence.RAG_EVIDENCE)) == p


def test_rag_mismatch_is_detected(tmp_path):
    md = tmp_path / 'results.md'
    md.write_text('| + cross-encoder rerank (x) | Set D (20) | top 1 15 → **18**, top 5 **20/20**, y | z |\n')
    assert evidence.recount_rag(evidence.load(evidence.RAG_EVIDENCE)) != evidence.published_rag(md)
