"""Chat page for the triage agent: one question box, answers from assistant/agent.py.

Served by panel.py (the start page "/"). The question goes to the same LangGraph agent as the
terminal command (route -> validate -> one tool); numbers and links still come from code.
No JavaScript: a plain form, the server renders the whole conversation (strict CSP in panel.py).
History lives only in this process's memory (cleared on restart, never written to disk).
Every text is HTML-escaped; only kap.org.tr links become clickable.

Usage:
  python -m kap_triage.web.panel --serve        # http://127.0.0.1:8765
"""

import html
import re
import threading
import time
from datetime import datetime

MAX_QUESTION = 500
MAX_HISTORY = 50
URL_RE = re.compile(r'https?://[^\s|<>"]+')
KAP_RE = re.compile(r'^https://(www\.)?kap\.org\.tr/')
EXAMPLES = [
    'Bugün neye bakmalıyım?',
    '17 Eylül 2026 bildirimleri',
    'Aselsan son bir yılda hangi işleri aldı?',
    "Fonet'in Aydın sözleşmesinin süresi kaç ay?",
    "KONTR 28 Ekim'de neden yükseldi?",
    "Şa-Ra Enerji'ye bir bak",
    "Irak'taki projelerle ilgili bildirimler",
]
HINT = (
    'Şirket adı ya da hisse kodu, bir tarih ve sorduğunuz ayrıntıyı (süre, tutar, karşı taraf, ülke) yazabilirsiniz. '
    'Ayrıntı sorularında cevap, bildirimden çıkarılan alanlarla bir kart olarak gelir.'
)
HISTORY = []
INTENT_TR = {
    'morning': 'günün listesi',
    'company': 'son 12 ay',
    'brief': 'şirket özeti',
    'why_moved': 'fiyat hareketi',
    'search': 'konu araması',
    'detail': 'bildirim kartı',
    'unknown': 'yardım',
}
LOCK = threading.Lock()  # one question at a time: Ollama runs one model call at once anyway

e = lambda x: html.escape('' if x is None else str(x))

CSS = """.msg{border-radius:10px;padding:10px 14px;margin:10px 0;max-width:85%}
.q{background:var(--q);margin-left:auto}.a{background:var(--surface);border:1px solid var(--line)}
.ah{font-weight:600;margin-bottom:4px}.a div{margin:2px 0}.err{border-left:4px solid var(--red)}
.ask textarea{width:100%;box-sizing:border-box;font:inherit;padding:8px}
.ex{display:inline-block;margin:4px 6px 4px 0}.ex button{border-radius:14px;padding:4px 12px;background:transparent;
color:var(--accent);border:1px solid var(--accent)}"""


def linkify(line):
    """Escape a line; KAP links become "KAP bildirimi" links, other URLs stay plain text."""
    out, pos = [], 0
    for m in URL_RE.finditer(line):
        url = m.group(0).rstrip('.,;:)')
        out.append(e(line[pos : m.start()]))
        if KAP_RE.match(url):
            out.append(f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">KAP bildirimi</a>')
        else:
            out.append(e(url))
        pos = m.start() + len(url)
    out.append(e(line[pos:]))
    return ''.join(out)


def render_answer(text):
    lines = []
    for raw in (text or '').splitlines():
        s = raw.rstrip()
        if not s:
            continue
        if s.startswith('# ') or s.startswith('## '):  # brief sections ("## 1. Son bildirim") are headings too
            lines.append(f'<div class="ah">{linkify(s.lstrip("#").strip())}</div>')
        else:
            lines.append(f'<div>{linkify(s)}</div>')
    return ''.join(lines)


WINDOW_GUARD = (
    True  # panel --sample sets False: sample/data is not the nightly DB, so the 23:40-23:50 window does not apply
)


def in_collection_window(now):
    """The one switch for every night-window check (panel GET routes and form context, form.run, chat.ask)."""
    return WINDOW_GUARD and now.hour == 23 and 40 <= now.minute <= 50


def default_runner(question):
    from kap_triage.assistant.agent import TOOLS, build_graph, llm_route, load_context

    ctx = load_context()  # one short read-only DB read per question, so a new night's data is seen
    return build_graph(llm_route, TOOLS, ctx).invoke({'question': question})


def ask(question, runner=None, now=None, history=None):
    """Run one question and append the record to the history; never raises."""
    history = HISTORY if history is None else history
    now = now or datetime.now()
    rec = {'q': question, 'at': now.strftime('%H:%M'), 'intent': None, 'seconds': 0.0, 'error': False}
    if in_collection_window(now):
        rec.update(
            a="Gece toplama penceresi (23:40-23:50): veritabanına dokunulmuyor. 23:50'den sonra tekrar sorun.",
            error=True,
        )
    else:
        t0 = time.time()
        try:
            with LOCK:
                out = (runner or default_runner)(question)
            rec.update(a=out.get('answer') or '', intent=out.get('intent'))
        except Exception as ex:  # Ollama down, DB locked, ...: show the type, keep the page alive
            rec.update(
                a=f'Cevap üretilemedi ({type(ex).__name__}). Ollama açık mı? Terminalde "ollama list" ile kontrol edin.',
                error=True,
            )
        rec['seconds'] = round(time.time() - t0, 1)
    history.append(rec)
    del history[:-MAX_HISTORY]
    return rec


LINKS = (
    ('/genel', 'Genel bakış'),
    ('/', 'Sohbet'),
    ('/form', 'Rehberli sorgu'),
    ('/days', 'Sabah listeleri'),
    ('/kontroller', 'Kontrol geçmişi'),
    ('/themes', 'Haftalık temalar'),
    ('/kart', 'KAP kartı'),
    ('/guvenilirlik', 'Güvenilirlik'),
)
HEADER = (
    '<header class="top"><div class="topin"><div class="brand"><span>KAP</span>Bildirim Önceliklendirme Asistanı'
    '<small>yeni iş ilişkisi · yerel modeller</small></div><nav>'
    + ''.join(f'<a href="{u}">{t}</a>' for u, t in LINKS)
    + '<a class="theme" href="/tema" title="Tema: sistem → koyu → açık" aria-label="Temayı değiştir">◐</a>'
    '</nav></div></header>'
)
NAV = ''  # the navigation lives in HEADER (panel.page); kept so callers stay unchanged


def render_body(history):
    out = [
        NAV,
        '<h1>Asistana sorun</h1>',
        '<p class="muted">Yeni iş ilişkisi bildirimleri hakkında sorun. Rakamlar ve KAP linkleri doğrudan bildirim '
        'verisinden gelir; veriler bu bilgisayardan çıkmaz.</p>',
    ]
    for i, r in enumerate(history):
        anchor = ' id="son"' if i == len(history) - 1 else ''
        out.append(f'<div class="msg q"{anchor}>{e(r["q"])}</div>')
        meta = f'{e(r["at"])} · {r["seconds"]:.1f} sn'.replace('.', ',') + (
            f' · {e(INTENT_TR.get(r["intent"], r["intent"]))}' if r['intent'] else ''
        )
        out.append(
            f'<div class="msg a{" err" if r["error"] else ""}">{render_answer(r["a"])}'
            f'<div class="muted">{meta}</div></div>'
        )
    out.append(
        '<form class="ask" method="post" action="/chat">'
        f'<textarea name="q" rows="2" maxlength="{MAX_QUESTION}" required '
        'placeholder="Sorunuzu yazın, ör. Bugün neye bakmalıyım?"></textarea>'
        '<button>Sor</button> <span class="muted">Cevap birkaç saniye sürer; ilk arama modelleri yüklediği için daha uzun.</span>'
        '</form>'
    )
    out.append(f'<p class="muted">{e(HINT)}</p>')
    if not history:
        out.append('<p class="muted">Örnek sorular:</p>')
    out += [
        f'<form class="ex" method="post" action="/chat"><input type="hidden" name="q" value="{e(q)}">'
        f'<button>{e(q)}</button></form>'
        for q in EXAMPLES
    ]
    if history:
        out.append('<form class="ex" method="post" action="/chat/clear"><button>Sohbeti temizle</button></form>')
    out.append('<p class="muted">Kaynak: KAP bildirimleri ve Matriks verisi. Karar öncesi KAP metnini okuyun.</p>')
    return ''.join(out)
