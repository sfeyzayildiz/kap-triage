"""Nightly job (kap_triage/collect/nightly.py) with fake collectors, runners and alerts: no network, no Matriks."""

import plistlib
import socket
import subprocess
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from kap_triage.collect import nightly
from kap_triage.collect.nightly import API_HOSTS, last_error_line, skip_message, wait_for_network
from kap_triage.collect.nightly import list_day, message, run_morning as run, summary


def test_launchd_template_paths():
    template = Path(__file__).resolve().parents[1] / 'deploy' / 'com.feyza.kap-daily.plist'
    plist = plistlib.loads(template.read_bytes())
    projects = '/Users/YOUR_USERNAME/projects'
    deploy = f'{projects}/kap-deploy'
    log = f'{projects}/kap-explore/data/daily.log'
    assert plist['ProgramArguments'] == [f'{deploy}/.venv/bin/python', 'main.py', 'nightly']
    assert plist['WorkingDirectory'] == deploy
    assert plist['StandardOutPath'] == plist['StandardErrorPath'] == log


# --- Collection -----------------------------------------------------------------


def test_collector_failure_keeps_exception_local(monkeypatch):
    error = RuntimeError('HTTP 401: synthetic vendor response with a test token')
    monkeypatch.setattr(nightly, 'collect_and_list', Mock(side_effect=error))
    monkeypatch.setattr(nightly, 'NTFY_URL', 'https://push.invalid/test')
    post = Mock()
    monkeypatch.setattr(nightly.requests, 'post', post)

    with pytest.raises(RuntimeError) as caught:
        nightly.main()

    assert caught.value is error
    post.assert_called_once_with(
        'https://push.invalid/test',
        data=b'See data/daily.log.',
        headers={'Title': 'KAP collector FAILED', 'Priority': 'high'},
        timeout=10,
    )


def test_daily_collect():
    calls = []

    def flaky(host, port):
        calls.append(host)
        if len(calls) < 3:
            raise socket.gaierror('down')

    assert wait_for_network(flaky, sleep=lambda s: None) == 3 and calls == [API_HOSTS[0]] * 3 + [API_HOSTS[1]]

    def down(host, port):
        raise socket.gaierror('down')

    try:
        wait_for_network(down, sleep=lambda s: None)
        raise AssertionError('must raise')
    except RuntimeError:
        pass
    tb = 'Traceback (most recent call last):\n  File "x.py", line 1\n    f()\n    ^^^\nrequests.exceptions.ReadTimeout: read timed out\n          ^^^^^^^^\n'
    assert last_error_line(tb) == 'requests.exceptions.ReadTimeout: read timed out'
    assert last_error_line('HTTP 401 on v2/news/search: bad token\n') == 'HTTP 401 on v2/news/search: bad token'
    assert last_error_line('') == 'no stderr' and last_error_line('  ^^^^\n') == 'no stderr'
    assert skip_message('prices', date(2026, 11, 11)).startswith('2026-11-11: already pulled today (prices)')


# --- Morning list ---------------------------------------------------------------


def test_morning_subprocess_failure_keeps_stderr_local(capsys):
    stderr = 'HTTP 403: synthetic private response body\n'
    runner = Mock(return_value=subprocess.CompletedProcess([], 1, stdout='', stderr=stderr))
    notify = Mock()

    assert run('2026-11-09', notify, runner=runner) is False

    notify.assert_called_once_with('KAP morning FAILED', '2026-11-09: See data/daily.log.', 'high')
    assert stderr in capsys.readouterr().err


def test_morning_job():
    assert list_day(datetime(2026, 11, 9, 23, 45)) == '2026-11-09'
    assert list_day(datetime(2026, 11, 10, 0, 20)) == '2026-11-09'
    assert list_day(datetime(2026, 11, 10, 13, 0)) == '2026-11-10'
    out = 'doc vectors...\ndisclosures=3 look_first=1 flagged=1 run_errors=0 -> data/morning_2026-11-09.md\n'
    s = summary(out)
    assert s == {'disclosures': 3, 'look_first': 1, 'flagged': 1, 'run_errors': 0} and summary('nothing') is None
    assert message('2026-11-09', s) == '2026-11-09: 3 bildirim, önce bak 1, kontrol et 1'
    assert message('2026-11-08', {**s, 'disclosures': 0}) == '2026-11-08: yeni bildirim yok'
    assert 'LLM hatası 2' in message('d', {**s, 'run_errors': 2})

    class R:
        def __init__(self, code, out='', err=''):
            self.returncode, self.stdout, self.stderr = code, out, err

    sent = []
    note = lambda t, m, p='default': sent.append((t, m, p))
    assert run('2026-11-09', note, runner=lambda *a, **k: R(0, out)) and sent[-1] == (
        'KAP morning list',
        '2026-11-09: 3 bildirim, önce bak 1, kontrol et 1',
        'default',
    )
    assert not run('d', note, runner=lambda *a, **k: R(0, 'no line')) and sent[-1][1] == 'd: no summary line'

    def boom(*a, **k):
        raise subprocess.TimeoutExpired('x', 1)

    assert not run('d', note, runner=boom) and sent[-1] == ('KAP morning FAILED', 'd: See data/daily.log.', 'high')
    assert (
        run('d', note, runner=lambda *a, **k: R(0, out.replace('run_errors=0', 'run_errors=2')))
        and sent[-1][2] == 'high'
    )
    assert run('2026-11-16', note, runner=lambda *a, **k: R(0, out), sealer=lambda d: ' | mühür abcd') and sent[-1][
        1
    ].endswith(' | mühür abcd')
