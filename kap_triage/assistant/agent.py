"""Triage agent (LangGraph): route an analyst's question to one tool and answer from data.

Graph: route (LLM, structured output) -> validate (code) -> one tool (code) -> END.
(Detail questions get a card: the detail switch failed alone on 10 Nov, docs/detail_card_rule.md, and was adopted
with router v2 the same day, cards right 12/16, docs/router_v2_rule.md; DETAIL_SWITCH below.)
The LLM only reads the question: intent, symbol, date, topic. Every number and link in
the answer comes from the database through code, so the model cannot invent them.
Tracing to LangSmith is switched off; nothing leaves the machine.

Reading map (search for these names; the last part is tests only):
  1. switches and their measured results: CARD, DETAIL_SWITCH, BRIEF_SWITCH, V2, PERIODS
  2. routing: llm_route (the only LLM call here), validate and route_question (code checks), period_switch
  3. tools, one per intent: tool_morning, tool_company, tool_why_moved, tool_search, tool_detail (card_lines)
  4. company brief, multi-step: step_latest, step_history, step_reaction, step_similar, compose_brief
  5. the LangGraph graph: build_graph (route -> one tool, or the brief steps -> compose)
  6. tests are in tests/; main: command line

Usage:
  python -m kap_triage.assistant.agent "Bugün neye bakmalıyım?"
  python -m kap_triage.assistant.agent --quiet "ASELS son bir yılda hangi işleri aldı?"   # route and line count only
"""

import argparse
import json
import logging
import os
import re
import time
import warnings
from datetime import date, datetime, timedelta
from typing import Literal, Optional, TypedDict

import duckdb
from pydantic import BaseModel, ValidationError

from kap_triage.settings import settings

# no tracing, quiet model libraries: set before LangGraph is imported
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ.setdefault('TRANSFORMERS_VERBOSITY', 'error')
os.environ.setdefault('TORCH_CPP_LOG_LEVEL', 'ERROR')
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')
logging.getLogger('torch.distributed.elastic.multiprocessing.redirects').setLevel(logging.ERROR)
_show, warnings.showwarning = (
    warnings.showwarning,
    lambda *a, **k: None,
)  # LangChain forces a deprecation notice at import; not ours
from langgraph.graph import END, START, StateGraph  # noqa: E402

warnings.showwarning = _show

DB_PATH = settings.path('kap.duckdb')
INTENTS = ('morning', 'company', 'why_moved', 'search', 'unknown')
TICKER_RE = re.compile(r'\b[A-ZÇĞİÖŞÜ0-9]{3,6}\b')
# docs/detail_card_rule.md (fixed before any question): a question about one disclosure's detail
DETAIL_RE = re.compile(
    r'\b(kaç|kac|ne kadar|ne zaman|süres|sures|kim|karşı taraf|karsi taraf|tutar|bedel|teslim|'
    r'hangi (ülke|ulke|şirket|sirket|firma|müşteri|musteri|kurum|para birimi|döviz|doviz)|nerede|nereye|nereden)',
    re.I,
)
CARD = True  # docs/detail_card_rule.md: False shows the ticker-filtered search with links only
# docs/detail_card_rule.md result 2026-11-10: REMOVE_SWITCH (routed 5/10, right disclosure 3/10; 0/10 questions
# wrote a ticker). Router v2 (names decide the ticker) then measured the switch again and kept it on:
DETAIL_SWITCH = True  # docs/router_v2_rule.md: ADOPT_V2, card ON (C 12/16 >= 70%, 10 Nov)
BRIEF_RE = re.compile(
    r'\b(bak|bakalım|bakalim|özet|ozet|özetle|ozetle|değerlendir|degerlendir|genel durum|ne durumda|durumu|brief)\b',
    re.I,
)
BRIEF_SWITCH = True  # docs/brief_rule.md: on for the measurement; decided by Feyza's 10 questions
BRIEF_HISTORY_LINKS = 8
V2 = True  # docs/router_v2_rule.md: company names, two-company note, date filter in search, detail switch
PERIODS = True  # docs/relative_periods_rule.md: ADOPT_PERIODS 13 Nov (exact 10/10, false 1/5, wrong fires 0/9)
PERIOD_TOOLS = ('company', 'search', 'detail', 'morning')
PERIOD_LIST_MAX = 30
ROUTER_PROMPT = """You route a Turkish equity analyst's question to exactly one tool. Return JSON only.
intent:
- "morning": what to look at on a day, or a day's new business disclosures ("Bugün neye bakmalıyım?", "30 Ekim'deki bildirimler")
- "company": one company's recent new business disclosures ("ASELS son bir yılda hangi işleri aldı?")
- "why_moved": why a stock moved on a day ("THYAO dün neden düştü?", "KONTR 28 Ekim'de neden yükseldi?")
- "search": find disclosures about a topic, not one company's list ("Irak'taki projeler", "savunma ihracat sözleşmeleri")
- "unknown": anything else
symbol: the BIST ticker in capitals if the question writes one, else null. Do not guess a ticker from a company name.
date: YYYY-MM-DD if the question gives a day; "bugün" is {today}, "dün" is {yesterday}; else null.
query: for "search", the topic words in Turkish; else null.
Question: """


class Route(BaseModel):
    intent: Literal['morning', 'company', 'why_moved', 'search', 'unknown']
    symbol: Optional[str]
    date: Optional[str]
    query: Optional[str]


class State(TypedDict, total=False):
    question: str
    intent: str
    symbol: Optional[str]
    day: Optional[str]
    query: Optional[str]
    note: Optional[str]
    date_filter: bool
    period: Optional[list]
    answer: str
    brief: dict
    steps: dict


def llm_route(question, today):
    from kap_triage.analysis.llm import CLIENT, MODEL

    schema = Route
    prompt = ROUTER_PROMPT.format(today=today, yesterday=today - timedelta(days=1))
    resp = CLIENT.chat(
        model=MODEL,
        messages=[{'role': 'user', 'content': prompt + question}],
        format=schema.model_json_schema(),
        options={'temperature': 0, 'num_ctx': 4096},
    )
    try:
        return schema.model_validate_json(resp.message.content).model_dump()
    except ValidationError:
        return {'intent': 'unknown', 'symbol': None, 'date': None, 'query': None}


def load_context():
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        symbols = {
            r[0] for r in con.execute('SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL').fetchall()
        }
        last_disc = con.execute('SELECT max(CAST(published_at AS DATE)) FROM disclosures').fetchall()[0][0]
        last_bar = con.execute("SELECT max(date) FROM daily_bars WHERE symbol='XU100'").fetchall()[0][0]
    finally:
        con.close()
    from kap_triage.assistant.names import load_names

    return {
        'symbols': symbols,
        'last_disclosure': last_disc,
        'last_bar': last_bar,
        'today': date.today(),
        'names': load_names(),
    }


def validate(route, question, ctx, names=None):
    """Code checks on the LLM route: known ticker, real date, sensible defaults.
    names (router v2): companies found in the question by code (ticker or name table) decide the ticker."""
    intent = route.get('intent') if route.get('intent') in INTENTS else 'unknown'
    symbol = (route.get('symbol') or '').strip().upper() or None
    found = None
    if names is not None:
        from kap_triage.assistant.names import mentions

        found = mentions(question, ctx['symbols'], names) or None
    note = None
    if found:
        symbol = found[0]
        if len(found) > 1:
            note = f'Soruda birden fazla şirket geçiyor ({", ".join(found)}); {symbol} için cevap verildi. Yanlışsa yalnızca istediğiniz şirketi yazın.'
    else:
        if symbol not in ctx['symbols']:
            # the model may miss or invent a ticker: trust only tickers written in the question
            written = [t for t in TICKER_RE.findall(question) if t in ctx['symbols']]
            symbol = written[0] if written else None
        if symbol and symbol not in TICKER_RE.findall(question.upper()):
            note = f'Hisse kodu şirket adından çıkarıldı: {symbol}. Yanlışsa soruda kodu yazın.'
    try:
        day = date.fromisoformat(route['date']) if route.get('date') else None
    except ValueError:
        day = None
    if intent == 'morning' and day is None:
        day = ctx['last_disclosure']
        note = f'Tarih verilmedi; veritabanındaki son bildirim günü kullanıldı ({day}).'
    elif intent == 'morning' and ctx['last_disclosure'] and day > ctx['last_disclosure']:
        note = (
            f'{day} günün bildirimleri henüz toplanmadı (toplama her gece 23:43). '
            f'Son toplanan gün gösteriliyor: {ctx["last_disclosure"]}.'
        )
        day = ctx['last_disclosure']
    if intent == 'why_moved':
        if day is None or day > ctx['last_bar']:
            note = ' '.join(
                filter(None, [note, f'Fiyat verisi {ctx["last_bar"]} tarihinde bitiyor; o gün kullanıldı.'])
            )
            day = ctx['last_bar']
    if intent in ('company', 'why_moved') and symbol is None:
        intent, note = 'unknown', 'Soruda veritabanında olan bir hisse kodu bulamadım (ör. ASELS).'
    query = route.get('query') or question
    return {'intent': intent, 'symbol': symbol, 'day': str(day) if day else None, 'query': query, 'note': note}


def route_question(route, question, ctx, v2=None):
    """Validated route; v2 (docs/router_v2_rule.md) adds names, the date filter flag and the detail switch."""
    v2 = V2 if v2 is None else v2
    if v2 and not route.get('date'):
        from kap_triage.assistant.periods import word_date

        written = word_date(question, ctx['today'])  # Amendment 1: the router sometimes misses a written date
        if written:
            route = {**route, 'date': str(written)}
    v = validate(route, question, ctx, names=ctx.get('names', []) if v2 else None)
    if v2:
        v['date_filter'] = True
        if DETAIL_SWITCH:
            v = detail_switch(v, question)
        if BRIEF_SWITCH:
            v = brief_switch(v, question)
    if PERIODS:
        v = period_switch(v, question, ctx)
    return v


def period_switch(v, question, ctx):
    """docs/relative_periods_rule.md: a period phrase (code) overrides the router's date for the period tools."""
    from kap_triage.assistant.periods import question_period

    p = question_period(question, ctx['today'])
    if p is None:
        return v
    start, end = p
    if v['intent'] not in PERIOD_TOOLS:
        return {**v, 'note': ' '.join(filter(None, [v.get('note'), 'Dönem ifadesi bu soru türünde kullanılmıyor.']))}
    last = ctx.get('last_disclosure')
    note = f'Dönem: {start} – {end}.'
    if last and end > last:
        end = last
        note = f'Dönem: {start} – {end} (son toplanan gün {last}; toplama her gece 23:43).'
    old = v.get('note')
    if v['intent'] == 'morning' and old and ('Tarih verilmedi' in old or 'henüz toplanmadı' in old):
        old = None  # the single-day notes of validate no longer apply
    return {**v, 'day': None, 'period': [str(start), str(end)], 'note': ' '.join(filter(None, [old, note]))}


def detail_switch(v, question):
    """Code rule after validate: a detail question about one disclosure goes to the detail tool."""
    if v['intent'] in ('company', 'search') and DETAIL_RE.search(question):
        return {**v, 'intent': 'detail'}
    return v


def brief_switch(v, question):
    """Code rule after validate (docs/brief_rule.md): a "look at X" question with a ticker runs the multi-step brief."""
    if v['intent'] == 'company' and v.get('symbol') and BRIEF_RE.search(question):
        return {**v, 'intent': 'brief'}
    return v


def tr_pct(x):
    return ('+' if x >= 0 else '') + f'{x * 100:.1f}'.replace('.', ',') + '%'


def period_list(start, end):
    """docs/relative_periods_rule.md: every disclosure in the period by date (no extraction, no importance order)."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        rows = con.execute(
            """SELECT d.published_at,d.symbol,d.is_update OR d.is_correction,n.amount,trim(n.cur),d.kap_url
            FROM disclosures d LEFT JOIN new_business n ON n.url=d.kap_url
            WHERE CAST(d.published_at AS DATE) BETWEEN ? AND ? ORDER BY d.published_at""",
            [date.fromisoformat(start), date.fromisoformat(end)],
        ).fetchall()
    finally:
        con.close()
    return render_period_list(start, end, rows)


def render_period_list(start, end, rows):
    from kap_triage.assistant.names import company_label

    lines = [
        f'# {start} – {end}: {len(rows)} yeni iş ilişkisi bildirimi',
        '',
        'Önem sırası yalnızca tek gün için hesaplanır; burada tarih sırası var. Bir günü sormak için tarihi yazın.',
        '',
    ]
    for pub, sym, upd, amount, cur, url in rows[:PERIOD_LIST_MAX]:
        amt = f'{amount:,.0f}'.replace(',', '.') + f' {cur} (Matriks kaydı)' if amount else 'tutar kaydı yok'
        lines.append(
            f'- {str(pub)[:10]} | {company_label(sym, short=True)} | {"güncelleme/düzeltme" if upd else "yeni"} | {amt} | {url}'
        )
    if len(rows) > PERIOD_LIST_MAX:
        lines.append(
            f'(ilk {PERIOD_LIST_MAX} gösterildi; {len(rows) - PERIOD_LIST_MAX} bildirim daha var, dönemi daraltın)'
        )
    if not rows:
        lines.append('Bu dönemde bildirim yok.')
    return '\n'.join(lines) + '\n'


def tool_morning(state):
    """The saved nightly list (two readings per disclosure). If it is missing or stale, the list is built here with
    one reading for this answer only and not saved, so the official list stays the nightly two-reading one."""
    from kap_triage.analysis.morning import enrich, extract_day, load_saved, render

    if state.get('period'):
        return period_list(*state['period'])
    day = date.fromisoformat(state['day'])
    items = load_saved(day)
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        n = con.execute('SELECT count(*) FROM disclosures WHERE CAST(published_at AS DATE)=?', [day]).fetchall()[0][0]
    finally:
        con.close()
    if n == 0:  # no disclosures that day (weekend, holiday): nothing to read, so no extraction and no index update
        return render(str(day), [])
    if items is None or len(items) != n:  # missing, or saved before that night's collection: built for this answer only
        items = enrich(extract_day(day))
        return (
            render(str(day), items)
            + '\nBu liste bu cevap için tek okumayla hazırlandı; gece listesi (iki okuma) değildir.\n'
        )
    return render(str(day), items)


def tool_company(state):
    p = state.get('period')
    if p:
        day = date.fromisoformat(p[1])
    else:
        day = date.fromisoformat(state['day']) if state.get('day') else date.today()
    lo, inclusive = (date.fromisoformat(p[0]), True) if p else (day - timedelta(days=365), False)
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        rows = con.execute(
            f"""SELECT d.published_at,d.is_update OR d.is_correction,n.amount,trim(n.cur),d.kap_url
            FROM disclosures d LEFT JOIN new_business n ON n.url=d.kap_url
            WHERE d.symbol=? AND CAST(d.published_at AS DATE)<=? AND CAST(d.published_at AS DATE){'>=' if inclusive else '>'}?
            ORDER BY d.published_at DESC""",
            [state['symbol'], day, lo],
        ).fetchall()
    finally:
        con.close()
    from kap_triage.assistant.names import company_label

    span = f'{p[0]} – {p[1]} arasında' if p else 'son 12 ayda'
    lines = [
        f'# {company_label(state["symbol"])}: {span} {len(rows)} yeni iş ilişkisi bildirimi'
        + ('' if p else f' ({day} itibarıyla)'),
        '',
    ]
    for pub, upd, amount, cur, url in rows:
        amt = f'{amount:,.0f}'.replace(',', '.') + f' {cur} (Matriks kaydı)' if amount else 'tutar kaydı yok'
        lines.append(f'- {str(pub)[:10]} | {"güncelleme/düzeltme" if upd else "yeni"} | {amt} | {url}')
    if not rows:
        lines.append('Bu dönemde bildirim yok.')
    return '\n'.join(lines) + '\n'


def tool_why_moved(state):
    from kap_triage.analysis.prices import (
        INDEX,
        Z_ABNORMAL,
        SPLIT_JUMP,
        abnormal,
        daily_returns,
        disclosures_before,
        load_closes,
        sigma_before,
    )

    sym = state['symbol']
    day = date.fromisoformat(state['day'])
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        series = load_closes(con, day - timedelta(days=150), day, [sym])
        if sym not in series:
            return f'{sym} için fiyat verisi yok.\n'
        ar = abnormal(daily_returns(series[sym]), daily_returns(series[INDEX]))
        days = [d for d in sorted(ar) if d <= day]
        if not days:
            return f'{sym} için {day} öncesinde fiyat verisi yok.\n'
        d = days[-1]
        a, r = ar[d]
        sigma, _ = sigma_before(ar, d)
        disc = disclosures_before(con, sym, d)
    finally:
        con.close()
    from kap_triage.assistant.names import company_label

    lines = [f"# {company_label(sym)}, {d}: hisse {tr_pct(r)}, XU100'e göre {tr_pct(a)}"]
    if d != day:
        lines.append(f'({day} işlem günü değil; ondan önceki son işlem günü kullanıldı.)')
    if abs(r) > SPLIT_JUMP:
        lines.append(
            'Hareket borsa günlük limitinin üstünde: büyük ihtimalle bölünme veya bedelsiz. '
            'Fiyatlar düzeltilmemiş olduğu için bu bir haber etkisi olarak yorumlanmamalı.'
        )
        return '\n'.join(lines) + '\n'
    if sigma:
        z = a / sigma
        lines.append(
            f'Olağandışı mı: {"evet" if abs(z) >= Z_ABNORMAL else "hayır"} (z {z:.1f}'.replace('.', ',')
            + f', eşik {Z_ABNORMAL:.0f}; önceki 60 işlem gününe göre)'
        )
    else:
        lines.append('Olağandışı mı: hesaplanamadı (fiyat geçmişi kısa).')
    if disc:
        lines.append(f'Önceki 4 günde {len(disc)} yeni iş ilişkisi bildirimi var:')
        lines += [f'- {x["published_at"][:16]} {x["kap_url"]}' for x in disc]
        lines.append('Bildirim hareketin sebebi olabilir; tek sebep olduğu kanıtlanmış değildir.')
    else:
        lines.append(
            'Önceki 4 günde yeni iş ilişkisi bildirimi yok. Sebep başka bir yerde olabilir '
            '(bu sistem yalnızca yeni iş ilişkisi bildirimlerine bakar).'
        )
    return '\n'.join(lines) + '\n'


def tool_search(state):
    # the full question is searched, as in the evaluation (docs/rerank_rule.md); the router's topic is only shown
    from kap_triage.assistant.search import load_index, search_question

    index = load_index()
    if index is None:
        return NO_INDEX
    period = state.get('period')
    day = state.get('day') if state.get('date_filter') and not period else None
    hits = search_question(index, state['question'], symbol=state.get('symbol'), k=5, on_day=day, period=period)
    from kap_triage.assistant.names import company_label

    head = f'# Arama: {state.get("query") or state["question"]}' + (
        f' ({company_label(state["symbol"])})' if state.get('symbol') else ''
    )
    span = f'{period[0]} – {period[1]}' if period else day
    lines = [head + (f', {span}' if span and hits else ''), '']
    if span and not hits:
        lines.append(
            f'{span} {"döneminde" if period else "tarihinde"} uygun bildirim bulunamadı; tüm tarihlerde arandı.'
        )
        hits = search_question(index, state['question'], symbol=state.get('symbol'), k=5)
    lines += [
        f'{i}. {h["published_at"][:10]} | {company_label(h["symbol"], short=True)} | {h["kap_url"]}'
        for i, h in enumerate(hits, 1)
    ]
    lines.append('')
    lines.append(
        'Sonuçlar anlam benzerliğine göre sıralandı. Bağımsız 20 soruluk testte doğru bildirim ilk 5 sonuçta 20/20, '
        'ilk sırada 17/20. KAP metnini okuyarak doğrulayın.'
    )
    return '\n'.join(lines) + '\n'


NO_INDEX = (
    'Arama indeksi bu bilgisayarda yok, bu yüzden konu araması ve bildirim kartı çalışmıyor. Örnek veride kurulmaz; '
    'gerçek veride "python main.py index --build" ile kurulur.\n'
)
# measured fields, said on every card and brief (docs/results.md: Set C, fields_rule 13 Nov)
FIELDS_NOTE = (
    'Tutar ve para birimi ölçüldü (bağımsız 100 bildirimde 1 sessiz hata); uzun sözleşme (en az 2 yıl) bilgisi de '
    'ölçüldü (50 bildirimde 3 hata). '
    'Yurt içi/dışı ve ilişkili taraf ölçüldü ama eşiği geçmedi: model bunları kaçırabiliyor, uydurmuyor. '
    'Diğer alanlar ölçülmedi.'
)
EVENT_TR = {'order': 'sipariş', 'contract': 'sözleşme', 'tender': 'ihale', 'other': 'diğer'}
ORIGIN_TR = {'domestic': 'yurt içi', 'foreign': 'yurt dışı', 'unknown': 'belirtilmemiş'}
_CARDS = {}  # news_id -> extraction, this process only (a repeated question is instant)


def extract_card(news_id):
    """Production extraction of one disclosure (pipeline.analyze: v3 + code checks + layered defence)."""
    if news_id not in _CARDS:
        from kap_triage.analysis.pipeline import analyze, defence_context, judge_pass, load_rows

        rows = load_rows(None, [news_id])
        if not rows:
            return None
        text = rows[0][4]
        matriks, judge = defence_context([news_id])
        data = analyze(text, matriks=matriks.get(str(news_id)))
        data = judge_pass([data], [text], judge)[0]
        from kap_triage.analysis.defence import source_sentence

        data['source_sentence'] = source_sentence(text, data.get('amount'))[0]  # verbatim, display only
        _CARDS[news_id] = data
    return _CARDS[news_id]


def card_lines(hit, data):
    """Card text from the extracted fields; every value comes from code, never written by the model."""
    from kap_triage.analysis.morning import REVIEW_TR, tr_num
    from kap_triage.assistant.names import company_label

    lines = [
        f'# Bildirim kartı: {company_label(hit["symbol"])}, {hit["published_at"][:10]}',
        f'Kaynak: {hit["kap_url"]}',
    ]
    if data is None or 'run_error' in data.get('needs_review_reasons', []):
        return lines + ['Bu bildirimden alan çıkarılamadı; KAP metnini okuyun.']
    v = lambda x: x if x not in (None, '') else 'belirtilmemiş'
    lines.append(f'Konu: {v(data.get("subject"))}')
    lines.append(f'Tür: {EVENT_TR.get(data.get("event_type"), v(data.get("event_type")))}')
    origin = data.get('counterparty_origin')
    origin_txt = 'yurt içi/dışı belirtilmemiş' if origin in (None, 'unknown') else ORIGIN_TR.get(origin, origin)
    lines.append(f'Karşı taraf: {v(data.get("counterparty_name"))} ({origin_txt})')
    lines.append(f'Süre / teslim: {v(data.get("duration"))}')
    if data.get('amount') is not None:
        amt = f'Tutar: {tr_num(data["amount"], 0)} {data.get("currency") or ""}'.rstrip()
        lines.append(amt + (' (KDV dahil)' if data.get('vat_included') else ''))
        if 'source_sentence' in data:
            src = data['source_sentence']
            lines.append(
                f'Kaynak cümle: "{src}"' if src else 'Kaynak cümle: tutar metinde aynen geçmiyor; KAP metnini okuyun.'
            )
    else:
        lines.append('Tutar: metinde belirtilmemiş')
    if data.get('is_revision'):
        prev = data.get('previous_amount')
        lines.append('Revizyon: evet' + (f', önceki tutar {tr_num(prev, 0)}' if prev is not None else ''))
    rp = data.get('related_party')
    lines.append(f'İlişkili taraf: {"evet" if rp is True else "hayır" if rp is False else "belirtilmemiş"}')
    if data.get('needs_review'):
        lines.append('KONTROL ET: ' + '; '.join(REVIEW_TR.get(c, c) for c in data['needs_review_reasons']))
    return lines


def detail_answer(question, symbol=None, search=None, extract=None, card=None, on_day=None, period=None):
    """Top hit of the measured search (ticker-filtered) as a card, the other hits as links."""
    card = CARD if card is None else card
    if search is None:
        from kap_triage.assistant.search import load_index, search_question

        index = load_index()
        if index is None:
            return {'hits': [], 'data': None, 'text': NO_INDEX}
        search = lambda q, sym: search_question(index, q, symbol=sym, k=5, on_day=on_day, period=period) or (
            search_question(index, q, symbol=sym, k=5) if (on_day or period) else []
        )
    hits = search(question, symbol)
    if not hits:
        return {'hits': [], 'data': None, 'text': 'Bu soruya uygun bildirim bulunamadı.\n'}
    data = (extract or extract_card)(hits[0]['news_id']) if card else None
    lines = (
        card_lines(hits[0], data)
        if card
        else [f'# Arama: {question}', f'1. {hits[0]["published_at"][:10]} | {hits[0]["symbol"]} | {hits[0]["kap_url"]}']
    )
    rest = hits[1:]
    if rest:
        lines += ['', ('Başka bildirim olabilir:' if card else '')]
        from kap_triage.assistant.names import company_label

        lines += [
            f'{i}. {h["published_at"][:10]} | {company_label(h["symbol"], short=True)} | {h["kap_url"]}'
            for i, h in enumerate(rest, 2)
        ]
    lines.append('')
    if card:
        lines.append(
            'Alanlar bu bildirimin metninden otomatik çıkarıldı. '
            + FIELDS_NOTE
            + ' Kart ilk sıradaki bildirime aittir; '
            'KAP metnini okuyarak doğrulayın.'
        )
    else:
        lines.append("Arama ilk 5'te doğru bildirimi bağımsız testte 20/20 buldu. KAP metnini okuyarak doğrulayın.")
    return {'hits': hits, 'data': data, 'text': '\n'.join(l for l in lines if l is not None) + '\n'}


def tool_detail(state):
    period = state.get('period')
    day = state.get('day') if state.get('date_filter') and not period else None
    return detail_answer(state['question'], state.get('symbol'), on_day=day, period=period)['text']


def tool_help(state):
    return (
        'Şunları sorabilirsiniz:\n'
        '- "Bugün neye bakmalıyım?" veya "30 Ekim\'deki bildirimler"\n'
        '- "Aselsan son bir yılda hangi işleri aldı?" (şirket adı ya da kodu)\n'
        '- Dönem: "bu hafta", "geçen ay", "son 3 ay", "geçen çeyrek", "bu yıl" (başka ifadeler okunmaz)\n'
        '- "Fonet\'in Aydın sözleşmesinin süresi kaç ay?" (ayrıntı: bildirim kartı)\n'
        '- "THYAO dün neden düştü?"\n'
        '- "Aselsan\'a bir bak" (şirket özeti: son bildirim, fiyat, 12 ay, benzerleri)\n'
        '- "Irak\'taki projelerle ilgili bildirimler"\n'
    )


# --- company brief: multi-step flow, docs/brief_rule.md (every value from code; the model writes no sentence) ---
def _timed(name, fn):
    def run(state):
        t = time.time()
        brief = dict(state.get('brief') or {})
        try:
            brief[name] = fn(state, brief)
        except Exception as e:
            brief[name] = {'error': type(e).__name__}
        steps = dict(state.get('steps') or {})
        steps[name] = round(time.time() - t, 1)
        return {'brief': brief, 'steps': steps}

    return run


def step_latest(state, brief):
    from kap_triage.analysis.importance import score_result

    day = state.get('day') or str(date.today())
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        rows = con.execute(
            """SELECT news_id,kap_url,symbol,published_at FROM disclosures
            WHERE symbol=? AND CAST(published_at AS DATE)<=? ORDER BY published_at DESC LIMIT 1""",
            [state['symbol'], day],
        ).fetchall()
        if not rows:
            return None
        nid, url, sym, pub = rows[0]
        hit = {'news_id': str(nid), 'kap_url': url, 'symbol': sym, 'published_at': str(pub)}
        data = extract_card(hit['news_id'])
        imp = score_result(con, {**(data or {}), **hit}) if data else None
    finally:
        con.close()
    return {'hit': hit, 'data': data, 'importance': imp}


def step_history(state, brief):
    latest = brief.get('latest') or {}
    end = latest['hit']['published_at'][:10] if latest.get('hit') else (state.get('day') or str(date.today()))
    day = date.fromisoformat(end)
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        rows = con.execute(
            """SELECT d.published_at,d.is_update OR d.is_correction,n.amount,trim(n.cur),d.kap_url
            FROM disclosures d LEFT JOIN new_business n ON n.url=d.kap_url
            WHERE d.symbol=? AND CAST(d.published_at AS DATE)<=? AND CAST(d.published_at AS DATE)>?
            ORDER BY d.published_at DESC""",
            [state['symbol'], day, day - timedelta(days=365)],
        ).fetchall()
    finally:
        con.close()
    return [
        {'published_at': str(p)[:10], 'update': bool(u), 'amount': a, 'currency': c, 'kap_url': k}
        for p, u, a, c, k in rows
    ]


def step_reaction(state, brief):
    from kap_triage.analysis.morning import reaction

    latest = brief.get('latest') or {}
    if not latest.get('hit'):
        return None
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return reaction(con, state['symbol'], datetime.fromisoformat(latest['hit']['published_at']))
    finally:
        con.close()


def step_similar(state, brief):
    from kap_triage.assistant.search import load_index, similar_earlier

    latest = brief.get('latest') or {}
    if not latest.get('hit'):
        return []
    index = load_index()
    if index is None:  # no search index on this computer (e.g. sample data): say so, never "none found"
        return {'error': 'no_index'}
    return similar_earlier(index, latest['hit']['news_id'], k=3)


def compose_brief(symbol, brief):
    """Brief text from the four steps; a failed or empty step becomes one line, the rest still shows."""
    from kap_triage.analysis.morning import LEVEL_TR, reaction_text, reason_text, tr_num
    from kap_triage.assistant.names import company_label

    lines = [f'# {company_label(symbol)}: şirket özeti', '', '## 1. Son bildirim']
    latest = brief.get('latest')
    if not latest or latest.get('error') or not latest.get('hit'):
        lines.append(
            'Son bildirim çıkarılamadı (hata).' if latest and latest.get('error') else 'Son bildirim bulunamadı.'
        )
    else:
        lines += card_lines(latest['hit'], latest['data'])[1:]
        imp = latest.get('importance')
        if imp:
            lines.append(
                f'Önem: {LEVEL_TR[imp["level"]]} (skor {imp["score"]})'
                + ('; ' + '; '.join(reason_text(r) for r in imp['reasons']) if imp['reasons'] else '')
            )
    lines += ['', '## 2. Fiyat tepkisi']
    rx = brief.get('reaction')
    lines.append(
        'Hesaplanamadı.'
        if rx is None or rx.get('error') or 'status' not in rx
        else reaction_text(rx)
        + (
            f'; olağandışı mı: {"evet" if abs(rx["z0"]) >= 3 else "hayır"} (eşik z 3)'
            if rx.get('z0') is not None
            else ''
        )
    )
    lines += ['', '## 3. Son 12 ay']
    hist = brief.get('history')
    if hist is None or isinstance(hist, dict):
        lines.append('Hesaplanamadı.')
    else:
        n_amt = sum(1 for h in hist if h['amount'])
        lines.append(
            f'{len(hist)} bildirim, {sum(h["update"] for h in hist)} güncelleme/düzeltme, {n_amt} Matriks tutar kaydı.'
        )
        for h in hist[:BRIEF_HISTORY_LINKS]:
            amt = f'{tr_num(h["amount"], 0)} {h["currency"]}' if h['amount'] else 'tutar kaydı yok'
            lines.append(f'- {h["published_at"]} | {"güncelleme" if h["update"] else "yeni"} | {amt} | {h["kap_url"]}')
        if len(hist) > BRIEF_HISTORY_LINKS:
            lines.append(f'- ... {len(hist) - BRIEF_HISTORY_LINKS} bildirim daha')
    lines += ['', '## 4. Benzer eski bildirimler']
    sim = brief.get('similar')
    if isinstance(sim, dict) and sim.get('error') == 'no_index':
        lines.append(
            'Arama indeksi bu bilgisayarda yok, bu yüzden benzer bildirimler aranamadı (örnek veride kurulmaz).'
        )
    elif sim is None or isinstance(sim, dict):
        lines.append('Hesaplanamadı.')
    elif not sim:
        lines.append('Yok.')
    else:
        lines += [f'- {x["published_at"][:10]} (benzerlik {tr_num(x["score"], 2)}) {x["kap_url"]}' for x in sim]
    lines += [
        '',
        FIELDS_NOTE + ' Önem skoru kurallı bir sıralamadır, tahmin değildir. Karar öncesi KAP metnini okuyun.',
    ]
    return '\n'.join(lines) + '\n'


def step_compose(state):
    return {
        'answer': (state['note'] + '\n\n' if state.get('note') else '')
        + compose_brief(state['symbol'], state.get('brief') or {})
    }


BRIEF_STEPS = (
    ('latest', step_latest),
    ('history', step_history),
    ('reaction', step_reaction),
    ('similar', step_similar),
)


TOOLS = {
    'morning': tool_morning,
    'company': tool_company,
    'why_moved': tool_why_moved,
    'search': tool_search,
    'detail': tool_detail,
    'unknown': tool_help,
}


def build_graph(router, tools, ctx, steps=BRIEF_STEPS):
    """route -> one tool -> END; intent brief -> the step chain -> compose -> END (docs/brief_rule.md)."""

    def _route(state):
        if state.get('intent'):  # guided form (web/form.py): the route is chosen by the analyst, no LLM
            return {'intent': state['intent']}
        r = router(state['question'], ctx['today'])
        return route_question(r, state['question'], ctx)

    def tool_node(name):
        def run(state):
            answer = tools[name](state)
            if state.get('note'):
                answer = state['note'] + '\n\n' + answer
            return {'answer': answer}

        return run

    g = StateGraph(State)
    g.add_node('route', _route)
    for name in tools:
        g.add_node(name, tool_node(name))
    g.add_edge(START, 'route')
    targets = {name: name for name in tools}
    if steps:
        names = [n for n, _ in steps]
        for n, fn in steps:
            g.add_node(n, _timed(n, fn))
        g.add_node('compose', step_compose)
        for a, b in zip(names, names[1:] + ['compose']):
            g.add_edge(a, b)
        g.add_edge('compose', END)
        targets['brief'] = names[0]
    g.add_conditional_edges('route', lambda s: s['intent'], targets)
    for name in tools:
        g.add_edge(name, END)
    return g.compile()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('question', nargs='?')
    ap.add_argument('--quiet', action='store_true', help='print only the route and the answer length')
    args = ap.parse_args()
    if not args.question:
        ap.error('give a question')
    now = datetime.now()
    if now.hour == 23 and 40 <= now.minute <= 50:
        raise SystemExit('collection window, try after 23:50')
    ctx = load_context()
    graph = build_graph(llm_route, TOOLS, ctx)
    out = graph.invoke({'question': args.question})
    if args.quiet:
        print(
            json.dumps({k: out.get(k) for k in ('intent', 'symbol', 'day')}, ensure_ascii=False),
            f'answer_lines={out["answer"].count(chr(10))}',
        )
    else:
        print(out['answer'])


if __name__ == '__main__':
    main()
