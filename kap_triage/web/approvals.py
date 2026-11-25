"""Local queue for the desk-mail interrupt. One immutable decision per day and desk."""

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from html import escape

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from langsmith import tracing_context

from kap_triage.settings import settings
from kap_triage.web.mail_mcp import build_mail_graph

# Failed attempts are audit entries. Only an approval or rejection closes a request.
PENDING = (
    "SELECT day, desk FROM requests EXCEPT SELECT day, desk FROM decisions WHERE decision IN ('approved','rejected')"
)


def init_queue(db):
    if db.execute('PRAGMA user_version').fetchone()[0]:
        return
    with db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('PRAGMA user_version').fetchone()[0]:
            return
        db.execute('CREATE TABLE IF NOT EXISTS requests (day TEXT, desk TEXT, PRIMARY KEY(day, desk))')
        # The original decisions table had a primary key on (day, desk), including every attempt.
        db.execute('CREATE TABLE audit (time TEXT, day TEXT, desk TEXT, decision TEXT, reason TEXT)')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='decisions'").fetchone():
            db.execute('INSERT INTO audit SELECT time, day, desk, decision, reason FROM decisions')
            db.execute('DROP TABLE decisions')
        db.execute('ALTER TABLE audit RENAME TO decisions')
        db.execute(
            "CREATE UNIQUE INDEX final_decision ON decisions(day, desk) WHERE decision IN ('approved','rejected')"
        )
        db.execute('PRAGMA user_version=1')


@contextmanager
def queue():
    with closing(sqlite3.connect(settings.path('mail_queue.sqlite'))) as db:
        init_queue(db)
        with db:
            yield db


def config(day, desk):
    return {'configurable': {'thread_id': f'{day}:{desk.casefold()}'}}


def enqueue(day, desk):
    with queue() as db, SqliteSaver.from_conn_string(settings.path('mail_checkpoints.sqlite')) as saver:
        db.execute('BEGIN IMMEDIATE')
        graph = build_mail_graph(saver)
        cfg = config(day, desk)
        state = graph.get_state(cfg)
        name = state.values.get('desk', desk)
        if db.execute('SELECT 1 FROM requests WHERE day=? AND desk=?', (day, name)).fetchone():
            return 'Bu e-posta daha önce sıraya alındı.'
        # A CLI crash may have persisted the interrupt just before the queue transaction committed.
        if not state.interrupts:
            with tracing_context(enabled=False):
                out = graph.invoke({'day': day, 'desk': desk}, cfg)
            if not out.get('__interrupt__'):
                raise SystemExit(out['result'])
            name = out['desk']
        db.execute('INSERT INTO requests VALUES (?, ?)', (day, name))
    return 'Karar için /onay sayfasını açın.'


def render():
    cards = []
    with queue() as db, SqliteSaver.from_conn_string(settings.path('mail_checkpoints.sqlite')) as saver:
        graph = build_mail_graph(saver)
        rows = db.execute(PENDING + ' ORDER BY day DESC')
        for day, desk in rows:
            state = graph.get_state(config(day, desk)).values
            cards.append(
                f'<section><h2>{escape(state["subject"])}</h2><p>{escape(day)} · {escape(state["desk"])} · '
                f'{escape(state["to"])}</p><pre>{escape(state["body"])}</pre>'
                '<form method="post" action="/onay">'
                f'<input type="hidden" name="day" value="{escape(day)}">'
                f'<input type="hidden" name="desk" value="{escape(desk)}">'
                '<button name="decision" value="approved" formnovalidate>Onayla</button> '
                '<label>Ret gerekçesi <input name="reason" required></label> '
                '<button name="decision" value="rejected">Gerekçeli Reddet</button></form></section>'
            )
    return '<h1>Masa e-posta onayları</h1>' + (''.join(cards) or '<p>Bekleyen e-posta yok.</p>')


def decide(day, desk, decision, reason, send_fn=None):
    reason = reason.strip() if decision == 'rejected' else ''
    if decision not in ('approved', 'rejected') or (decision == 'rejected' and not reason):
        return 400
    with queue() as db:
        # Serialize the pending check, send and audit across panel processes.
        try:
            db.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                return 503
            raise
        if not db.execute(f'SELECT 1 FROM ({PENDING}) WHERE day=? AND desk=?', (day, desk)).fetchone():
            return 409
        with (
            SqliteSaver.from_conn_string(settings.path('mail_checkpoints.sqlite')) as saver,
            tracing_context(enabled=False),
        ):
            graph = build_mail_graph(saver, send_fn)
            cfg = config(day, desk)
            state = graph.get_state(cfg)
            # A completed checkpoint can survive a crash just before this audit transaction commits.
            if state.interrupts:
                final = graph.invoke(Command(resume=decision == 'approved'), cfg)
            elif state.next:
                return 503
            else:
                final = state.values
        result = final.get('result')
        if result == 'send_failed':
            outcome, reason = result, final['error_type']
        elif result == 'sent=True':
            outcome, reason = 'approved', ''
        elif result == 'declined':
            if decision != 'rejected':
                return 409
            outcome = 'rejected'
        else:
            return 503  # No durable outcome or fresh approval interrupt. Do not replay a send.
        db.execute(
            'INSERT INTO decisions VALUES (?, ?, ?, ?, ?)',
            (datetime.now(timezone.utc).isoformat(), day, desk, outcome, reason),
        )
    if outcome == 'send_failed':
        return 502
    return 303 if outcome == decision else 409
