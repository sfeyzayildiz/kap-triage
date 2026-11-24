'''Panel pages: chat with the agent (start page) and the morning list per sector desk, with a human
confirm step for flagged items. The routes are in app.py (FastAPI); this module renders the HTML.

Local only (binds 127.0.0.1). Reads the saved morning list data/morning_<day>.jsonl (no LLM,
no network). Desk = Matriks sector of the symbol (table symbol_sectors), optionally grouped by
DESKS below ({"sector name": "desk name"}, filled after the sector load); no sector -> "Atanmamış".
Reviewer decisions for flagged items are appended to data/review_log.jsonl (not the DB, so the
panel never holds a DB lock the nightly job needs). Latest decision per news_id wins.
All text is HTML-escaped (KAP text is external input); KAP links are shown only for kap.org.tr.

Reading map (search for these names; the last part is tests only):
  1. data loading: load_sectors, load_reviews, record_review, available_days, sources_for_items
  2. page frame and safety: CSS, page, reads_db / window_block (no DB read in the night window)
  3. day page: render_item, look_first_box, render_day; themes: render_themes_index, render_week
  4. overview /genel and review history /kontroller: column_chart, flag_chart, render_overview, render_reviews
  5. request helpers used by app.py: theme_back, safe_back, with_message, host_ok
  6. main: command line (tests are in tests/)

Usage:
  python main.py panel [--sample]     # http://127.0.0.1:8765 (chat), /genel (overview), /days (morning lists)
  python main.py panel --stats        # counts only: confirmed / rejected, overall and per reason code
'''
import argparse
import glob
import html
import json
import os
import re
from collections import Counter
from datetime import date, datetime
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

import kap_triage.web.chat as chat
import kap_triage.web.form as form
import kap_triage.web.reliability as reliability
import kap_triage.web.watchlist as watchlist
from kap_triage.settings import settings

DB_PATH=settings.path('kap.duckdb')
DESKS={}  # sector name -> desk name; empty until the sector names are known
LOG_PATH=settings.path('review_log.jsonl')
# bind address: 127.0.0.1 on the Mac; the Docker image sets PANEL_HOST=0.0.0.0 and compose publishes
# the port on 127.0.0.1 only, so the panel stays local either way (docs/docker.md)
HOST=os.environ.get('PANEL_HOST','127.0.0.1')
LOCAL_NAMES=('127.0.0.1','localhost')  # accepted Origin / Referer hosts
HOST_NAMES=LOCAL_NAMES+('panel',)  # accepted Host header names; 'panel' = the compose service n8n calls (n8n/desk_routing.json)
PORT=8765
UNASSIGNED='Atanmamış'
SAMPLE=False  # --sample: made-up data in sample/data/ (kap_triage/sample.py); every page says so
SAMPLE_BANNER=('<div class="card high"><b>Örnek veri.</b> Şirketler, bildirimler, tutarlar, sektörler ve fiyatlar '
               'uydurmadır; gerçek veri lisans gereği paylaşılmaz. Sabah listeleri gerçek gece zinciriyle üretildi, '
               'yalnızca model cevapları önceden yazıldı. KAP linkleri gerçek bir bildirime gitmez. Sohbet, konu araması, '
               'bildirim kartı ve şirket özeti yerel Ollama ister (arama ve benzer bildirimler ayrıca embedding modeli); '
               'diğer sayfalar modelsiz çalışır. '
               'Başlamak için: <a href="/genel">Genel bakış</a>.</div>')
DECISIONS={'confirm':'Doğru (KAP metniyle kontrol ettim)','reject':'Yanlış (çıkarım hatalı)'}
DAY_RE=re.compile(r'^\d{4}-\d{2}-\d{2}$')
KAP_RE=re.compile(r'^https://(www\.)?kap\.org\.tr/')

e=lambda x:html.escape('' if x is None else str(x))


def load_sectors(path=DB_PATH):
    '''symbol -> sector name; {} if the table is not loaded yet (one short read).'''
    import duckdb
    if not os.path.exists(path):
        return {}
    con=duckdb.connect(path,read_only=True)
    try:
        if not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='symbol_sectors'").fetchall()[0][0]:
            return {}
        return {s:pretty_sector(n) for s,n in con.execute('SELECT symbol,sector_name FROM symbol_sectors').fetchall()}
    finally:
        con.close()


def load_symbols(path=DB_PATH):
    '''Disclosure symbols for the form's drop-down (one short read); empty without a DB.'''
    import duckdb
    if not os.path.exists(path):
        return set()
    con=duckdb.connect(path,read_only=True)
    try:
        return {r[0] for r in con.execute('SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL').fetchall()}
    finally:
        con.close()


ASCII_TR={'ESYA':'EŞYA','ULASIM':'ULAŞIM','TAS':'TAŞ'}  # Matriks names written without Turkish letters (display only)
SMALL_WORDS={'ve','ile','veya'}


def pretty_sector(name):
    '''Display form of a Matriks sector name: spacing around commas and dashes, Turkish title case. Data unchanged.'''
    if not name:
        return name
    import re as _re
    s=_re.sub(r'\s*,\s*',', ',name.strip())
    s=_re.sub(r'\s*-\s*',' - ',s)
    words=[]
    for w in s.split():
        w=ASCII_TR.get(w.upper().strip(','),w.strip(','))+(',' if w.endswith(',') else '')
        low=w.replace('İ','i').replace('I','ı').lower()
        if words and low.strip(',') in SMALL_WORDS:
            words.append(low)
        else:
            first=low[0]
            words.append(({'i':'İ','ı':'I'}.get(first) or first.upper())+low[1:])
    return ' '.join(words)


def desk_of(symbol,sectors,desks):
    sector=sectors.get(symbol)
    if not sector:
        return UNASSIGNED
    return desks.get(sector,sector)


def by_desk(items,sectors,desks):
    '''desk -> items (morning priority order); desks with something to look at first come first.'''
    from kap_triage.analysis.morning import priority
    groups={}
    for i in sorted(items,key=priority):
        groups.setdefault(desk_of(i['symbol'],sectors,desks),[]).append(i)
    def look(i):
        return i['importance']['needs_review'] or i['importance']['level']=='high'
    return dict(sorted(groups.items(),key=lambda kv:(-sum(look(i) for i in kv[1]),kv[0]==UNASSIGNED,kv[0])))


def load_reviews(path=None):
    '''news_id -> latest decision record (path None = the current LOG_PATH).'''
    path=LOG_PATH if path is None else path
    out={}
    if path and os.path.exists(path):
        with open(path,encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line)
                    out[r['news_id']]=r
    return out


def record_review(news_id,day,decision,note,path=None,now=None,reasons=None):
    '''reasons: the flag codes shown at review time, so later rebuilds of the day cannot change the stats.'''
    if decision not in DECISIONS:
        raise ValueError('decision')
    path=LOG_PATH if path is None else path
    r={'news_id':str(news_id),'day':day,'decision':decision,'note':(note or '')[:500],
       'at':(now or datetime.now()).isoformat(timespec='seconds')}
    if reasons is not None:
        r['reasons']=list(reasons)
    with open(path,'a',encoding='utf-8') as f:
        f.write(json.dumps(r,ensure_ascii=False)+'\n')
    return r


def available_days():
    days=[os.path.basename(p)[len('morning_'):-len('.jsonl')] for p in glob.glob(settings.path('morning_*.jsonl'))]
    return sorted((d for d in days if DAY_RE.match(d)),reverse=True)


def kap_link(url):
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">KAP</a>' if url and KAP_RE.match(url) \
        else f'<span class="muted">KAP linki geçersiz: {e(url)}</span>'


# dark tokens: used by the system setting (unless the analyst chose light) and by the theme switch (/tema, a cookie)
DARK=('--bg:#0c121c;--surface:#141d2b;--ink:#e6ebf2;--muted:#9aa5b5;--line:#26324a;--brand:#08111f;--accent:#2dd4bf;'
      '--amber:#f59e0b;--red:#f87171;--green:#4ade80;--tint-red:#2a1719;--tint-green:#13261b;--q:#1a2a42;'
      '--shadow:0 2px 10px rgba(0,0,0,.35);color-scheme:dark')
THEMES=('auto','dark','light')  # the switch cycles in this order
CSS=''':root{--bg:#f3f5f8;--surface:#fff;--ink:#14213d;--muted:#5b6474;--line:#dde2ea;--brand:#0b1f3a;
--accent:#0f766e;--amber:#b45309;--red:#b91c1c;--green:#15803d;--tint-red:#fdf1f1;--tint-green:#eef8f1;--q:#e8f0fb;
--shadow:0 2px 8px rgba(11,31,58,.08)}
@media (prefers-color-scheme: dark){:root:not([data-theme=light]){'''+DARK+'''}}
:root[data-theme=dark]{'''+DARK+'''}
:root[data-theme=light]{color-scheme:light}
nav a.theme{font-size:1.1rem;margin-left:4px}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:var(--bg);
color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.45}
header.top{position:sticky;top:0;z-index:20;background:var(--brand);border-bottom:3px solid var(--accent);padding:10px 16px}
.topin{max-width:980px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px 22px}
.brand{color:#fff;font-weight:700;letter-spacing:.02em}.brand span{color:var(--accent);margin-right:6px}
.brand small{color:#9fb0c6;font-weight:400;margin-left:8px}
nav a{color:#d3dce8;text-decoration:none;margin-right:16px;font-size:.95rem}nav a:hover{color:#fff;text-decoration:underline}
main{max-width:980px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:1.35rem;margin:6px 0 10px}
h2{font-size:.95rem;letter-spacing:.01em;color:var(--muted);margin:28px 0 8px;
padding-left:8px;border-left:3px solid var(--accent)}
a{color:var(--accent)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}
.card,.review{scroll-margin-top:64px}
main>.card.high:first-child{padding:6px 12px;margin:0 0 10px;font-size:.84rem;line-height:1.38}
.card[id^=c]>div:not([class]):has(+.src),.card[id^=c]>div:not([class]):has(+div:not([class])){font-weight:600;margin-top:4px}
.flag{border-left:4px solid var(--red)}.high{border-left:4px solid var(--amber)}
.badge{display:inline-block;font-size:.75rem;font-weight:600;padding:1px 8px;border-radius:10px;border:1px solid var(--line);
color:var(--muted);margin-left:6px}.badge.high{color:var(--amber);border-color:var(--amber)}
.badge.flag{color:var(--red);border-color:var(--red)}.badge.done{color:var(--green);border-color:var(--green)}a.badge{text-decoration:none}
.muted{color:var(--muted);font-size:.9rem}
.review{background:var(--tint-red);padding:8px;border-radius:6px;margin-top:6px}.done{background:var(--tint-green)}
.review form{display:flex;flex-wrap:nowrap;align-items:center;gap:8px;margin-top:6px}
.review form input[type=text]{flex:1 1 180px;width:auto;min-width:140px}
.review form button{background:var(--surface);color:var(--ink);border:1.5px solid var(--line);margin-right:0;white-space:nowrap}
.review button[value=confirm]{color:var(--green);border-color:var(--green)}
.review button[value=confirm]:hover{background:var(--tint-green)}
.review button[value=reject]{color:var(--red);border-color:var(--red)}
.review button[value=reject]:hover{background:var(--tint-red)}
button{font:inherit;background:var(--accent);color:#fff;border:0;border-radius:6px;padding:6px 12px;margin-right:6px;cursor:pointer}
input,select,textarea{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
input[type=text]{width:60%}
.choices{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-top:12px}
.choice{display:flex;flex-direction:column;gap:4px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;color:var(--ink);text-decoration:none}
.choice:hover{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}.choice .ic{font-size:1.4rem;color:var(--accent)}
.choice.free{border-style:dashed}
.src{border-left:3px solid var(--line);padding:2px 0 2px 10px;margin:6px 0;font-size:.9rem}.src mark{background:transparent;color:var(--accent);font-weight:700}
.chart{margin:8px 0 2px}.chart svg{width:100%;max-width:440px;height:auto;display:block}.chart figcaption{font-size:.8rem}.k.s{color:var(--accent)}.k.i{color:var(--muted)}
form.guided{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:14px}
form.guided label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted);gap:4px}
form.guided .wide{grid-column:1/-1}form.guided input[type=text]{width:100%}form.guided button{justify-self:start}
@media (max-width:760px){.review form{flex-wrap:wrap}.review form input[type=text]{flex:1 1 100%}}
@media (max-width:640px){form.guided{grid-template-columns:1fr}input[type=text]{width:100%}}'''+chat.CSS+reliability.CSS+'''
.tile{border-top:3px solid var(--accent);box-shadow:var(--shadow)}
.tile b{font-size:1.85rem;font-variant-numeric:tabular-nums;line-height:1.15}'''


def page(title,body,extra_css=''):
    '''extra_css: styles only one page needs (the overview charts), so the other pages stay byte-identical.'''
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<style>{CSS}{extra_css}</style></head><body>{chat.HEADER}<main>'
            f'{SAMPLE_BANNER if SAMPLE else ""}{body}</main></body></html>')


WINDOW_MSG='Gece toplama penceresi (23:40-23:50): veritabanına dokunulmuyor. 23:50\'den sonra tekrar deneyin.'


def reads_db(path,query=''):
    '''GET routes that open the DB (day page: sectors, prices, source sentences; desks JSON: sectors;
    form step 2 with a company: symbols; themes: counts, sectors, links).'''
    if re.match(r'^/(day|api/v1/desks)/',path) or path=='/themes' or path.startswith('/themes/'):
        return True
    if path=='/form':
        kind=(parse_qs(query).get('type') or [None])[0]
        return kind in form.TYPES and 'symbol' in form.FIELDS[kind]
    return False


def window_block(path,query,now):
    '''known_issues C6: no DB read during the nightly collection; the page says so (503) instead.'''
    if not chat.in_collection_window(now) or not reads_db(path,query):
        return None
    if path.startswith('/api/'):
        return (503,json.dumps({'error':'collection window','retry_after':'23:50'}),'application/json; charset=utf-8')
    return (503,page('Gece toplama',f'<p>{WINDOW_MSG}</p>'))


def sources_for_items(items,db=DB_PATH):
    '''{news_id: (sentence, spans)} for items with an amount (one short read-only connection); errors -> {}.'''
    import duckdb
    from kap_triage.analysis.defence import source_sentence
    ids=[i['news_id'] for i in items if i.get('amount') is not None]
    if not ids or not os.path.exists(db):
        return {}
    try:
        con=duckdb.connect(db,read_only=True)
        try:
            marks=','.join('?' for _ in ids)
            rows=con.execute(f'SELECT news_id,aciklama FROM disclosures WHERE news_id IN ({marks})',ids).fetchall()
        finally:
            con.close()
    except Exception:
        return {}
    amount={i['news_id']:i['amount'] for i in items}
    return {str(n):source_sentence(t,amount[str(n)]) for n,t in rows if str(n) in amount}


def source_html(source):
    '''The amount's sentence, verbatim and escaped, the amount marked; None (text not read) -> nothing.'''
    if source is None:
        return ''
    sentence,spans=source
    if sentence is None:
        return '<div class="src muted">Kaynak cümle: tutar metinde aynen geçmiyor; KAP metnini okuyun.</div>'
    parts,pos=[],0
    for a,b in spans:
        parts.append(e(sentence[pos:a])+'<mark>'+e(sentence[a:b])+'</mark>')
        pos=b
    parts.append(e(sentence[pos:]))
    return f'<div class="src">Kaynak cümle: “{"".join(parts)}”</div>'


TR_MONTHS=('Oca','Şub','Mar','Nis','May','Haz','Tem','Ağu','Eyl','Eki','Kas','Ara')


def tr_time(at):
    '''"2026-11-10T00:41:50" -> "10 Kas 2026 00:41"; anything unreadable is shown as it is.'''
    try:
        t=datetime.fromisoformat(str(at))
    except ValueError:
        return str(at)
    return f'{t.day} {TR_MONTHS[t.month-1]} {t.year} {t:%H:%M}'


def render_item(item,day,review,chart='',source=None,watched=None,back=None):
    from kap_triage.analysis.morning import LEVEL_TR, REVIEW_TR, reaction_text, reason_text, tr_num
    imp=item['importance']
    cls='flag' if imp['needs_review'] else ('high' if imp['level']=='high' else '')
    score=f' · skor {e(imp["score"])}'
    badges=f'<span class="badge {"high" if imp["level"]=="high" else ""}">{e(LEVEL_TR.get(imp["level"],imp["level"]))}{score}</span>'
    if imp['needs_review']:
        badges+=(f'<a class="badge flag" href="#r{e(item["news_id"])}">kontrol et ↓</a>' if not review
                 else '<span class="badge done">kontrol edildi ✓</span>')
    if watched:
        badges+='<span class="badge">takipte</span>'  # neutral: green is "kontrol edildi"
    from kap_triage.assistant.names import company_label
    out=[f'<div class="card {cls}" id="c{e(item["news_id"])}"><b>{e(company_label(item["symbol"],short=True))}</b> '
         f'<span class="muted">{e(item["symbol"])}</span>{badges} · {kap_link(item.get("kap_url"))}']
    if item.get('amount') is not None:
        out.append(f'<div>Tutar: {e(tr_num(item["amount"],0))} {e(item.get("currency"))}</div>')
        out.append(source_html(source))
    reasons=[reason_text(r) for r in imp.get('reasons',[])]
    if reasons:
        out.append(f'<div>Neden: {e("; ".join(reasons))}</div>')
    if item.get('reaction'):
        out.append(f'<div class="muted">Fiyat: {e(reaction_text(item["reaction"]))}</div>')
    out.append(chart or '')  # built by charts.py from numbers only
    if imp['needs_review']:
        codes='; '.join(REVIEW_TR.get(c,c) for c in imp['needs_review_reasons'])
        if review:
            out.append(f'<div class="review done">Kontrol edildi: {e(DECISIONS[review["decision"]])} '
                       f'({e(tr_time(review["at"]))}){" - "+e(review["note"]) if review.get("note") else ""}</div>')
        else:
            out.append(f'<div class="review" id="r{e(item["news_id"])}"><b>KONTROL ET:</b> {e(codes)}<br>'
                       f'<form method="post" action="/review">'
                       f'<input type="hidden" name="news_id" value="{e(item["news_id"])}">'
                       f'<input type="hidden" name="day" value="{e(day)}">'
                       f'<input type="text" name="note" maxlength="500" placeholder="not (isteğe bağlı)"> '
                       + ''.join(f'<button name="decision" value="{k}">{e(v)}</button>' for k,v in DECISIONS.items())
                       + '</form></div>')
    if watched is not None:
        act,lbl=('remove','Takipten çıkar') if watched else ('add','Takibe al')
        out.append(f'<form method="post" action="/takip" class="watch">'  # secondary look: WATCH_CSS
                   f'<input type="hidden" name="symbol" value="{e(item["symbol"])}">'
                   f'<input type="hidden" name="action" value="{act}">'
                   f'<input type="hidden" name="back" value="{e(back or "")}">'
                   f'<button>{lbl}</button></form>')
    out.append('</div>')
    return ''.join(out)


LOOK_FIRST_MAX=3


def look_first_box(items,reviews,base=''):
    '''"Önce bak": up to 3 look-first items (high or flagged) in the morning list's order, each with its reasons
    through the same path as the cards and a link to its card.
    base: the day page's address when the box is shown elsewhere (overview); '' on the day page itself.'''
    from kap_triage.analysis.morning import REVIEW_TR, priority, reason_text
    from kap_triage.assistant.names import company_label
    look=sorted([i for i in items if i['importance']['needs_review'] or i['importance']['level']=='high'],key=priority)
    if not look:
        return ''
    rows=[]
    for i in look[:LOOK_FIRST_MAX]:
        imp=i['importance']
        why=[reason_text(r) for r in imp.get('reasons',[])]
        if imp['needs_review'] and i['news_id'] not in reviews:
            why=['kontrol et: '+', '.join(REVIEW_TR.get(c,c) for c in imp['needs_review_reasons'])]+why
        rows.append(f'<li><a href="{e(base)}#c{e(i["news_id"])}"><b>{e(company_label(i["symbol"],short=True))}</b></a> '
                    f'<span class="muted">{e(i["symbol"])}</span>: {e("; ".join(why) or "yüksek önem")}</li>')
    more=f'<p class="muted">ve {len(look)-LOOK_FIRST_MAX} bildirim daha (aşağıda)</p>' if len(look)>LOOK_FIRST_MAX else ''
    return f'<div class="card high look"><b>Önce bak ({len(look)})</b><ol>{"".join(rows)}</ol>{more}</div>'


WATCH_CSS=('form.watch{margin-top:6px}'
           'form.watch button{background:transparent;color:var(--muted);border:1px solid var(--line);font-size:.82rem;padding:2px 8px}'
           'form.watch button:hover{color:var(--accent);border-color:var(--accent)}')


def render_day(day,items,sectors,desks,reviews,charts=None,sources=None,watch=None,only_watched=False,query='',watch_broken=False):
    watch_set=set(watch or ())
    watch_active=watch is not None and not watch_broken
    watched_items=[i for i in items if i['symbol'] in watch_set] if watch_active else []
    filtered=only_watched and watch_active
    shown=watched_items if filtered else items
    groups=by_desk(shown,sectors,desks)
    flagged=[i for i in shown if i['importance']['needs_review']]
    done=sum(i['news_id'] in reviews for i in flagged)
    body=[chat.NAV+f'<h1>Sabah listesi: {e(day)}</h1>']
    if watch_broken:
        body.append(f'<div class="card flag">{e(watchlist.MESSAGES["broken"])}</div>')
    elif watch_active:
        all_a=f'<a href="/day/{e(day)}">Tümü</a>'
        only_a=f'<a href="/day/{e(day)}?{FILTER_PARAM}=1">Sadece takip ettiklerim ({len(watched_items)})</a>'
        body.append(f'<p>{all_a if filtered else f"<b>{all_a}</b>"} · {f"<b>{only_a}</b>" if filtered else only_a}</p>')
        msg=takip_message(query)
        if msg:
            body.append(msg)
    body.append(f'<p>{len(shown)} bildirim, {len(groups)} masa; kontrol gereken {len(flagged)}, kontrol edilen {done}.</p>')
    if not shown:
        body.append('<p>Bu gün takip listenizdeki şirketlerden bildirim yok.</p>' if filtered and items
                    else '<p>Bu gün yeni iş ilişkisi bildirimi yok.</p>')
    body.append(look_first_box(shown,reviews))
    back=f'/day/{day}?{FILTER_PARAM}=1' if filtered else f'/day/{day}'
    for desk,its in groups.items():
        body.append(f'<h2>{e(desk)} ({len(its)})</h2>')
        body+=[render_item(i,day,reviews.get(i['news_id']),(charts or {}).get(i['news_id'],''),(sources or {}).get(i['news_id']),
                           watched=(i['symbol'] in watch_set) if watch_active else None,
                           back=back if watch_active else None)
               for i in its]
    body.append('<p class="muted">Kaynak: KAP bildirimleri ve Matriks verisi. Skor kurallı bir sıralamadır, tahmin değildir; '
                'karar öncesi KAP metnini okuyun.</p>')
    return page(f'Sabah listesi {day}',''.join(body),WATCH_CSS if watch_active else '')


def render_index(days):
    links=''.join(f'<li><a href="/day/{e(d)}">{e(d)}</a></li>' for d in days) or '<li>Kayıtlı sabah listesi yok.</li>'
    return page('Masa paneli',chat.NAV+
                f'<h1>Sabah listeleri</h1><ul>{links}</ul>')


THEME_LIMIT=('Temalar bildirim metinlerinin benzerliğinden otomatik çıkarılır ve sektörü yalnızca kısmen yansıtır; '
             'benzer bildirim şablonu kullanan şirketler aynı temada toplanabilir. Masa ataması Matriks sektörüne '
             'göredir; temalar haftaya genel bakış içindir.')


def fmt1(x):
    return f'{x:.1f}'.replace('.',',')


def render_themes_index(week_rows,last,n_after):
    links=''.join(f'<li><a href="/themes/{e(w)}">{e(w)} haftası</a> ({n} bildirim)</li>' for w,n in week_rows) \
        or '<li>Kümeleme yok (clusters.json bulunamadı).</li>'
    note=(f'<p class="muted">Son kümelenen bildirim: {e(last[:10])}. Sonraki {n_after} bildirim henüz kümelenmedi '
          '(yeniden kurmak kümeleri ve tema numaralarını değiştirir).</p>') if last else ''
    return page('Haftalık temalar',chat.NAV+f'<h1>Haftalık temalar</h1>{note}<ul>{links}</ul>'
                f'<p class="muted">{e(THEME_LIMIT)}</p>')


def render_week(start,view,sectors,urls):
    n=sum(v['n'] for v in view)
    body=[chat.NAV,f'<h1>Haftalık temalar: {e(start)} haftası</h1>',
          f'<p>{n} bildirim, {len(view)} tema.</p>']
    if not view:
        body.append('<p>Bu hafta kümelenmiş bildirim yok.</p>')
    for v in view:
        title=', '.join(v['words']) if v['words'] else 'tema kelimesi yok (kelime en az 3 şirkette geçmeli)'
        body.append(f'<h2>{e(title)} ({v["n"]} bildirim, {v["companies_week"]} şirket)</h2>')
        notes=[f'normalde haftada {fmt1(v["avg_per_week"])} bildirim',f'tüm dönemde {v["companies_all"]} şirket']
        if v['companies_all']==1:
            notes.append('tek şirketin bildirim şablonu (şablon etkisi)')
        sec=Counter(desk_of(a['symbol'],sectors,{}) for a in v['items'])
        notes.append('sektörler: '+', '.join(f'{s} {c}' for s,c in sec.most_common()))
        body.append(f'<p class="muted">{e("; ".join(notes))}</p><ul>')
        body+= [f'<li>{e(a["symbol"])} · {e(a["published_at"][:10])} · {kap_link(urls.get(a["news_id"]))}</li>'
                for a in v['items']]
        body.append('</ul>')
    body.append(f'<p class="muted">{e(THEME_LIMIT)}</p>')
    return page(f'Temalar {start}',''.join(body))


# --- overview (/genel) and review history (/kontroller): saved lists + review log only, no DB, no model ---
CHART_DAYS=30
OVERVIEW_CSS='''.ov{margin:6px 0 4px}.ov figcaption{margin-bottom:6px}
.cols{display:flex;align-items:flex-end;gap:2px;height:150px;border-bottom:1px solid var(--line)}
.col{flex:1 1 0;min-width:0;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center}
.col:hover .stack,.col:focus-visible .stack{outline:2px solid var(--accent);outline-offset:1px}
.stack{width:100%;max-width:24px;display:flex;flex-direction:column-reverse;gap:2px;border-radius:4px 4px 0 0;overflow:hidden}
.seg{display:block;min-height:3px}.seg.flag{background:var(--red)}.seg.look{background:var(--amber)}
.seg.other{background:var(--muted);opacity:.5}
.xlab{display:flex;gap:2px;font-size:.72rem;color:var(--muted);margin-top:3px}
.xlab span{flex:1 1 0;min-width:0;text-align:center;white-space:nowrap}
.keys{margin:8px 0 2px}.key{display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:.85rem;color:var(--muted)}
.key i{display:inline-block;width:10px;height:10px;border-radius:2px;min-height:0}
.key i.hit{background:var(--accent)}.key i.miss{background:var(--muted);opacity:.5}
.hr{display:grid;grid-template-columns:minmax(110px,260px) 1fr auto;gap:4px 12px;align-items:center;margin:8px 0}
.hbar{display:flex;gap:2px;height:14px}.hbar span{display:block;height:100%}.hbar span:last-child{border-radius:0 4px 4px 0}
.hbar .hit{background:var(--accent)}.hbar .miss{background:var(--muted);opacity:.5}
.hv{font-size:.85rem;color:var(--muted);white-space:nowrap}
.scroll{overflow-x:auto}table.t th.n,table.t td.n{text-align:right}
@media (max-width:640px){.hr{grid-template-columns:1fr auto}.hr .hv{order:2}.hr .hbar{order:3;grid-column:1/-1}}'''
# watchlist layer on the overview (only when the watchlist is shown): inline remove buttons, the add box
OV_WATCH_CSS=('form.watch.inline{display:inline;margin:0 0 0 6px}'
              'form.watch.inline button{background:transparent;color:var(--muted);border:1px solid var(--line);font-size:.82rem;padding:1px 7px}'
              'form.watch.inline button:hover{color:var(--accent);border-color:var(--accent)}'
              'form.wadd{margin:8px 0}form.wadd input[type=text]{width:14em}')
EXTRA_CODES={'unknown_item':'bildirim o günün listesinde yok','not_flagged_after_rebuild':'liste yeniden kurulunca işaret kalktı',
             'no_reason_stored':'gerekçe kaydedilmemiş'}
DECISION_SHORT={'confirm':'Doğru','reject':'Yanlış (çıkarım hatalı)'}
REVIEW_NOTE=('Doğru: analist KAP metnine baktı, çıkarılan değerler doğruydu (işaret gereksiz alarmdı). Yanlış: çıkarım '
             'hatalıydı (işaret gerçek bir hatayı yakaladı). Bir bildirimde birden çok işaret olabilir; türlere göre sayıların '
             'toplamı karar sayısını geçebilir. Bu sayılar analistin geri bildirimidir, önceden yazılmış bir kuralla yapılmış '
             'kör bir ölçüm değildir.')


def code_text(code):
    from kap_triage.analysis.morning import REVIEW_TR
    return REVIEW_TR.get(code) or EXTRA_CODES.get(code,code)


def tr_day(day,year=True):
    d=date.fromisoformat(day)
    return f'{d.day} {TR_MONTHS[d.month-1]}'+(f' {d.year}' if year else '')


def day_counts(items,reviews):
    '''Counts of one saved list: disclosures, look first (high or flagged), flagged, flagged with a decision.'''
    look=[i for i in items if i['importance']['needs_review'] or i['importance']['level']=='high']
    flagged=[i for i in items if i['importance']['needs_review']]
    return {'n':len(items),'look':len(look),'flagged':len(flagged),'done':sum(i['news_id'] in reviews for i in flagged)}


def all_day_stats(days,reviews,load=None):
    load=load or load_day
    return {d:day_counts(load(d) or [],reviews) for d in days}


def count_text(day,c):
    return f'{tr_day(day)}: {c["n"]} bildirim · önce bak {c["look"]} · kontrol et {c["flagged"]} (kontrol edilen {c["done"]})'


def column_chart(stats):
    '''The last CHART_DAYS saved lists as stacked columns (kontrol et at the base, then önce bak, then the rest);
    each column links to its day; the tooltip and the table below carry the numbers.'''
    days=sorted(stats)[-CHART_DAYS:]
    if not days:
        return ''
    top=max(stats[d]['n'] for d in days) or 1
    cols,labels=[],[]
    for k,d in enumerate(days):
        c=stats[d]
        parts=(('flag',c['flagged']),('look',c['look']-c['flagged']),('other',c['n']-c['look']))
        segs=''.join(f'<span class="seg {cls}" style="flex:{v}"></span>' for cls,v in parts if v>0)
        tip=count_text(d,c)
        cols.append(f'<a class="col" href="/day/{e(d)}" title="{e(tip)}" aria-label="{e(tip)}">'
                    f'<span class="stack" style="height:{c["n"]/top*100:.0f}%">{segs}</span></a>')
        show=k==len(days)-1 or (k%5==0 and len(days)-1-k>=3)   # sparse labels that never collide
        labels.append(f'<span>{e(tr_day(d,year=False)) if show else ""}</span>')
    keys=('<div class="keys"><span class="key"><i class="seg flag"></i>kontrol et</span>'
          '<span class="key"><i class="seg look"></i>önce bak (yüksek önem)</span><span class="key"><i class="seg other"></i>diğer</span></div>')
    return (f'<figure class="ov"><figcaption class="muted">Son {len(days)} sabah listesi: günlük bildirim sayısı (en yüksek {top}). '
            f'Sütuna tıklayınca o gün açılır; sayılar üzerine gelince ve aşağıdaki tabloda.</figcaption>'
            f'<div class="cols">{"".join(cols)}</div><div class="xlab">{"".join(labels)}</div>{keys}</figure>')


def flag_chart(rstats):
    '''Per flag type: decisions where the extraction was wrong (the flag caught an error) and where it was right.'''
    rows=sorted(rstats.items(),key=lambda kv:(-(kv[1]['reject']+kv[1]['confirm']),kv[0]))
    if not rows:
        return ''
    top=max(c['reject']+c['confirm'] for _,c in rows) or 1
    out=[]
    for code,c in rows:
        hit,miss=c['reject'],c['confirm']
        label=code_text(code)
        tip=f'{label}: {hit} kararda çıkarım hatalıydı, {miss} kararda doğruydu'
        bar=''.join(f'<span class="{cls}" style="width:{v/top*100:.1f}%"></span>' for cls,v in (('hit',hit),('miss',miss)) if v)
        out.append(f'<div class="hr" title="{e(tip)}"><span>{e(label)}</span><span class="hbar">{bar}</span>'
                   f'<span class="hv">{hit} hata · {miss} doğru</span></div>')
    keys=('<div class="keys"><span class="key"><i class="hit"></i>çıkarım hatalı: işaret işe yaradı</span>'
          '<span class="key"><i class="miss"></i>çıkarım doğru: gereksiz alarm</span></div>')
    return f'<figure class="ov">{"".join(out)}{keys}</figure>'


def review_rows(reviews,load=None):
    '''[(decision record, its item from the saved list or None)], newest decision first.'''
    load=load or load_day
    lists={}
    rows=[]
    for r in reviews.values():
        if r['day'] not in lists:
            lists[r['day']]={i['news_id']:i for i in (load(r['day']) or [])}
        rows.append((r,lists[r['day']].get(r['news_id'])))
    return sorted(rows,key=lambda ri:ri[0]['at'],reverse=True)


def review_summary(rows):
    if not rows:
        return ('<p>Henüz kontrol kararı yok. Sabah listesinde "kontrol et" işaretli bir bildirimde Doğru veya Yanlış seçin; '
                'karar burada görünür.</p>')
    wrong=sum(r['decision']=='reject' for r,_ in rows)
    return (f'<p>{len(rows)} karar: {wrong} bildirimde çıkarım hatalıydı (işaret gerçek bir hatayı yakaladı), '
            f'{len(rows)-wrong} bildirimde çıkarım doğruydu (gereksiz alarm).</p>')


def render_reviews(rows,rstats):
    from kap_triage.assistant.names import company_label
    body=[chat.NAV,'<h1>Kontrol geçmişi</h1>',review_summary(rows)]
    if rows:
        body.append('<h2>İşaret türüne göre</h2>'+flag_chart(rstats))
        trs=[]
        for r,item in rows:
            codes=r['reasons'] if 'reasons' in r else (item['importance']['needs_review_reasons'] if item else [])
            who=(f'{e(company_label(item["symbol"],short=True))} <span class="muted">{e(item["symbol"])}</span>' if item
                 else '<span class="muted">listede yok</span>')
            note=r.get('note') or ''  # free text
            trs.append(f'<tr><td>{e(tr_time(r["at"]))}</td><td><a href="/day/{e(r["day"])}#c{e(r["news_id"])}">{e(tr_day(r["day"]))}</a></td>'
                       f'<td>{who}</td><td>{e("; ".join(code_text(c) for c in codes))}</td>'
                       f'<td>{e(DECISION_SHORT.get(r["decision"],r["decision"]))}</td><td>{e(note)}</td></tr>')
        body.append('<h2>Kararlar</h2><div class="scroll"><table class="t"><tr><th>Karar zamanı</th><th>Gün</th><th>Şirket</th>'
                    f'<th>İşaret</th><th>Karar</th><th>Not</th></tr>{"".join(trs)}</table></div>')
    body.append(f'<p class="muted">{e(REVIEW_NOTE)}</p>')
    return page('Kontrol geçmişi',''.join(body),OVERVIEW_CSS)


def days_table(stats):
    trs=''.join(f'<tr><td><a href="/day/{e(d)}">{e(tr_day(d))}</a></td><td class="n">{c["n"]}</td><td class="n">{c["look"]}</td>'
                f'<td class="n">{c["flagged"]}</td><td class="n">{c["done"]}</td></tr>' for d,c in sorted(stats.items(),reverse=True))
    return ('<div class="scroll"><table class="t"><tr><th>Gün</th><th class="n">Bildirim</th><th class="n">Önce bak</th>'
            f'<th class="n">Kontrol et</th><th class="n">Kontrol edilen</th></tr>{trs}</table></div>')


def render_overview(stats,last_items,reviews,rows,rstats,watch=None,watch_broken=False,query=''):
    '''One scrolling page in layers; every layer links to its detail page.
    watch: the watchlist (None = the layer is not shown, the page stays as before); it comes first, unnumbered.'''
    days=sorted(stats,reverse=True)
    body=[chat.NAV,'<h1>Genel bakış</h1>',
          '<p class="muted">Yeni iş ilişkisi bildirimleri gece okunur, sabah önem sırasıyla listelenir; şüpheli çıkarımlar '
          '"kontrol et" ile analiste gider. Bu sayfa özet; her bölümün ayrıntısı kendi sayfasında.</p>']
    watch_on=watch is not None or watch_broken
    if watch_on:
        body.append('<h2>Takip ettiklerin</h2>')
        if watch_broken:
            body.append(f'<div class="card flag">{e(watchlist.MESSAGES["broken"])}</div>')
        else:
            from kap_triage.analysis.morning import LEVEL_TR
            from kap_triage.assistant.names import company_label
            msg=takip_message(query)
            if msg:
                body.append(msg)
            wset=set(watch)
            hits=[i for i in last_items if i['symbol'] in wset]
            if hits and days:
                last=days[0]
                hrows=''.join(f'<li><a href="/day/{e(last)}#c{e(i["news_id"])}"><b>{e(company_label(i["symbol"],short=True))}</b></a> '
                              f'<span class="muted">{e(i["symbol"])} · {e(LEVEL_TR.get(i["importance"]["level"],i["importance"]["level"]))}</span></li>'
                              for i in hits)
                body.append(f'<div class="card"><b>Son listede ({len(hits)})</b><ul>{hrows}</ul></div>')
            else:
                body.append('<p class="muted">Son listede takip ettiğin şirketlerden bildirim yok.</p>')
            if watch:
                chips=''.join(f'<li><b>{e(company_label(s,short=True))}</b> <span class="muted">{e(s)}</span>'
                              f'<form method="post" action="/takip" class="watch inline">'
                              f'<input type="hidden" name="symbol" value="{e(s)}">'
                              f'<input type="hidden" name="action" value="remove">'
                              f'<input type="hidden" name="back" value="/genel">'
                              f'<button>Çıkar</button></form></li>' for s in watch)
                body.append(f'<ul>{chips}</ul>')
            else:
                body.append('<p class="muted">Takip listesi boş.</p>')
            # maxlength is a convenience only: a POST can send anything, watchlist.normalize decides on the server
            body.append('<form method="post" action="/takip" class="wadd">'
                        '<input type="text" name="symbol" maxlength="6" placeholder="Şirket kodu (ör. ASELS)" required> '
                        '<input type="hidden" name="action" value="add">'
                        '<input type="hidden" name="back" value="/genel">'
                        '<button>Takibe al</button></form>')
    if not days:
        body.append('<p>Kayıtlı sabah listesi yok.</p>')
    else:
        last=days[0]
        c=stats[last]
        recent=sorted(stats)[-CHART_DAYS:]
        tiles=''.join(f'<div class="tile"><b>{v}</b><span>{e(k)}</span></div>'
                      for v,k in ((c['n'],'bildirim'),(c['look'],'önce bak'),(c['flagged'],'kontrol et'),(f'{c["done"]}/{c["flagged"]}','kontrol edilen')))
        body+= [f'<h2>1. Son liste: <a href="/day/{e(last)}">{e(tr_day(last))}</a></h2><div class="tiles">{tiles}</div>',
                f'<p class="muted">Son {len(recent)} listede {sum(stats[d]["n"] for d in recent)} bildirim; '
                f'{sum(stats[d]["flagged"] for d in recent)} tanesi "kontrol et" ile analiste gönderildi.</p>',
                '<h2>2. Son günler</h2>'+column_chart(stats),
                f'<h2>3. Önce bak ({e(tr_day(last))})</h2>'+
                (look_first_box(last_items,reviews,base=f'/day/{last}') or '<p class="muted">Son listede önce bakılacak bildirim yok.</p>')]
    body+= ['<h2>4. Kontrol kararları</h2>'+review_summary(rows)+flag_chart(rstats)+
            '<p><a href="/kontroller">Bütün kararlar →</a></p>',
            '<h2>5. Ölçülmüş güvenilirlik</h2>'+f'<div class="tiles">{reliability.tiles_html(3)}</div>'+
            '<p><a href="/guvenilirlik">Bütün sonuçlar ve grafikler →</a></p>']
    if days:
        body.append('<h2>6. Bütün günler</h2>'+days_table(stats))
    return page('Genel bakış',''.join(body),OVERVIEW_CSS+(OV_WATCH_CSS if watch_on else ''))


def load_day(day):
    from kap_triage.analysis.morning import load_saved
    return load_saved(day)


def theme_back(referer):
    '''Where the theme switch returns: a local page of this panel, never another site (a "//host" path is one).'''
    ref=urlparse(referer or '')
    if ref.hostname in LOCAL_NAMES and ref.path.startswith('/') and not ref.path.startswith('//'):
        return ref.path+('?'+ref.query if ref.query and ref.path=='/form' else '')
    return '/'


FILTER_PARAM='takip'
MSG_PARAM='takip_msg'


def host_ok(value):
    '''Host header check against DNS rebinding: only this computer's names (and the compose service name), any port.'''
    try:
        return urlparse('//'+(value or '')).hostname in HOST_NAMES
    except ValueError:  # e.g. a malformed port or bracket
        return False


def safe_back(back):
    '''Where a watchlist POST returns: a local path of this panel, never another site or header injection.
    ASCII only: http.server encodes headers as latin-1, so another character would drop the connection.'''
    if not isinstance(back,str) or not back.isascii() or not back.startswith('/') or '//' in back or '\\' in back or '\r' in back or '\n' in back:
        return '/genel'
    return back


def with_message(back,status):
    '''Append or replace MSG_PARAM=<status> in back; keeps FILTER_PARAM and other query parameters.'''
    u=urlparse(back)
    params=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if k!=MSG_PARAM]
    if status in watchlist.MESSAGES:
        params.append((MSG_PARAM,status))
    q=urlencode(params)
    return u.path+('?'+q if q else '')+('#'+u.fragment if u.fragment else '')


def takip_message(query):
    '''Message box for a known MSG_PARAM status code; unknown or missing codes render nothing.'''
    code=(parse_qs(query or '').get(MSG_PARAM) or [''])[0]
    msg=watchlist.MESSAGES.get(code)
    return f'<div class="card">{e(msg)}</div>' if msg else ''


def stats(path=None):
    rv=load_reviews(path)
    c={'reviewed':len(rv),'confirm':0,'reject':0}
    for r in rv.values():
        c[r['decision']]+=1
    return c


def reason_stats(reviews,load=None):
    '''reason code -> {'confirm': n, 'reject': n}: which checks flag real errors (codes and counts only).'''
    load=load or load_day
    days={}
    out={}
    for nid,r in reviews.items():
        if 'reasons' in r:  # stored at review time (since 12 Nov)
            codes=r['reasons'] or ['no_reason_stored']
        else:  # older records: the day's current list, which a rebuild may have changed
            if r['day'] not in days:
                days[r['day']]={i['news_id']:i for i in (load(r['day']) or [])}
            item=days[r['day']].get(nid)
            codes=(item['importance']['needs_review_reasons'] or ['not_flagged_after_rebuild']) if item else ['unknown_item']
        for code in codes:
            out.setdefault(code,{'confirm':0,'reject':0})[r['decision']]+=1
    return dict(sorted(out.items()))




def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serve',action='store_true')
    ap.add_argument('--port',type=int,default=PORT)
    ap.add_argument('--stats',action='store_true')
    ap.add_argument('--review-log',help='another review log, e.g. data/review_log_test.jsonl for a clean test (the real log stays untouched)')
    ap.add_argument('--sample',action='store_true',
                    help='made-up sample data (main.py has already pointed the data folder to sample/data/)')
    args=ap.parse_args()
    if args.sample:
        import kap_triage.sample as sample_data
        info=sample_data.ensure()
        if info:
            print(f'sample data built: {info["companies"]} companies, {info["disclosures"]} disclosures, {info["days"]} days',flush=True)
        chat.EXAMPLES=sample_data.CHAT_EXAMPLES  # the real examples name real companies
        chat.WINDOW_GUARD=False  # sample/data is not the nightly DB: no 23:40-23:50 block (all four checks use this switch)
        global SAMPLE
        SAMPLE=True
    if args.review_log:
        global LOG_PATH
        LOG_PATH=args.review_log
    if args.stats:
        print(' '.join(f'{k}={v}' for k,v in stats().items()))
        for code,c in reason_stats(load_reviews()).items():
            print(f'  {code} confirm={c["confirm"]} reject={c["reject"]}')
    elif args.serve:
        print(f'panel on http://127.0.0.1:{args.port} (bind {HOST}; Ctrl+C to stop); days={len(available_days())} sectors={len(load_sectors())} '
              f'review log={LOG_PATH}'+(' data=sample/data (made up)' if SAMPLE else ''))
        if SAMPLE:
            print(f'start here: http://127.0.0.1:{args.port}/genel',flush=True)
        import uvicorn
        from kap_triage.web.app import app
        uvicorn.run(app,host=HOST,port=args.port,log_level='warning',access_log=False)   # no request log
    else:
        ap.error('give --serve, --stats')


if __name__=='__main__':
    main()
