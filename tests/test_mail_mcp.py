"""kap_triage/analysis/desks.py, kap_triage/web/mail_mcp.py: the checks of the v1 self-test in mail_mcp.py, on made-up data (no network, no real data)."""

import re

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from kap_triage.web.mail_mcp import BAD_CASES, SERVER_ENV, decide, norm_text, server_env, synthetic_message


def test_mail_mcp():
    env = server_env()
    assert (
        set(env) == set(SERVER_ENV) | {'PATH'}
        and env['SMTP_ALLOWED_RECIPIENTS'] == '@masa.local'
        and env['ELICITATION'] == 'true'
    )
    assert 'KAP_TOKEN' not in env and env['SMTP_HOST'] == '127.0.0.1'
    assert norm_text('a  \r\nb\n\n') == 'a\nb'
    m = synthetic_message('t')
    assert (
        m['to'] == ['savunma@masa.local']
        and m['subject'].startswith('[t] ')
        and 'KAP: https://www.kap.org.tr' in m['body']
    )
    from kap_triage.analysis.desks import leaks

    assert not leaks(m['subject'] + m['body'])
    outside = lambda c: [
        x for k in ('to', 'cc', 'bcc') for x in c.get(k, []) if not re.fullmatch(r'[^@\s]+@masa\.local', x)
    ]
    assert len(BAD_CASES) == 7 and all(
        outside(c) for _, c in BAD_CASES
    )  # every A case has an address outside the allowlist
    assert decide({'a': True}, 1.0) == 'ADOPT_SMTP_MCP' and decide({'a': True, 'b': False}, 1.0) == 'SMTP_MCP_OFF'
    assert decide({'a': True}, 6.0) == 'SMTP_MCP_OFF' and decide({'a': True}, None) == 'SMTP_MCP_OFF'


def test_smtp_server_path_is_in_the_repository():
    # the pinned smtp-mcp server lives in mcp/smtp/ at the repository root, two levels above web/
    import kap_triage.web.mail_mcp as mail_mcp

    assert (mail_mcp.ROOT / 'main.py').exists() and (mail_mcp.ROOT / 'mcp' / 'smtp' / 'package.json').exists()
    assert mail_mcp.SERVER_JS.is_relative_to(mail_mcp.ROOT / 'mcp' / 'smtp')


def _clean_state():
    m = synthetic_message('t')
    return {'day': '2026-11-12', 'desk': 'Savunma', 'to': m['to'][0], 'subject': m['subject'], 'body': m['body']}


@pytest.fixture
def saver():
    with SqliteSaver.from_conn_string(':memory:') as checkpoint:
        yield checkpoint


def test_mail_graph_no_send_before_interrupt(saver):
    # running up to interrupt() must pause with the preview and never call send_fn
    from kap_triage.web.mail_mcp import build_mail_graph

    calls = []
    g = build_mail_graph(saver, send_fn=lambda args: calls.append(args) or 'sent=True')
    s = _clean_state()
    out = g.invoke(s, {'configurable': {'thread_id': '2026-11-12:Savunma'}})
    assert out.get('__interrupt__') and out['__interrupt__'][0].value == {
        'to': s['to'],
        'subject': s['subject'],
        'body': s['body'],
    }
    assert calls == []


def test_mail_graph_decline_does_not_send(saver):
    # resuming with False must skip send_fn and record result='declined'
    from langgraph.types import Command
    from kap_triage.web.mail_mcp import build_mail_graph

    calls = []
    g = build_mail_graph(saver, send_fn=lambda args: calls.append(args) or 'sent=True')
    cfg = {'configurable': {'thread_id': '2026-11-12:Savunma'}}
    g.invoke(_clean_state(), cfg)
    final = g.invoke(Command(resume=False), cfg)
    assert calls == [] and final['result'] == 'declined'


def test_mail_graph_approve_sends_once_with_exact_payload(saver):
    # resuming with True must call send_fn exactly once with the prepared to/subject/body
    from langgraph.types import Command
    from kap_triage.web.mail_mcp import build_mail_graph

    calls = []
    g = build_mail_graph(saver, send_fn=lambda args: calls.append(args) or 'sent=True')
    s = _clean_state()
    cfg = {'configurable': {'thread_id': '2026-11-12:Savunma'}}
    g.invoke(s, cfg)
    final = g.invoke(Command(resume=True), cfg)
    assert calls == [{'to': [s['to']], 'subject': s['subject'], 'body': s['body']}]
    assert final['result'] == 'sent=True'


def test_mail_graph_stops_before_interrupt_on_amount_leak(saver):
    # a message body containing an amount (leaks) must stop in prepare without interrupting or sending
    from kap_triage.web.mail_mcp import build_mail_graph

    calls = []
    g = build_mail_graph(saver, send_fn=lambda args: calls.append(args) or 'sent=True')
    s = {**_clean_state(), 'body': 'Sözleşme bedeli 500.000 TL olarak açıklanmıştır.'}
    out = g.invoke(s, {'configurable': {'thread_id': '2026-11-12:Savunma'}})
    assert not out.get('__interrupt__') and 'amount' in (out.get('result') or '')
    assert calls == []


def test_mail_graph_second_resume_does_not_send_twice(saver):
    # resuming the same thread_id a second time must not trigger a second send
    from langgraph.types import Command
    from kap_triage.web.mail_mcp import build_mail_graph

    calls = []
    g = build_mail_graph(saver, send_fn=lambda args: calls.append(args) or 'sent=True')
    cfg = {'configurable': {'thread_id': '2026-11-12:Savunma'}}
    g.invoke(_clean_state(), cfg)
    g.invoke(Command(resume=True), cfg)
    g.invoke(Command(resume=True), cfg)
    assert len(calls) == 1
