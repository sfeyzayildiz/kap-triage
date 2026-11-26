"""kap_triage/collect/collector.py without network: importing it needs no token, a missing token
is a clear error at request time, and the KAP form table becomes a dict."""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest

import kap_triage.collect.collector as collector
from kap_triage.collect.collector import CollectionStatus

DAY = date(2026, 11, 9)


def test_import_needs_no_token():
    env = {k: v for k, v in os.environ.items() if k != 'KAP_TOKEN'}
    subprocess.run([sys.executable, '-c', 'import kap_triage.collect.collector'], env=env, check=True)


def test_missing_token_is_a_clear_error(monkeypatch):
    monkeypatch.delenv('KAP_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='KAP_TOKEN is missing'):
        collector.token()


def test_parse_form():
    html = '<table><tr><td>Açıklama</td><td>Sözleşme imzalandı.</td></tr><tr><td>tek hücre</td></tr></table>'
    assert collector.parse_form(html) == {'Açıklama': 'Sözleşme imzalandı.'}  # rows without two cells are skipped
    assert collector.parse_form(None) == {}
    assert collector.parse_form('<table><tr><td> </td><td>Sentetik</td></tr></table>') == {}


@pytest.fixture
def database():
    with duckdb.connect(':memory:') as con:
        con.execute(Path(collector.SCHEMA_PATH).read_text(encoding='utf-8'))
        yield con


def news(news_id, day='2026-11-09'):
    return {
        'id': news_id,
        'date': f'{day}T12:00:00Z',
        'content': '<table><tr><td>Açıklama</td><td>Sentetik kayıt.</td></tr></table>',
    }


def business(url, **overrides):
    return {
        'url': url, 'sym': 'TEST', 'date': DAY.isoformat(), 'cur': 'TRY', 'amount': 50,
        'desc': 'synthetic', 'per': None, 'rt': None, 'shfRet': None, 'tcmbExRt': None,
        'cumRt': None, 'marValRt': None, **overrides,
    }


@pytest.mark.parametrize(
    ('search', 'expected'),
    [
        ({'id': 'query', 'messageCount': 0}, CollectionStatus.OK),
        ({'id': 'query', 'messageCount': 0, 'err': 'failed'}, CollectionStatus.FAILED),
        ({'messageCount': 0}, CollectionStatus.FAILED),
        ({'id': ' ', 'messageCount': 0}, CollectionStatus.FAILED),
        ({'id': 'query'}, CollectionStatus.FAILED),
        ({'id': 'query', 'messageCount': False}, CollectionStatus.FAILED),
    ],
)
def test_search_zero_requires_valid_response(monkeypatch, database, search, expected):
    get = Mock(return_value=search)
    monkeypatch.setattr(collector, 'get', get)
    assert collector.fetch_disclosures(database, DAY, DAY) == (expected, 0, 0)
    assert get.call_count == 1


@pytest.mark.parametrize(
    ('total', 'cap', 'second', 'expected', 'ids'),
    [
        (3, 10, [news(3)], CollectionStatus.OK, [1, 3]),
        (4, 10, [], CollectionStatus.PARTIAL, [1]),
        (4, 10, [news(3)], CollectionStatus.PARTIAL, [1, 3]),
        (4, 10, [news('1'), news(3)], CollectionStatus.PARTIAL, [1, 3]),
        (4, 10, RuntimeError('mock page HTTP error'), CollectionStatus.PARTIAL, [1]),
        (4, 4, [news(3), news(4)], CollectionStatus.PARTIAL, [1, 3, 4]),
        (6, 4, [news(3), news(4)], CollectionStatus.PARTIAL, [1, 3, 4]),
    ],
)
def test_pagination_retains_valid_records(monkeypatch, database, total, cap, second, expected, ids):
    monkeypatch.setattr(collector, 'PAGE_SIZE', 2)
    monkeypatch.setattr(collector, 'SEARCH_COUNT', cap)
    get = Mock(side_effect=[{'id': 'query', 'messageCount': total}, [news(1), news(2, '2026-11-08')], second])
    monkeypatch.setattr(collector, 'get', get)
    collector.save_disclosures(database, DAY, DAY, [news(99)])

    assert collector.fetch_disclosures(database, DAY, DAY) == (expected, len(ids), 1)
    assert database.execute('SELECT news_id FROM disclosures ORDER BY CAST(news_id AS INTEGER)').fetchall() == [
        (str(n),) for n in [*ids, 99]
    ]
    assert get.call_count == 3


@pytest.mark.parametrize(
    'body',
    [
        None, '', '   ', '<div></div>',
        '<table><tr><td>Açıklama</td><td>Yeni metin.</td></tr></table>',
        '<table><tr><td>Başlık</td><td>Yeni metin.</td></tr></table>https://www.kap.org.tr/Bildirim/123',
    ],
)
def test_incomplete_disclosure_cannot_overwrite_existing_record(monkeypatch, database, body):
    original = news(1)
    original['content'] += 'https://www.kap.org.tr/Bildirim/123'
    collector.save_disclosures(database, DAY, DAY, [original])
    incomplete = {key: value for key, value in original.items() if key != 'content'}
    if body is not None:
        incomplete['content'] = body
    get = Mock(side_effect=[{'id': 'query', 'messageCount': 1}, [incomplete]])
    monkeypatch.setattr(collector, 'get', get)
    assert collector.fetch_disclosures(database, DAY, DAY) == (CollectionStatus.FAILED, 0, 0)
    assert database.execute('SELECT kap_url, aciklama FROM disclosures').fetchone() == (
        'https://www.kap.org.tr/Bildirim/123', 'Sentetik kayıt.',
    )


@pytest.mark.parametrize('field', ['Güncelleme', 'Düzeltme'])
def test_complete_disclosure_can_update_existing_record(monkeypatch, database, field):
    original = news(1)
    original['content'] += 'https://www.kap.org.tr/Bildirim/123'
    collector.save_disclosures(database, DAY, DAY, [original])
    updated = news(1)
    updated['content'] = (
        f'<table><tr><td>Yapılan Açıklama {field} mi?</td><td>Evet</td></tr>'
        '<tr><td>Açıklama</td><td>Yeni metin.</td></tr></table>'
        'https://www.kap.org.tr/Bildirim/123'
    )
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[{'id': 'query', 'messageCount': 1}, [updated]]))
    assert collector.fetch_disclosures(database, DAY, DAY) == (CollectionStatus.OK, 1, 0)
    assert database.execute('SELECT aciklama, is_update, is_correction FROM disclosures').fetchone() == (
        'Yeni metin.', field == 'Güncelleme', field == 'Düzeltme',
    )


def test_bad_date_does_not_discard_other_rows_on_same_page(monkeypatch, database):
    page = [news(1), {**news(2), 'date': 'invalid'}, news(3)]
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[{'id': 'query', 'messageCount': 3}, page]))
    assert collector.fetch_disclosures(database, DAY, DAY) == (CollectionStatus.PARTIAL, 2, 0)
    assert database.execute('SELECT news_id FROM disclosures ORDER BY news_id').fetchall() == [('1',), ('3',)]


@pytest.mark.parametrize(
    ('responses', 'expected'),
    [
        ([[], {'id': 'query', 'messageCount': 0}], CollectionStatus.OK),
        ([RuntimeError('mock new_business HTTP error')], CollectionStatus.FAILED),
        ([[], RuntimeError('mock search HTTP error')], CollectionStatus.FAILED),
    ],
)
def test_collector_exit_status_for_zero_and_api_error(monkeypatch, database, responses, expected):
    monkeypatch.setattr(collector.duckdb, 'connect', lambda _: database.cursor())
    monkeypatch.setattr(collector, 'claim', Mock())
    monkeypatch.setattr(sys, 'argv', ['collector', '--start', DAY.isoformat(), '--end', DAY.isoformat()])
    monkeypatch.setattr(collector, 'get', Mock(side_effect=responses))
    assert collector.main() == expected
    collector.claim.assert_called_once_with('collector')


@pytest.mark.parametrize('mixed', [False, True])
def test_new_business_invalid_rows_cannot_report_ok(monkeypatch, database, mixed):
    first, last = 'https://example.invalid/one', 'https://example.invalid/two'
    rows = [
        {},
        business('not a URL'),
        business('https://example.invalid/bad', amount='invalid'),
        business('https://example.invalid/invalid path'),
        business('https://placeholder@example.invalid/invalid'),
        business('https://example.invalid:invalid/invalid'),
    ]
    if mixed:
        rows = [business(first), *rows, business(last)]
    monkeypatch.setattr(collector.duckdb, 'connect', lambda _: database.cursor())
    monkeypatch.setattr(collector, 'claim', Mock())
    monkeypatch.setattr(sys, 'argv', ['collector', '--start', DAY.isoformat(), '--end', DAY.isoformat()])
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[rows, {'id': 'query', 'messageCount': 0}]))
    assert collector.main() == (CollectionStatus.PARTIAL if mixed else CollectionStatus.FAILED)
    assert database.execute('SELECT url FROM new_business ORDER BY url').fetchall() == (
        [(first,), (last,)] if mixed else []
    )


@pytest.mark.parametrize('variant', ['url_only', 'missing_field', 'explicit_null', 'blank_currency', 'correction'])
def test_new_business_same_url_preserves_existing_values(monkeypatch, database, variant):
    url = 'https://example.invalid/synthetic'
    original = business(url, rt=0)
    incoming = business(url, amount=0, rt=0, desc='corrected')
    if variant == 'url_only':
        incoming = {'url': url}
    elif variant == 'missing_field':
        incoming.pop('rt')
    elif variant == 'explicit_null':
        incoming['amount'] = None
    elif variant == 'blank_currency':
        incoming['cur'] = ' '
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[[original], [incoming]]))
    assert collector.fetch_new_business(database, DAY, DAY) == (1, 0)
    valid = variant == 'correction'
    assert collector.fetch_new_business(database, DAY, DAY) == ((1, 0) if valid else (0, 1))
    assert database.execute('SELECT amount,cur,rt,description,per FROM new_business').fetchone() == (
        (0, 'TRY', 0, 'corrected', None) if valid else (50, 'TRY', 0, 'synthetic', None)
    )


@pytest.mark.parametrize('value', [float('nan'), float('inf'), '-Infinity', '1e999'])
def test_nonfinite_financial_value_cannot_overwrite_same_url(monkeypatch, database, value):
    url = 'https://example.invalid/synthetic'
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[[business(url, rt=0)], [business(url, rt=value)]]))
    assert collector.fetch_new_business(database, DAY, DAY) == (1, 0)
    assert collector.fetch_new_business(database, DAY, DAY) == (0, 1)
    assert database.execute('SELECT rt FROM new_business WHERE url = ?', (url,)).fetchone() == (0,)


def test_collector_preserves_url_query_and_rejects_noncanonical_news_id(monkeypatch, database):
    assert collector.norm_url('http://example.invalid/path/?next=http://example.invalid/') == (
        'https://example.invalid/path?next=http://example.invalid/'
    )
    page = [news(1), news(' 1 '), news('2\x00')]
    monkeypatch.setattr(collector, 'get', Mock(side_effect=[{'id': 'query', 'messageCount': 3}, page]))
    assert collector.fetch_disclosures(database, DAY, DAY) == (CollectionStatus.PARTIAL, 1, 0)
    assert database.execute('SELECT news_id FROM disclosures').fetchall() == [('1',)]


def test_collector_partial_preserves_guard_and_blocks_second_pull(monkeypatch, database, tmp_path):
    marker = tmp_path / 'last_pull.txt'
    claim = collector.claim
    connect = Mock(side_effect=lambda _: database.cursor())
    monkeypatch.setattr(collector.duckdb, 'connect', connect)
    monkeypatch.setattr(collector, 'claim', lambda kind: claim(kind, path=marker, log=tmp_path / 'pull_log.txt'))
    monkeypatch.setattr(sys, 'argv', ['collector', '--start', DAY.isoformat(), '--end', DAY.isoformat()])

    def get(path, params, **kwargs):
        assert marker.is_file()
        if path == 'v1/new-business-api':
            return [business('https://example.invalid/synthetic')]
        return {'id': 'query'}

    vendor = Mock(side_effect=get)
    monkeypatch.setattr(collector, 'get', vendor)
    assert collector.main() == CollectionStatus.PARTIAL
    assert database.execute('SELECT count(*) FROM new_business').fetchone() == (1,)
    assert collector.main() == CollectionStatus.FAILED
    assert vendor.call_count == 2 and connect.call_count == 2


def test_db_lock_happens_before_claim(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['collector', '--start', DAY.isoformat(), '--end', DAY.isoformat()])
    monkeypatch.setattr(collector.duckdb, 'connect', Mock(side_effect=duckdb.IOException('Could not set lock')))
    claim = Mock()
    monkeypatch.setattr(collector, 'claim', claim)
    assert collector.main() == collector.PRE_PULL_LOCK
    claim.assert_not_called()
