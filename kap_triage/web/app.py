"""The analyst panel as a FastAPI app. Local only: every request needs a local Host header
(DNS rebinding), a POST from another site's page is refused (Origin), and pages that read the
DB answer 503 during the nightly collection (23:40-23:50).

  HTML pages   rendered by panel.py, chat.py, form.py, reliability.py and kart.py
  /api/v1      JSON: the saved days, one morning list, the desk payload that n8n reads
  /kart        kap-kart: a card from a pasted disclosure text (no database, no Matriks)

Start: python main.py panel [--sample]   -> http://127.0.0.1:8765
"""

import json
import re
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

import kap_triage.analysis.desks as desks
import kap_triage.assistant.themes as themes
import kap_triage.web.approvals as approvals
import kap_triage.web.chat as chat
import kap_triage.web.form as form
import kap_triage.web.kart as kart
import kap_triage.web.panel as panel
import kap_triage.web.reliability as reliability
import kap_triage.web.watchlist as watchlist

CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"  # no scripts, no outside resources
HTML = 'text/html; charset=utf-8'
JSON = 'application/json; charset=utf-8'
DAY = r'\d{4}-\d{2}-\d{2}'
MAX_FORM = 4096  # bytes: review, watchlist, chat and form posts are short

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # the API docs page would load outside scripts


def theme(request):
    t = request.cookies.get('theme')
    return t if t in panel.THEMES else 'auto'


def send(request, code, body, ctype=HTML, location=None, cookie=None):
    """One response: the chosen theme on <html> (HTML pages only), the CSP header, an optional redirect and cookie."""
    t = theme(request)
    if t != 'auto' and ctype == HTML:
        body = body.replace('<html lang="tr">', f'<html lang="tr" data-theme="{t}">', 1)
    headers = {'Content-Type': ctype, 'Content-Security-Policy': CSP}
    if location:
        headers['Location'] = location
    if cookie:
        headers['Set-Cookie'] = cookie
    return Response(body.encode('utf-8'), status_code=code, headers=headers)


def page(request, code, title, html):
    return send(request, code, panel.page(title, html))


def kart_page(request, code, body):
    return send(request, code, panel.page('KAP kartı', body, kart.CSS))


def as_json(request, code, data):
    return send(request, code, json.dumps(data, ensure_ascii=False), ctype=JSON)


class BadBody(Exception):
    """A POST body the app does not read: 400 (Content-Length is not a non-negative number) or 413 (too large)."""

    def __init__(self, code):
        self.code = code


async def read_form(request, limit):
    """The urlencoded form fields of a body of at most `limit` bytes, also when it comes in chunks
    (no Content-Length). Raises BadBody; a body is never cut silently."""
    value = request.headers.get('content-length')
    if value is not None and not (value.isascii() and value.isdigit()):
        raise BadBody(400)
    if value is not None and int(value) > limit:
        raise BadBody(413)
    raw = b''
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise BadBody(413)
    return {k: v[0] for k, v in parse_qs(raw.decode('utf-8', errors='replace')).items()}


def origin_ok(origin):
    """No Origin (same-site form, curl) or a local one; a malformed Origin is refused."""
    if not origin:
        return True
    try:
        return urlparse(origin).hostname in panel.LOCAL_NAMES
    except ValueError:
        return False


@app.middleware('http')
async def local_only(request, call_next):
    if not panel.host_ok(request.headers.get('host')):
        return page(request, 403, 'Hayır', '<p>Yalnızca yerel istek.</p>')
    if request.url.path == '/onay' and request.url.hostname != '127.0.0.1':
        return page(request, 403, 'Hayır', '<p>Yalnızca 127.0.0.1.</p>')
    if request.method == 'POST' and not origin_ok(request.headers.get('origin')):
        return page(request, 403, 'Hayır', '<p>Yalnızca yerel istek.</p>')
    if request.method == 'GET':
        blocked = panel.window_block(request.url.path, request.url.query, datetime.now())
        if blocked:
            return send(request, *blocked)
    return await call_next(request)


@app.exception_handler(BadBody)
async def bad_body(request, exc):
    msg = 'Geçersiz istek.' if exc.code == 400 else 'İstek çok büyük.'
    if request.url.path == '/kart':
        return kart_page(request, exc.code, kart.render_body(card=f'<p class="flag">{msg}</p>'))
    return page(request, exc.code, 'Hata', f'<p>{msg}</p>')


@app.exception_handler(HTTPException)
async def not_found(request, exc):
    # unknown path or wrong method: one plain page, as for every other "no such page"
    return page(request, 404, 'Yok', '<p>Sayfa yok.</p>')


# --- pages ------------------------------------------------------------------


@app.get('/')
def home(request: Request):
    return page(request, 200, 'KAP asistanı', chat.render_body(chat.HISTORY))


@app.get('/days')
def days(request: Request):
    return send(request, 200, panel.render_index(panel.available_days()))


@app.get('/genel')
@app.get('/kontroller')
def overview(request: Request):
    # saved lists + review log only (no DB read, so no night-window block)
    reviews = panel.load_reviews()
    rows = panel.review_rows(reviews)
    rstats = panel.reason_stats(reviews)
    if request.url.path == '/kontroller':
        return send(request, 200, panel.render_reviews(rows, rstats))
    watch, broken = watchlist.load()
    all_days = panel.available_days()
    latest = (panel.load_day(all_days[0]) or []) if all_days else []
    return send(
        request,
        200,
        panel.render_overview(
            panel.all_day_stats(all_days, reviews),
            latest,
            reviews,
            rows,
            rstats,
            watch=watch,
            watch_broken=broken,
            query=request.url.query,
        ),
    )


@app.get('/day/{day}')
def day_page(request: Request, day: str):
    items = panel.load_day(day) if re.fullmatch(DAY, day) else None
    if items is None:
        return page(request, 404, 'Yok', '<p>Bu gün için sabah listesi yok.</p>')
    from kap_triage.web.charts import charts_for_items

    query = request.url.query
    only = (parse_qs(query).get(panel.FILTER_PARAM) or [''])[0] == '1'
    watch, broken = watchlist.load()
    return send(
        request,
        200,
        panel.render_day(
            day,
            items,
            panel.load_sectors(),
            panel.DESKS,
            panel.load_reviews(),
            charts_for_items(items),
            panel.sources_for_items(items),
            watch=watch,
            only_watched=only,
            query=query,
            watch_broken=broken,
        ),
    )


@app.get('/tema')
def switch_theme(request: Request):
    # theme switch without JavaScript: the next theme in a cookie, back to the same page
    nxt = panel.THEMES[(panel.THEMES.index(theme(request)) + 1) % len(panel.THEMES)]
    age = 0 if nxt == 'auto' else 31536000
    return send(
        request,
        303,
        '',
        location=panel.theme_back(request.headers.get('referer')),
        cookie=f'theme={nxt}; Path=/; Max-Age={age}; SameSite=Strict',
    )


@app.get('/guvenilirlik')
def reliability_page(request: Request):
    return page(request, 200, 'Güvenilirlik', reliability.render_body(chat.NAV))


@app.get('/form')
def form_page(request: Request):
    kind = (parse_qs(request.url.query).get('type') or [None])[0]
    kind = kind if kind in form.TYPES else None  # unknown type -> step 1
    symbols = panel.load_symbols() if kind and 'symbol' in form.FIELDS[kind] else set()
    return page(
        request,
        200,
        'Rehberli sorgu',
        form.render_body(symbols, form.display_names(), form.LAST, chat.NAV, chat.render_answer, kind=kind),
    )


@app.get('/themes')
def themes_index(request: Request):
    out = themes.load_clusters()
    if out is None:
        return send(request, 200, panel.render_themes_index([], None, 0))
    last = themes.last_clustered(out['assign'])
    return send(request, 200, panel.render_themes_index(themes.weeks(out['assign']), last, themes.count_after(last)))


@app.get('/themes/{week}')
def theme_week(request: Request, week: str):
    out = themes.load_clusters()
    try:
        start = date.fromisoformat(week) if re.fullmatch(DAY, week) else None
    except ValueError:
        start = None
    if out is None or start is None or themes.week_start(start) != start:
        return page(request, 404, 'Yok', '<p>Bu hafta yok (hafta pazartesi ile başlar).</p>')
    view = themes.week_view(out, start)
    urls = themes.load_meta([a['news_id'] for v in view for a in v['items']])
    return send(request, 200, panel.render_week(str(start), view, panel.load_sectors(), urls))


@app.get('/kart')
def kart_form(request: Request):
    text = kart.example_text((parse_qs(request.url.query).get('ornek') or [''])[0])
    return kart_page(request, 200, kart.render_body(text))


@app.get('/onay')
def mail_approvals(request: Request):
    return page(request, 200, 'E-posta onayı', approvals.render())


# --- forms (POST, answered with a redirect) -----------------------------------


@app.post('/onay')
async def mail_decision(request: Request):
    data = await read_form(request, MAX_FORM)
    status = await run_in_threadpool(
        approvals.decide, data.get('day', ''), data.get('desk', ''), data.get('decision', ''), data.get('reason', '')
    )
    if status == 303:
        return send(request, 303, '', location='/onay')
    messages = {
        400: 'Kararı ve ret gerekçesini kontrol edin.',
        409: 'Bu e-posta karar beklemiyor.',
        502: 'Gönderim doğrulanamadı. E-posta onay bekliyor. Yeniden onaylamadan önce yerel posta kutusunu kontrol edin.',
        503: 'İşlem tamamlanamadı. Yerel posta kutusunu ve onay listesini kontrol edin.',
    }
    return page(request, status, 'E-posta onayı', f'<p>{messages[status]}</p>')


@app.post('/review')
async def review(request: Request):
    data = await read_form(request, MAX_FORM)
    day = data.get('day', '')
    if not panel.DAY_RE.match(day) or data.get('decision') not in panel.DECISIONS or not data.get('news_id'):
        return page(request, 400, 'Hata', '<p>Geçersiz istek.</p>')
    flagged = {i['news_id']: i for i in (panel.load_day(day) or []) if i['importance']['needs_review']}
    if data['news_id'] not in flagged:
        return page(request, 400, 'Hata', '<p>Bu bildirim o günün kontrol listesinde yok.</p>')
    panel.record_review(
        data['news_id'],
        day,
        data['decision'],
        data.get('note'),
        reasons=flagged[data['news_id']]['importance']['needs_review_reasons'],
    )
    return send(request, 303, '', location=f'/day/{day}')


@app.post('/takip')
async def follow(request: Request):
    data = await read_form(request, MAX_FORM)
    if data.get('action') not in ('add', 'remove'):
        return page(request, 400, 'Hata', '<p>Geçersiz istek.</p>')
    fn = watchlist.add if data['action'] == 'add' else watchlist.remove
    status = fn(watchlist.PATH, data.get('symbol', ''))
    return send(request, 303, '', location=panel.with_message(panel.safe_back(data.get('back')), status))


@app.post('/chat/clear')
def chat_clear(request: Request):
    chat.HISTORY.clear()
    return send(request, 303, '', location='/')


@app.post('/chat')
async def chat_ask(request: Request):
    data = await read_form(request, MAX_FORM)
    q = (data.get('q') or '').strip()
    if not q or len(q) > chat.MAX_QUESTION:
        return page(request, 400, 'Hata', '<p>Soru boş ya da çok uzun.</p>')
    rec = await run_in_threadpool(chat.ask, q)  # the model call takes seconds; keep other pages answering
    print(f'chat: intent={rec["intent"]} seconds={rec["seconds"]} error={rec["error"]}', flush=True)  # no text
    return send(request, 303, '', location='/#son')


def run_form(data):
    from kap_triage.assistant.agent import load_context

    try:
        ctx = None if chat.in_collection_window(datetime.now()) else load_context()  # no DB read in the window
        return form.run(data, ctx)
    except Exception as ex:  # DB missing or locked: show the type, keep the page alive
        rec = {
            'form': {k: data.get(k, '') for k in ('type', 'symbol', 'day', 'text')},
            'seconds': 0.0,
            'error': True,
            'at': datetime.now().strftime('%H:%M'),
            'answer': f'Veritabanı okunamadı ({type(ex).__name__}).',
        }
        form.LAST.clear()
        form.LAST.update(rec)
        return rec


@app.post('/form')
async def form_ask(request: Request):
    data = await read_form(request, MAX_FORM)
    rec = await run_in_threadpool(run_form, data)
    print(f'form: type={rec["form"]["type"]} seconds={rec["seconds"]} error={rec["error"]}', flush=True)  # no text
    kind = rec['form'].get('type')
    return send(request, 303, '', location=f'/form?type={kind}#son' if kind in form.TYPES else '/form')


@app.post('/kart')
async def kart_card(request: Request):
    data = await read_form(request, kart.MAX_BODY)
    text, link = data.get('text', ''), data.get('link', '')
    if not text.strip() or len(text) > kart.MAX_CHARS:
        return kart_page(
            request,
            200,
            kart.render_body(
                text[: kart.MAX_CHARS], link, '<p class="flag">Metin boş ya da 30.000 karakterden uzun.</p>'
            ),
        )
    card = await run_in_threadpool(kart.analyze, text)
    return kart_page(
        request, 200, kart.render_body(text, link, kart.render_card_html(card, text, kart.safe_link(link)))
    )


# --- JSON API -----------------------------------------------------------------


@app.get('/api/v1/days')
def api_days(request: Request):
    return as_json(request, 200, {'days': panel.available_days()})


@app.get('/api/v1/day/{day}')
def api_day(request: Request, day: str):
    items = panel.load_day(day) if re.fullmatch(DAY, day) else None
    if items is None:
        return as_json(request, 404, {'error': 'no morning list', 'day': day})
    return as_json(request, 200, {'day': day, 'items': items})


@app.get('/api/v1/desks/{day}')
def api_desks(request: Request, day: str):
    # docs/n8n_routing_rule.md: what n8n reads (no amounts, no disclosure text)
    if day == 'latest':
        all_days = panel.available_days()
        day = all_days[0] if all_days else None
    items = panel.load_day(day) if day and re.fullmatch(DAY, day) else None
    if items is None:
        return as_json(request, 404, {'error': 'no morning list', 'day': day})
    return as_json(request, 200, desks.payload(day, items, panel.load_sectors(), panel.DESKS))
