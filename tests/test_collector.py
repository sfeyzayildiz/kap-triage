"""kap_triage/collect/collector.py without network: importing it needs no token, a missing token
is a clear error at request time, and the KAP form table becomes a dict."""

import os
import subprocess
import sys

import pytest

import kap_triage.collect.collector as collector


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
