import os
import subprocess
import sys
from datetime import datetime
from unittest.mock import Mock, call

import pytest
from fastapi.testclient import TestClient

from kap_triage.settings import settings
from kap_triage.web import approvals, panel
from kap_triage.web.app import app

DAY = '2026-11-12'
DESK = 'Enerji'
client = TestClient(app, base_url='http://127.0.0.1')


@pytest.fixture
def send_fn():
    return Mock(return_value='sent=True')


@pytest.fixture
def pending(tmp_path, monkeypatch, send_fn):
    from kap_triage.analysis import desks

    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    monkeypatch.setattr(panel, 'load_day', lambda day: [])
    monkeypatch.setattr(panel, 'load_sectors', dict)
    mail = {'desk': DESK, 'subject': '<konu>', 'to': 'enerji@masa.local', 'text': '<gövde>'}
    monkeypatch.setattr(desks, 'payload', lambda *args: {'desks': [mail]})
    decide = approvals.decide
    monkeypatch.setattr(approvals, 'decide', lambda *args: decide(*args, send_fn=send_fn))
    approvals.enqueue(DAY, DESK)
    return send_fn.call_args_list


def post(decision, reason='', **kwargs):
    return client.post(
        '/onay', data=dict(day=DAY, desk=DESK, decision=decision, reason=reason), follow_redirects=False, **kwargs
    )


def records():
    with approvals.queue() as db:
        return db.execute('SELECT * FROM decisions').fetchall()


# Approval sends the preview once and stores just the five audit fields.
def test_approve(pending):
    assert post('approved').status_code == 303
    assert pending == [call({'to': ['enerji@masa.local'], 'subject': '<konu>', 'body': '<gövde>'})]
    (row,) = records()
    assert datetime.fromisoformat(row[0]).tzinfo and row[1:] == (DAY, DESK, 'approved', '')


# A rejected request leaves the queue with its reason and never calls the sender.
def test_reject(pending):
    assert post('rejected', ' Yanlış masa ').status_code == 303
    assert records()[0][1:] == (DAY, DESK, 'rejected', 'Yanlış masa')
    assert 'Bekleyen e-posta yok' in client.get('/onay').text and not pending


# A whitespace-only reason leaves the decision open.
def test_reason_required(pending):
    assert post('rejected', '  ').status_code == 400
    assert not records() and not pending


# Requeueing and submitting a stale form cannot issue a second send.
def test_duplicate(pending):
    assert post('approved').status_code == 303
    approvals.enqueue(DAY, DESK.lower())
    assert post('approved').status_code == 409
    assert len(records()) == len(pending) == 1


# A fresh interpreter can display the saved, HTML-escaped interrupt and resume it.
def test_restart(pending, tmp_path):
    script = """from kap_triage.web.approvals import render, decide
assert '&lt;konu&gt;' in render() and '&lt;gövde&gt;' in render()
assert decide('2026-11-12', 'Enerji', 'approved', '', lambda msg: 'sent=True') == 303
"""
    subprocess.run([sys.executable, '-c', script], env={**os.environ, 'KAP_DATA_DIR': str(tmp_path)}, check=True)
    assert post('approved').status_code == 409 and not pending


# A foreign Origin and the compose service Host cannot make decisions.
def test_local_only(pending):
    assert post('approved', headers={'origin': 'https://example.org'}).status_code == 403
    assert post('approved', headers={'host': 'panel'}).status_code == 403
    assert not records() and not pending


# A failed attempt audits only its type and waits for another explicit approval before sending.
def test_retry_after_send_error(pending, send_fn):
    delivered = []

    def send(msg):
        if send_fn.call_count == 1:
            raise ConnectionError('private message content')
        delivered.append(msg)
        return 'sent=True'

    send_fn.side_effect = send
    assert post('approved').status_code == 502
    assert [r[3:] for r in records()] == [('send_failed', 'ConnectionError')]
    assert '&lt;konu&gt;' in client.get('/onay').text and not delivered
    assert post('approved').status_code == 303
    assert [r[3:] for r in records()] == [('send_failed', 'ConnectionError'), ('approved', '')]
    assert post('approved').status_code == 409 and len(delivered) == 1
    assert 'Bekleyen e-posta yok' in client.get('/onay').text


# A user can also reject a failed delivery without invoking the sender again.
def test_reject_after_send_error(pending, send_fn):
    send_fn.return_value = 'sent=False'
    assert post('approved').status_code == 502
    assert post('rejected', 'İptal').status_code == 303
    assert [r[3:] for r in records()] == [('send_failed', 'MailSendError'), ('rejected', 'İptal')]
    assert send_fn.call_count == 1
