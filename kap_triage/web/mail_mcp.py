"""Desk e-mail through a third-party MCP server, with human approval (rule: docs/smtp_mcp_rule.md).

Server: @ni-c/smtp-mcp 0.2.0, pinned in mcp/smtp (npm ci --ignore-scripts), stdio, our environment only.
Message: desk_mail.payload (no amounts, no disclosure text). Recipients limited to @masa.local by the server.

Usage:
  python -m kap_triage.web.mail_mcp --send --day 2026-11-12                  # lists the desks of that day
  python -m kap_triage.web.mail_mcp --send --day 2026-11-12 --desk Savunma  # shows the approval text, asks e/h
  python -m kap_triage.web.mail_mcp --check                                 # measurement A-G (synthetic message, Mailpit API)
"""

import argparse
import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repository root (kap_triage/web/ -> two levels up)
SERVER_JS = ROOT / 'mcp/smtp/node_modules/@ni-c/smtp-mcp/dist/index.js'
MAILPIT = 'http://127.0.0.1:8025'
SENDER = 'asistan@masa.local'
SERVER_ENV = {
    'SMTP_HOST': '127.0.0.1',
    'SMTP_PORT': '1025',
    'SMTP_TLS': 'none',
    'SMTP_USER': 'kap',
    'SMTP_PASSWORD': 'local',
    'SMTP_FROM': SENDER,
    'SMTP_ALLOW_SEND': 'true',
    'SMTP_ALLOWED_RECIPIENTS': '@masa.local',
    'SMTP_ALLOW_TOOLS': 'essential',
    'ELICITATION': 'true',
}
BAR_SECONDS = 5.0
BAD_CASES = [
    ('A1 dış alan adı', {'to': ['x@gmail.com']}),
    ('A2 masa.local.evil.com', {'to': ['savunma@masa.local.evil.com']}),
    ('A3 masalocal.com', {'to': ['savunma@masalocal.com']}),
    ('A4 Cc dışarı', {'to': ['savunma@masa.local'], 'cc': ['x@gmail.com']}),
    ('A5 Bcc dışarı', {'to': ['savunma@masa.local'], 'bcc': ['x@gmail.com']}),
    # Amendment 1 (nodemailer advisories GHSA-85x2-q946-cp5h, GHSA-m943-m63m-w62w)
    ('A6 tırnaklı yerel kısım ">"', {'to': ['"savunma@masa.local>"@gmail.com']}),
    ('A7 ";" grubu', {'to': ['savunma@masa.local; x@gmail.com']}),
]


def server_env():
    """Only PATH from the user's environment (node), plus the fixed server settings."""
    return {'PATH': os.environ.get('PATH', ''), **SERVER_ENV}


def norm_text(s):
    return '\n'.join(line.rstrip() for line in (s or '').replace('\r\n', '\n').split('\n')).strip()


def result_text(res):
    return ' '.join(getattr(c, 'text', '') for c in (res.content or []))


def sent_ok(res):
    sc = res.structuredContent or {}
    return not res.isError and sc.get('sent') is True and not sc.get('already_sent')


async def call(args, answer=None, tool='send_mail'):
    """One stdio session. answer: None = client without elicitation; else callback(message) -> bool."""
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client

    if not SERVER_JS.exists():
        raise SystemExit('smtp-mcp missing: cd mcp/smtp && npm ci --ignore-scripts')

    async def elicit(ctx, params):
        ok = answer(params.message)
        return (
            types.ElicitResult(action='accept', content={'confirm': True})
            if ok
            else types.ElicitResult(action='decline')
        )

    params = StdioServerParameters(command='node', args=[str(SERVER_JS)], env=server_env())
    with open(os.devnull, 'w') as devnull:  # server audit lines stay out of the output
        async with stdio_client(params, errlog=devnull) as (r, w):
            async with ClientSession(r, w, elicitation_callback=elicit if answer else None) as s:
                await s.initialize()
                return await s.call_tool(tool, args)


async def call_twice(args, answer):
    """Same session, same request twice (replay check D)."""
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client

    async def elicit(ctx, params):
        return (
            types.ElicitResult(action='accept', content={'confirm': True})
            if answer(params.message)
            else types.ElicitResult(action='decline')
        )

    params = StdioServerParameters(command='node', args=[str(SERVER_JS)], env=server_env())
    with open(os.devnull, 'w') as devnull:
        async with stdio_client(params, errlog=devnull) as (r, w):
            async with ClientSession(r, w, elicitation_callback=elicit) as s:
                await s.initialize()
                t = time.time()
                first = await s.call_tool('send_mail', args)
                secs = time.time() - t
                second = await s.call_tool('send_mail', args)
                return first, second, secs


def mailpit_search(tag):
    q = urllib.parse.quote(f'subject:"{tag}"')
    with urllib.request.urlopen(f'{MAILPIT}/api/v1/search?query={q}&limit=50', timeout=10) as r:
        return json.load(r).get('messages') or []


def mailpit_text(msg_id):
    with urllib.request.urlopen(f'{MAILPIT}/api/v1/message/{msg_id}', timeout=10) as r:
        return json.load(r).get('Text') or ''


def count_after(tag, wait=2.0):
    """Messages with the tag, after giving Mailpit a moment to index."""
    time.sleep(wait)
    return mailpit_search(tag)


def synthetic_message(tag):
    """A desk e-mail from desk_mail.payload on made-up items (no data/ read)."""
    from kap_triage.analysis.desks import payload

    item = lambda nid, sym, level, flag: {
        'news_id': nid,
        'symbol': sym,
        'kap_url': f'https://www.kap.org.tr/tr/Bildirim/{nid}',
        'importance': {
            'level': level,
            'score': 5,
            'needs_review': flag,
            'needs_review_reasons': ['currency_unclear'] if flag else [],
            'reasons': [{'code': 'long_contract'}],
            'amount_try': 1.0,
        },
    }
    p = payload(
        '2026-11-12', [item('1', 'AAA', 'high', False), item('2', 'AAA', 'medium', True)], {'AAA': 'Savunma'}, {}
    )
    d = p['desks'][0]
    return {'to': [d['to']], 'subject': f'[{tag}] {d["subject"]}', 'body': d['text']}


def decide(checks, secs):
    ok = all(checks.values()) and secs is not None and secs <= BAR_SECONDS
    return 'ADOPT_SMTP_MCP' if ok else 'SMTP_MCP_OFF'


def cmd_check():
    from kap_triage.analysis.desks import leaks

    tag = f'smtp-mcp-check {time.strftime("%Y%m%d-%H%M%S")}'
    try:
        mailpit_search(tag)
    except Exception as e:
        raise SystemExit(f'Mailpit API not reachable on {MAILPIT} ({type(e).__name__}); docker compose up -d')
    msg = synthetic_message(tag)
    checks = {}
    for name, rcpt in BAD_CASES:
        res = asyncio.run(call({**msg, **rcpt}, answer=lambda m: True))
        n = len(count_after(tag, 0.5))
        checks[name] = res.isError and not sent_ok(res) and n == 0
        print(f'{name}: refused={res.isError} messages={n} -> {"PASS" if checks[name] else "FAIL"}')
    res = asyncio.run(call(msg, answer=lambda m: False))
    n = len(count_after(tag))
    checks['B reddedilen onay'] = not sent_ok(res) and n == 0
    print(f'B declined: sent={sent_ok(res)} messages={n} -> {"PASS" if checks["B reddedilen onay"] else "FAIL"}')
    first, second, secs = asyncio.run(call_twice(msg, answer=lambda m: True))
    found = count_after(tag)
    good = False
    if len(found) == 1:
        m = found[0]
        to = [a.get('Address') for a in m.get('To') or []]
        good = (
            to == msg['to']
            and (m.get('From') or {}).get('Address') == SENDER
            and m.get('Subject') == msg['subject']
            and norm_text(mailpit_text(m['ID'])) == norm_text(msg['body'])
        )
    checks['C onaylanan gönderim'] = sent_ok(first) and good
    print(
        f'C accepted: sent={sent_ok(first)} messages={len(found)} fields_and_text_equal={good} seconds={secs:.2f} -> '
        f'{"PASS" if checks["C onaylanan gönderim"] else "FAIL"}'
    )
    checks['D tekrar'] = not sent_ok(second) and len(found) == 1
    print(
        f'D replay: sent_again={sent_ok(second)} already_sent={(second.structuredContent or {}).get("already_sent")} '
        f'messages={len(found)} -> {"PASS" if checks["D tekrar"] else "FAIL"}'
    )
    res = asyncio.run(call({**msg, 'confirm_token': 'uydurma-token-0000000000'}, answer=None))
    n = len(count_after(tag))
    checks['E uydurma token'] = res.isError and not sent_ok(res) and n == 1
    print(
        f'E invented token: rejected={res.isError} messages={n} (1 = only C) -> {"PASS" if checks["E uydurma token"] else "FAIL"}'
    )
    checks['F sızıntı yok'] = not leaks(msg['subject'] + msg['body'])
    print(f'F no leak: {"PASS" if checks["F sızıntı yok"] else "FAIL"}')
    print(f'G latency C: {secs:.2f} s (bar <= {BAR_SECONDS:.0f}) -> {"PASS" if secs <= BAR_SECONDS else "FAIL"}')
    print(f'run tag: {tag}')
    print(f'decision: {decide(checks, secs)}')


def terminal_answer(message):
    print('\n' + '=' * 80 + '\nsmtp-mcp onay isteği (sunucunun metni):\n' + '-' * 80)
    print(message)
    print('=' * 80)
    while True:
        a = input('Bu e-postayı gönder? [e/h]: ').strip().lower()
        if a in ('e', 'h'):
            return a == 'e'


def build_mail_graph(send_fn=None):
    """LangGraph approval flow: prepare -> approve (interrupt) -> send. No side effects before approval."""
    from typing import Optional, TypedDict

    os.environ.setdefault('LANGSMITH_TRACING', 'false')
    os.environ.setdefault('LANGCHAIN_TRACING_V2', 'false')
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt
    from kap_triage.analysis.desks import leaks, payload
    from kap_triage.web.panel import DESKS, load_day, load_sectors

    class MailState(TypedDict, total=False):
        day: str
        desk: str
        to: str
        subject: str
        body: str
        approved: Optional[bool]
        result: Optional[str]

    def prepare(s):
        to, subject, body = s.get('to'), s.get('subject'), s.get('body')
        if not (to and subject and body):
            day, desk = s.get('day', ''), s.get('desk', '')
            items = load_day(day)
            if items is None:
                return {'result': f'no morning list for {day}'}
            desks = payload(day, items, load_sectors(), DESKS)['desks']
            d = next((x for x in desks if x['desk'].lower() == desk.lower()), None)
            if d is None:
                return {'result': f'no desk "{desk}" on {day}; run without --desk to list them'}
            to, subject, body = d['to'], d['subject'], d['text']
        if leaks(subject + body):
            return {'to': to, 'subject': subject, 'body': body, 'result': 'message text contains an amount; not sent'}
        return {'to': to, 'subject': subject, 'body': body, 'result': None}

    def after_prepare(s):
        return END if s.get('result') else 'approve'

    def approve(s):
        decision = interrupt({'to': s['to'], 'subject': s['subject'], 'body': s['body']})
        return {'approved': bool(decision)}

    def send(s):
        if s.get('result'):
            return {}
        if not s.get('approved'):
            return {'result': 'declined'}
        args = {'to': [s['to']], 'subject': s['subject'], 'body': s['body']}
        if send_fn is not None:
            res = send_fn(args)
            return {
                'result': res
                if isinstance(res, str)
                else ('sent=True' if sent_ok(res) else f'sent=False ({result_text(res)[:160]})')
            }
        res = asyncio.run(call(args, answer=lambda m: True))
        return {'result': 'sent=True' if sent_ok(res) else f'sent=False ({result_text(res)[:160]})'}

    g = StateGraph(MailState)
    g.add_node('prepare', prepare)
    g.add_node('approve', approve)
    g.add_node('send', send)
    g.add_edge(START, 'prepare')
    g.add_conditional_edges('prepare', after_prepare, {'approve': 'approve', END: END})
    g.add_edge('approve', 'send')
    g.add_edge('send', END)
    return g.compile(checkpointer=MemorySaver())


def cmd_send(day, desk):
    from langgraph.types import Command
    from kap_triage.analysis.desks import payload
    from kap_triage.web.panel import DESKS, load_day, load_sectors

    if not desk:
        items = load_day(day)
        if items is None:
            raise SystemExit(f'no morning list for {day}')
        desks = payload(day, items, load_sectors(), DESKS)['desks']
        print('masalar: ' + ', '.join(f'{d["desk"]} ({d["to"]})' for d in desks))
        return
    graph = build_mail_graph()
    cfg = {'configurable': {'thread_id': f'{day}:{desk}'}}
    out = graph.invoke({'day': day, 'desk': desk}, cfg)
    paused = out.get('__interrupt__')
    if not paused:
        raise SystemExit(out.get('result') or 'not sent')
    info = paused[0].value
    preview = f'To: {info["to"]}\nSubject: {info["subject"]}\n\n{info["body"]}'
    decision = terminal_answer(preview)
    final = graph.invoke(Command(resume=decision), cfg)
    res = final.get('result') or ''
    print('sent=False (declined)' if res == 'declined' else res)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--send', action='store_true')
    g.add_argument('--check', action='store_true')
    ap.add_argument('--day')
    ap.add_argument('--desk')
    args = ap.parse_args()
    if args.check:
        cmd_check()
    else:
        if not args.day:
            ap.error('--send needs --day')
        cmd_send(args.day, args.desk)


if __name__ == '__main__':
    main()
