'''Desk panel: chat with the agent (start page) and the morning list per sector desk, with a human
confirm step for flagged items.

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
  5. web server: body_length, theme_back, Handler (do_GET routes, do_POST review / chat / form)
  6. _self_test: tests only, not needed to understand the panel; main: command line

Usage:
  python scripts/panel.py --self-test
  python scripts/panel.py --serve            # http://127.0.0.1:8765 (chat), /genel (overview), /days (morning lists)
  python scripts/panel.py --stats            # counts only: confirmed / rejected, overall and per reason code
'''
import argparse
import glob
import html
import json
import os
import re
from collections import Counter
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import chat
import demo_mode
import form
import reliability
import themes

DB_PATH='data/kap.duckdb'
DESKS={}  # sector name -> desk name; empty until the sector names are known
LOG_PATH='data/review_log.jsonl'
# bind address: 127.0.0.1 on the Mac; the Docker image sets PANEL_HOST=0.0.0.0 and compose publishes
# the port on 127.0.0.1 only, so the panel stays local either way (docs/docker.md)
HOST=os.environ.get('PANEL_HOST','127.0.0.1')
LOCAL_NAMES=('127.0.0.1','localhost')  # accepted Origin / Referer hosts
PORT=8765
UNASSIGNED='Atanmamış'
SAMPLE=False  # --sample: made-up data in sample/data/ (scripts/sample_data.py); every page says so
SAMPLE_BANNER=('<div class="card high"><b>Örnek veri.</b> Şirketler, bildirimler, tutarlar, sektörler ve fiyatlar '
               'uydurmadır; gerçek veri lisans gereği paylaşılmaz. Sabah listeleri gerçek gece zinciriyle üretildi, '
               'yalnızca model cevapları önceden yazıldı. KAP linkleri gerçek bir bildirime gitmez. Sohbet, konu araması '
               've bildirim kartı yerel Ollama ve embedding modeli ister; diğer sayfalar modelsiz çalışır. '
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
    from morning import priority
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
    days=[os.path.basename(p)[len('morning_'):-len('.jsonl')] for p in glob.glob('data/morning_*.jsonl')]
    return sorted((d for d in days if DAY_RE.match(d)),reverse=True)


def kap_link(url):
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">KAP</a>' if url and KAP_RE.match(url) \
        else f'<span class="muted">KAP linki geçersiz: {e(url)}</span>'


# dark tokens: used by the system setting (unless the analyst chose light) and by the theme switch (/tema, a cookie)
DARK=('--bg:#0c121c;--surface:#141d2b;--ink:#e6ebf2;--muted:#9aa5b5;--line:#26324a;--brand:#08111f;--accent:#2dd4bf;'
      '--amber:#f59e0b;--red:#f87171;--green:#4ade80;--tint-red:#2a1719;--tint-green:#13261b;--q:#1a2a42;color-scheme:dark')
THEMES=('auto','dark','light')  # the switch cycles in this order
CSS=''':root{--bg:#f3f5f8;--surface:#fff;--ink:#14213d;--muted:#5b6474;--line:#dde2ea;--brand:#0b1f3a;
--accent:#0f766e;--amber:#b45309;--red:#b91c1c;--green:#15803d;--tint-red:#fdf1f1;--tint-green:#eef8f1;--q:#e8f0fb}
@media (prefers-color-scheme: dark){:root:not([data-theme=light]){'''+DARK+'''}}
:root[data-theme=dark]{'''+DARK+'''}
:root[data-theme=light]{color-scheme:light}
nav a.theme{font-size:1.1rem;margin-left:4px}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:var(--bg);
color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.45}
header.top{background:var(--brand);border-bottom:3px solid var(--accent);padding:10px 16px}
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
.flag{border-left:4px solid var(--red)}.high{border-left:4px solid var(--amber)}
.badge{display:inline-block;font-size:.75rem;font-weight:600;padding:1px 8px;border-radius:10px;border:1px solid var(--line);
color:var(--muted);margin-left:6px}.badge.high{color:var(--amber);border-color:var(--amber)}
.badge.flag{color:var(--red);border-color:var(--red)}.badge.done{color:var(--green);border-color:var(--green)}a.badge{text-decoration:none}
.muted{color:var(--muted);font-size:.9rem}
.review{background:var(--tint-red);padding:8px;border-radius:6px;margin-top:6px}.done{background:var(--tint-green)}
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
@media (max-width:640px){form.guided{grid-template-columns:1fr}input[type=text]{width:100%}}'''+chat.CSS+reliability.CSS


def page(title,body,extra_css=''):
    '''extra_css: styles only one page needs (the overview charts), so the other pages stay byte-identical.'''
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<style>{CSS}{extra_css}</style></head><body>{chat.HEADER}<main>{demo_mode.BANNER if demo_mode.ON else ""}'
            f'{SAMPLE_BANNER if SAMPLE else ""}{body}</main></body></html>')


WINDOW_MSG='Gece toplama penceresi (23:40-23:50): veritabanına dokunulmuyor. 23:50\'den sonra tekrar deneyin.'


def reads_db(path,query=''):
    '''GET routes that open the DB (day page: sectors, prices, source sentences; desks JSON: sectors;
    form step 2 with a company: symbols; themes: counts, sectors, links).'''
    if re.match(r'^/(day|api/desks)/',path) or path=='/themes' or path.startswith('/themes/'):
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
    from source_check import source_sentence
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


def render_item(item,day,review,chart='',source=None):
    from morning import LEVEL_TR, REVIEW_TR, reaction_text, reason_text, tr_num
    imp=item['importance']
    cls='flag' if imp['needs_review'] else ('high' if imp['level']=='high' else '')
    score='' if demo_mode.ON else f' · skor {e(imp["score"])}'  # demo: the score sums Matriks-based points
    badges=f'<span class="badge {"high" if imp["level"]=="high" else ""}">{e(LEVEL_TR.get(imp["level"],imp["level"]))}{score}</span>'
    if imp['needs_review']:
        badges+=(f'<a class="badge flag" href="#r{e(item["news_id"])}">kontrol et ↓</a>' if not review
                 else '<span class="badge done">kontrol edildi ✓</span>')
    from names import company_label
    out=[f'<div class="card {cls}" id="c{e(item["news_id"])}"><b>{e(company_label(item["symbol"],short=True))}</b> '
         f'<span class="muted">{e(item["symbol"])}</span>{badges} · {kap_link(item.get("kap_url"))}']
    if item.get('amount') is not None:
        out.append(f'<div>Tutar: {e(tr_num(item["amount"],0))} {e(item.get("currency"))}</div>')
        out.append(source_html(source))
    reasons=[reason_text(r) for r in imp.get('reasons',[])]
    if demo_mode.ON:
        reasons=demo_mode.reasons(reasons)
    if reasons:
        out.append(f'<div>Neden: {e("; ".join(reasons))}</div>')
    if item.get('reaction'):
        out.append(f'<div class="muted">Fiyat: {e(demo_mode.PLACEHOLDER if demo_mode.ON else reaction_text(item["reaction"]))}</div>')
    out.append('' if demo_mode.ON else (chart or ''))  # built by price_chart from numbers only (Matriks prices)
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
    out.append('</div>')
    return ''.join(out)


LOOK_FIRST_MAX=3


def look_first_box(items,reviews,base=''):
    '''"Önce bak": up to 3 look-first items (high or flagged) in the morning list's order, each with its reasons
    through the same path as the cards (demo mode hides Matriks-based reasons there too) and a link to its card.
    base: the day page's address when the box is shown elsewhere (overview); '' on the day page itself.'''
    from morning import REVIEW_TR, priority, reason_text
    from names import company_label
    look=sorted([i for i in items if i['importance']['needs_review'] or i['importance']['level']=='high'],key=priority)
    if not look:
        return ''
    rows=[]
    for i in look[:LOOK_FIRST_MAX]:
        imp=i['importance']
        why=[reason_text(r) for r in imp.get('reasons',[])]
        if demo_mode.ON:
            why=demo_mode.reasons(why)
        if imp['needs_review'] and i['news_id'] not in reviews:
            why=['kontrol et: '+', '.join(REVIEW_TR.get(c,c) for c in imp['needs_review_reasons'])]+why
        rows.append(f'<li><a href="{e(base)}#c{e(i["news_id"])}"><b>{e(company_label(i["symbol"],short=True))}</b></a> '
                    f'<span class="muted">{e(i["symbol"])}</span>: {e("; ".join(why) or "yüksek önem")}</li>')
    more=f'<p class="muted">ve {len(look)-LOOK_FIRST_MAX} bildirim daha (aşağıda)</p>' if len(look)>LOOK_FIRST_MAX else ''
    return f'<div class="card high look"><b>Önce bak ({len(look)})</b><ol>{"".join(rows)}</ol>{more}</div>'


def render_day(day,items,sectors,desks,reviews,charts=None,sources=None):
    if demo_mode.ON:
        desks=demo_mode.desk_map(sectors,desks)  # "Masa N", never the sector name
    groups=by_desk(items,sectors,desks)
    flagged=[i for i in items if i['importance']['needs_review']]
    done=sum(i['news_id'] in reviews for i in flagged)
    body=[chat.NAV+f'<h1>Sabah listesi: {e(day)}</h1>',
          f'<p>{len(items)} bildirim, {len(groups)} masa; kontrol gereken {len(flagged)}, kontrol edilen {done}.</p>']
    if not items:
        body.append('<p>Bu gün yeni iş ilişkisi bildirimi yok.</p>')
    body.append(look_first_box(items,reviews))
    for desk,its in groups.items():
        body.append(f'<h2>{e(desk)} ({len(its)})</h2>')
        body+= [render_item(i,day,reviews.get(i['news_id']),(charts or {}).get(i['news_id'],''),(sources or {}).get(i['news_id']))
                for i in its]
    body.append('<p class="muted">Kaynak: KAP bildirimleri ve Matriks verisi. Skor kurallı bir sıralamadır, tahmin değildir; '
                'karar öncesi KAP metnini okuyun.</p>')
    return page(f'Sabah listesi {day}',''.join(body))


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
        if demo_mode.ON:  # same desk numbers as the day pages
            sec=Counter(desk_of(a['symbol'],sectors,demo_mode.desk_map(sectors,DESKS)) for a in v['items'])
            notes.append('masalar: '+', '.join(f'{s} ({c})' for s,c in sorted(sec.items(),key=lambda sc:(-sc[1],sc[0]==UNASSIGNED,sc[0]))))
        else:
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
EXTRA_CODES={'unknown_item':'bildirim o günün listesinde yok','not_flagged_after_rebuild':'liste yeniden kurulunca işaret kalktı',
             'no_reason_stored':'gerekçe kaydedilmemiş'}
DECISION_SHORT={'confirm':'Doğru','reject':'Yanlış (çıkarım hatalı)'}
REVIEW_NOTE=('Doğru: analist KAP metnine baktı, çıkarılan değerler doğruydu (işaret gereksiz alarmdı). Yanlış: çıkarım '
             'hatalıydı (işaret gerçek bir hatayı yakaladı). Bir bildirimde birden çok işaret olabilir; türlere göre sayıların '
             'toplamı karar sayısını geçebilir. Bu sayılar analistin geri bildirimidir, önceden yazılmış bir kuralla yapılmış '
             'kör bir ölçüm değildir.')


def code_text(code):
    from morning import REVIEW_TR
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
    from names import company_label
    body=[chat.NAV,'<h1>Kontrol geçmişi</h1>',review_summary(rows)]
    if rows:
        body.append('<h2>İşaret türüne göre</h2>'+flag_chart(rstats))
        trs=[]
        for r,item in rows:
            codes=r['reasons'] if 'reasons' in r else (item['importance']['needs_review_reasons'] if item else [])
            who=(f'{e(company_label(item["symbol"],short=True))} <span class="muted">{e(item["symbol"])}</span>' if item
                 else '<span class="muted">listede yok</span>')
            note=(demo_mode.PLACEHOLDER if r.get('note') else '') if demo_mode.ON else r.get('note') or ''  # free text
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


def render_overview(stats,last_items,reviews,rows,rstats):
    '''One scrolling page in layers; every layer links to its detail page.'''
    days=sorted(stats,reverse=True)
    body=[chat.NAV,'<h1>Genel bakış</h1>',
          '<p class="muted">Yeni iş ilişkisi bildirimleri gece okunur, sabah önem sırasıyla listelenir; şüpheli çıkarımlar '
          '"kontrol et" ile analiste gider. Bu sayfa özet; her bölümün ayrıntısı kendi sayfasında.</p>']
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
    return page('Genel bakış',''.join(body),OVERVIEW_CSS)


def load_day(day):
    from morning import load_saved
    return load_saved(day)


MAX_BODY=4096


def body_length(value):
    '''Content-Length clamped to 0..MAX_BODY; None for a value that is not a number (the request is refused).'''
    try:
        return max(0,min(int(value or 0),MAX_BODY))
    except ValueError:
        return None


def theme_back(referer):
    '''Where the theme switch returns: a local page of this panel, never another site (a "//host" path is one).'''
    ref=urlparse(referer or '')
    if ref.hostname in LOCAL_NAMES and ref.path.startswith('/') and not ref.path.startswith('//'):
        return ref.path+('?'+ref.query if ref.query and ref.path=='/form' else '')
    return '/'


class Handler(BaseHTTPRequestHandler):
    def theme(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k,_,v=part.strip().partition('=')
            if k=='theme' and v in THEMES:
                return v
        return 'auto'

    def send(self,code,body,ctype='text/html; charset=utf-8',location=None,cookie=None):
        t=self.theme()
        if t!='auto':
            body=body.replace('<html lang="tr">',f'<html lang="tr" data-theme="{t}">',1)
        data=body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        if location:
            self.send_header('Location',location)
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self,*args):  # no request lines (paths carry dates only, but keep stdout quiet)
        pass

    def do_GET(self):
        path=urlparse(self.path).path
        blocked=window_block(path,urlparse(self.path).query,datetime.now())
        if blocked:
            return self.send(*blocked)
        if path=='/':
            return self.send(200,page('KAP asistanı',chat.render_body(chat.HISTORY)))
        if path=='/days':
            return self.send(200,render_index(available_days()))
        if path in ('/genel','/kontroller'):  # saved lists + review log only (no DB read, so no night-window block)
            reviews=load_reviews()
            rows=review_rows(reviews)
            rstats=reason_stats(reviews)
            if path=='/kontroller':
                return self.send(200,render_reviews(rows,rstats))
            days=available_days()
            return self.send(200,render_overview(all_day_stats(days,reviews),(load_day(days[0]) or []) if days else [],
                                                 reviews,rows,rstats))
        m=re.match(r'^/day/(\d{4}-\d{2}-\d{2})$',path)
        if m:
            items=load_day(m.group(1))
            if items is None:
                return self.send(404,page('Yok','<p>Bu gün için sabah listesi yok.</p>'))
            from price_chart import charts_for_items
            charts={} if demo_mode.ON else charts_for_items(items)  # demo: prices are not even read
            return self.send(200,render_day(m.group(1),items,load_sectors(),DESKS,load_reviews(),charts,
                                            sources_for_items(items)))
        m=re.match(r'^/api/desks/(\d{4}-\d{2}-\d{2}|latest)$',path)
        if m:  # docs/n8n_routing_rule.md: read-only JSON for n8n (no amounts, no disclosure text)
            day=m.group(1)
            if day=='latest':
                days=available_days()
                day=days[0] if days else None
            items=load_day(day) if day else None
            if items is None:
                return self.send(404,json.dumps({'error':'no morning list','day':day}),ctype='application/json')
            import desk_mail
            return self.send(200,json.dumps(desk_mail.payload(day,items,load_sectors(),DESKS),ensure_ascii=False),
                             ctype='application/json; charset=utf-8')
        if path=='/tema':  # theme switch without JavaScript: next theme in a cookie, back to the same page
            nxt=THEMES[(THEMES.index(self.theme())+1)%len(THEMES)]
            back=theme_back(self.headers.get('Referer'))
            age=0 if nxt=='auto' else 31536000
            return self.send(303,'',location=back,cookie=f'theme={nxt}; Path=/; Max-Age={age}; SameSite=Strict')
        if path=='/guvenilirlik':
            return self.send(200,page('Güvenilirlik',reliability.render_body(chat.NAV)))
        if path=='/form':
            kind=(parse_qs(urlparse(self.path).query).get('type') or [None])[0]
            kind=kind if kind in form.TYPES else None  # unknown type -> step 1
            symbols=load_symbols() if kind and 'symbol' in form.FIELDS[kind] else set()
            return self.send(200,page('Rehberli sorgu',form.render_body(symbols,form.display_names(),form.LAST,
                                                                        chat.NAV,chat.render_answer,kind=kind)))
        if path=='/themes':
            out=themes.load_clusters()
            if out is None:
                return self.send(200,render_themes_index([],None,0))
            last=themes.last_clustered(out['assign'])
            return self.send(200,render_themes_index(themes.weeks(out['assign']),last,themes.count_after(last)))
        m=re.match(r'^/themes/(\d{4}-\d{2}-\d{2})$',path)
        if m:
            out=themes.load_clusters()
            try:
                start=date.fromisoformat(m.group(1))
            except ValueError:
                start=None
            if out is None or start is None or themes.week_start(start)!=start:
                return self.send(404,page('Yok','<p>Bu hafta yok (hafta pazartesi ile başlar).</p>'))
            view=themes.week_view(out,start)
            urls=themes.load_meta([a['news_id'] for v in view for a in v['items']])
            return self.send(200,render_week(str(start),view,load_sectors(),urls))
        self.send(404,page('Yok','<p>Sayfa yok.</p>'))

    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).hostname not in LOCAL_NAMES:
            return self.send(403,page('Hayır','<p>Yalnızca yerel istek.</p>'))
        path=urlparse(self.path).path
        if path not in ('/review','/chat','/chat/clear','/form'):
            return self.send(404,page('Yok','<p>Sayfa yok.</p>'))
        n=body_length(self.headers.get('Content-Length'))
        if n is None:
            return self.send(400,page('Hata','<p>Geçersiz istek.</p>'))
        form_data={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode('utf-8',errors='replace')).items()}
        if path=='/chat/clear':
            chat.HISTORY.clear()
            return self.send(303,'',location='/')
        if path=='/form':
            from agent import load_context
            try:
                ctx=None if chat.in_collection_window(datetime.now()) else load_context()  # no DB read in the window
                rec=form.run(form_data,ctx)
            except Exception as ex:  # DB missing or locked: show the type, keep the page alive
                rec={'form':{k:form_data.get(k,'') for k in ('type','symbol','day','text')},'seconds':0.0,'error':True,
                     'at':datetime.now().strftime('%H:%M'),'answer':f'Veritabanı okunamadı ({type(ex).__name__}).'}
                form.LAST.clear()
                form.LAST.update(rec)
            print(f'form: type={rec["form"]["type"]} seconds={rec["seconds"]} error={rec["error"]}',flush=True)  # no text
            kind=rec['form'].get('type')
            return self.send(303,'',location=f'/form?type={kind}#son' if kind in form.TYPES else '/form')
        if path=='/chat':
            q=(form_data.get('q') or '').strip()
            if not q or len(q)>chat.MAX_QUESTION:
                return self.send(400,page('Hata','<p>Soru boş ya da çok uzun.</p>'))
            rec=chat.ask(q)
            print(f'chat: intent={rec["intent"]} seconds={rec["seconds"]} error={rec["error"]}',flush=True)  # no text
            return self.send(303,'',location='/#son')
        day=form_data.get('day','')
        if not DAY_RE.match(day) or form_data.get('decision') not in DECISIONS or not form_data.get('news_id'):
            return self.send(400,page('Hata','<p>Geçersiz istek.</p>'))
        flagged={i['news_id']:i for i in (load_day(day) or []) if i['importance']['needs_review']}
        if form_data['news_id'] not in flagged:
            return self.send(400,page('Hata','<p>Bu bildirim o günün kontrol listesinde yok.</p>'))
        record_review(form_data['news_id'],day,form_data['decision'],form_data.get('note'),
                      reasons=flagged[form_data['news_id']]['importance']['needs_review_reasons'])
        self.send(303,'',location=f'/day/{day}')


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


def _self_test():
    import tempfile
    imp=lambda score,level,flag:{'score':score,'level':level,'needs_review':bool(flag),'needs_review_reasons':flag,
                                 'reasons':[{'code':'foreign_currency','currency':'USD','points':1}]}
    items=[{'news_id':'1','symbol':'AAA','kap_url':'https://www.kap.org.tr/tr/Bildirim/1','amount':1500000.0,'currency':'USD',
            'importance':imp(4,'high',[])},
           {'news_id':'2','symbol':'BBB','kap_url':'javascript:alert(1)','amount':None,
            'importance':imp(0,'low',['amount_not_in_text'])},
           {'news_id':'3','symbol':'<script>','kap_url':'https://kap.org.tr/x','amount':None,'importance':imp(1,'low',[])},
           {'news_id':'4','symbol':'CCC','kap_url':'https://www.kap.org.tr/tr/Bildirim/4','amount':None,
            'importance':imp(1,'low',[])}]
    sectors={'AAA':'Savunma','BBB':'Enerji','CCC':'Savunma'}
    assert desk_of('AAA',sectors,{})=='Savunma' and desk_of('ZZZ',sectors,{})==UNASSIGNED
    assert pretty_sector('GIDA , İÇECEK VE TÜTÜN')=='Gıda, İçecek ve Tütün'
    assert pretty_sector('METAL ESYA,MAKİNE,ELEKTRİKLİ CİHAZLAR,ULASIM ARAÇ')=='Metal Eşya, Makine, Elektrikli Cihazlar, Ulaşım Araç'
    assert pretty_sector('TEKNOLOJİ - BİLİŞİM')=='Teknoloji - Bilişim' and pretty_sector('İNŞAAT-TAAHHÜT')=='İnşaat - Taahhüt' and pretty_sector(None) is None
    assert pretty_sector('TAS VE TOPRAĞA DAYALI')=='Taş ve Toprağa Dayalı'   # display only; mailbox unchanged (tas-ve-...)
    assert desk_of('BBB',sectors,{'Enerji':'Enerji ve altyapı'})=='Enerji ve altyapı'
    g=by_desk(items,sectors,{})
    assert list(g)==['Enerji','Savunma',UNASSIGNED]  # ties on look-first broken by name, unassigned last
    assert [i['symbol'] for i in g['Savunma']]==['AAA','CCC']
    html_out=render_day('2026-11-09',items,sectors,{},{})
    assert '<script>' not in html_out and '&lt;script&gt;' in html_out          # escaped
    assert 'href="javascript' not in html_out and 'KAP linki geçersiz' in html_out
    assert '4 bildirim, 3 masa; kontrol gereken 1, kontrol edilen 0.' in html_out
    assert 'KONTROL ET:</b> tutar metinde geçmiyor' in html_out and 'name="decision" value="confirm"' in html_out
    with tempfile.TemporaryDirectory() as d:
        log=os.path.join(d,'r.jsonl')
        record_review('2','2026-11-09','reject','x',path=log,now=datetime(2026,11,10,9))
        record_review('2','2026-11-09','confirm','',path=log,now=datetime(2026,11,10,10))
        rv=load_reviews(log)
        assert rv['2']['decision']=='confirm' and stats(log)=={'reviewed':1,'confirm':1,'reject':0}
        rs=reason_stats({**rv,'9':{'news_id':'9','day':'2026-11-09','decision':'reject'}},load=lambda d:items)
        assert rs=={'amount_not_in_text':{'confirm':1,'reject':0},'unknown_item':{'confirm':0,'reject':1}}
        stored=record_review('4','2026-11-09','reject','',path=log,reasons=['currency_unclear'])
        rs2=reason_stats({'4':stored,'1':{'news_id':'1','day':'2026-11-09','decision':'confirm'}},load=lambda d:items)
        assert rs2=={'currency_unclear':{'confirm':0,'reject':1},'not_flagged_after_rebuild':{'confirm':1,'reject':0}}
        try:
            record_review('2','2026-11-09','maybe',None,path=log)
            raise AssertionError('bad decision accepted')
        except ValueError:
            pass
        out=render_day('2026-11-09',items,sectors,{},rv)
        assert 'kontrol edilen 1' in out and 'Kontrol edildi: Doğru' in out and 'name="decision"' not in out
    assert 'Kayıtlı sabah listesi yok.' in render_index([]) and 'href="/days"' in render_index([])
    assert 'Bu gün yeni iş ilişkisi bildirimi yok.' in render_day('2026-11-01',[],{},{},{})
    assert 'href="/themes"' in render_index([]) and 'href="/themes"' in render_day('2026-11-01',[],{},{},{})

    view=[{'cluster':1,'n':2,'words':[],'companies_week':1,'companies_all':1,'avg_per_week':0.25,'ratio':8.0,
           'items':[{'news_id':'4','symbol':'<b>','published_at':'2026-11-11 09:00:00'},
                    {'news_id':'5','symbol':'CCC','published_at':'2026-11-12 08:00:00'}]},
          {'cluster':0,'n':1,'words':['savunma','<i>x'],'companies_week':1,'companies_all':9,'avg_per_week':1.5,'ratio':0.7,
           'items':[{'news_id':'3','symbol':'AAA','published_at':'2026-11-10 09:00:00'}]}]
    w=render_week('2026-11-09',view,sectors,{'4':'javascript:alert(1)','5':'https://www.kap.org.tr/tr/Bildirim/5'})
    assert '3 bildirim, 2 tema.' in w and '<b>' not in w and '<i>' not in w and '&lt;i&gt;x' in w   # escaped
    assert 'href="javascript' not in w and 'href="https://www.kap.org.tr/tr/Bildirim/5"' in w
    assert w.count('şablon etkisi')==1 and 'normalde haftada 0,2 bildirim' in w and 'sektörler: Savunma 1' in w
    assert 'tema kelimesi yok' in w and 'kısmen yansıtır' in w
    assert '<figure class="chart">X</figure>' in render_day('2026-11-09',items,sectors,{},{},charts={'1':'<figure class="chart">X</figure>'})
    idx=render_themes_index([('2026-11-09',3)],'2026-11-12 08:00:00',2)
    assert 'href="/themes/2026-11-09"' in idx and 'Sonraki 2 bildirim henüz kümelenmedi' in idx
    assert 'clusters.json bulunamadı' in render_themes_index([],None,0)
    assert 'class="top"' in html_out and 'href="/form"' in html_out and '<main>' in html_out    # theme header on every page
    assert '<a class="badge flag" href="#r2">kontrol et ↓</a>' in html_out and 'id="r2"' in html_out and 'class="badge high">yüksek · skor 4' in html_out
    assert ':root[data-theme=dark]{' in CSS and ':root:not([data-theme=light])' in CSS and 'href="/tema"' in render_index([])
    # source sentence: verbatim, escaped, amount marked; missing -> stated, never invented; not read -> nothing
    src=source_html(('<b>X</b> ile 12.500.000 TL bedelli sözleşme.',[(13,23)]))
    assert src=='<div class="src">Kaynak cümle: “&lt;b&gt;X&lt;/b&gt; ile <mark>12.500.000</mark> TL bedelli sözleşme.”</div>'
    assert 'aynen geçmiyor' in source_html((None,[])) and source_html(None)==''
    assert 'Kaynak cümle: “a <mark>5</mark>”' in render_day('2026-11-09',[dict(items[0],amount=5.0)],sectors,{},{},sources={items[0]['news_id']:('a 5',[(2,3)])})
    assert sources_for_items([{'news_id':'1','amount':None}])=={} and sources_for_items([dict(items[0],amount=1.0)],db='/nonexistent.duckdb')=={}
    # C6: nightly window blocks every DB-reading GET route (503, no DB read); other pages and other times are untouched
    at=lambda h,m:datetime(2026,11,20,h,m)
    sym_kind=next(k for k in form.TYPES if 'symbol' in form.FIELDS[k])
    db_routes=[('/day/2026-11-09',''),('/api/desks/latest',''),('/themes',''),('/themes/2026-11-09',''),('/form',f'type={sym_kind}')]
    free_routes=[('/',''),('/days',''),('/guvenilirlik',''),('/form',''),('/tema',''),('/nope','')]
    for t in (at(23,40),at(23,45),at(23,50)):
        assert all(window_block(p,q,t) and window_block(p,q,t)[0]==503 for p,q in db_routes)
        assert all(window_block(p,q,t) is None for p,q in free_routes)
    assert all(window_block(p,q,t) is None for p,q in db_routes for t in (at(23,39),at(23,51),at(7,30)))
    assert '23:50' in window_block('/day/2026-11-09','',at(23,45))[1] and window_block('/api/desks/latest','',at(23,45))[2].startswith('application/json')
    # UI polish 19 Nov: Turkish review time, green "kontrol edildi"
    assert tr_time('2026-11-10T00:41:50')=='10 Kas 2026 00:41' and tr_time('x')=='x'
    assert '.badge.done{color:var(--green)' in CSS
    # "Önce bak" box: look-first items (high or flagged) in priority order, linked to their cards
    box=look_first_box(items,{})
    assert 'Önce bak (2)' in box and box.index('href="#c1"')>=0 and 'href="#c2"' in box and 'href="#c4"' not in box
    assert 'kontrol et:' in box and look_first_box([items[3]],{})=='' and 'id="c1"' in render_day('2026-11-09',items,sectors,{},{})
    # overview and review history (22 Nov): counts, column chart, flag chart, decisions table, demo hides notes
    c=day_counts(items,{'2':{}})
    assert c=={'n':4,'look':2,'flagged':1,'done':1}
    dstats=all_day_stats(['2026-11-09','2026-11-10'],{},load=lambda d:items if d=='2026-11-09' else [])
    ch=column_chart(dstats)
    assert ch.count('<a class="col"')==2 and 'href="/day/2026-11-09"' in ch and 'class="seg flag" style="flex:1"' in ch
    assert 'class="seg look" style="flex:1"' in ch and 'class="seg other" style="flex:2"' in ch and 'style="height:0%"' in ch
    assert '9 Kas 2026: 4 bildirim · önce bak 2 · kontrol et 1 (kontrol edilen 0)' in ch and column_chart({})==''
    many=column_chart({f'2026-10-{d:02d}':{'n':1,'look':0,'flagged':0,'done':0} for d in range(1,32)})
    assert many.count('<a class="col"')==CHART_DAYS and 'href="/day/2026-10-01"' not in many   # last 30 only
    rlog={'2':{'news_id':'2','day':'2026-11-09','decision':'reject','note':'<b>not</b>','at':'2026-11-10T09:00:00',
               'reasons':['amount_not_in_text']},
          '9':{'news_id':'9','day':'2026-11-09','decision':'confirm','note':'','at':'2026-11-10T10:00:00','reasons':[]}}
    rows=review_rows(rlog,load=lambda d:items)
    assert [r['news_id'] for r,_ in rows]==['9','2'] and rows[0][1] is None and rows[1][1]['symbol']=='BBB'
    rs=reason_stats(rlog,load=lambda d:items)
    fc=flag_chart(rs)
    assert 'tutar metinde geçmiyor' in fc and '1 hata · 0 doğru' in fc and 'gerekçe kaydedilmemiş' in fc and flag_chart({})==''
    rv=render_reviews(rows,rs)
    assert '2 karar: 1 bildirimde çıkarım hatalıydı' in rv and 'href="/day/2026-11-09#c2"' in rv and 'listede yok' in rv
    assert '&lt;b&gt;not&lt;/b&gt;' in rv and '<b>not</b>' not in rv and 'Yanlış (çıkarım hatalı)' in rv and '.hbar{' in rv
    saved_demo=demo_mode.ON
    try:
        demo_mode.ON=True
        assert 'not&lt;' not in render_reviews(rows,rs) and demo_mode.PLACEHOLDER in render_reviews(rows,rs)
    finally:
        demo_mode.ON=saved_demo
    assert 'Henüz kontrol kararı yok' in render_reviews([],{})
    ov=render_overview(dstats,items,{},rows,rs)
    assert all(f'<h2>{n}.' in ov for n in range(1,7)) and 'href="/day/2026-11-10"' in ov and 'href="/day/2026-11-10#c1"' in ov
    assert 'href="/kontroller"' in ov and 'href="/guvenilirlik"' in ov and ov.count('<div class="tile">')==7
    assert 'Kayıtlı sabah listesi yok' in render_overview({},[],{},[],{}) and '<h2>6.' not in render_overview({},[],{},[],{})
    assert '.cols{' not in render_index([]) and not reads_db('/genel') and not reads_db('/kontroller')   # other pages: no chart CSS
    # outside review 22 Nov: request hardening
    assert body_length('120')==120 and body_length(None)==0 and body_length('-1')==0 and body_length('99999')==MAX_BODY
    assert body_length('abc') is None
    assert theme_back('http://127.0.0.1:8765/day/2026-11-09')=='/day/2026-11-09' and theme_back('http://localhost//evil.example')=='/'
    assert theme_back('http://evil.example/day/x')=='/' and theme_back('http://localhost:8765/form?type=brief')=='/form?type=brief'
    assert theme_back(None)=='/' and theme_back('http://localhost:8765/days?x=1')=='/days'
    assert 'şükrü'.encode('utf-8')[:-1].decode('utf-8',errors='replace').startswith('şükr')   # a cut character no longer raises
    print('self-test ok: 70 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serve',action='store_true')
    ap.add_argument('--port',type=int,default=PORT)
    ap.add_argument('--stats',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--review-log',help='another review log, e.g. data/review_log_test.jsonl for a clean test (the real log stays untouched)')
    ap.add_argument('--demo',action='store_true',help='demo mode: hide Matriks-licensed values on every page (docs/demo_mode_rule.md)')
    ap.add_argument('--sample',action='store_true',
                    help='made-up sample data: sample/data/ instead of data/ (built if missing; no licence, no Ollama for the list pages)')
    args=ap.parse_args()
    if args.demo:
        demo_mode.ON=True
    if args.sample:  # every module reads data/... relative to the working directory, so data/ now means sample/data/
        import sample_data
        info=sample_data.ensure()
        if info:
            print(f'sample data built: {info["companies"]} companies, {info["disclosures"]} disclosures, {info["days"]} days',flush=True)
        os.chdir(sample_data.SAMPLE_ROOT)
        chat.EXAMPLES=sample_data.CHAT_EXAMPLES  # the real examples name real companies
        global SAMPLE
        SAMPLE=True
    if args.review_log:
        global LOG_PATH
        LOG_PATH=args.review_log
    if args.self_test:
        _self_test()
    elif args.stats:
        print(' '.join(f'{k}={v}' for k,v in stats().items()))
        for code,c in reason_stats(load_reviews()).items():
            print(f'  {code} confirm={c["confirm"]} reject={c["reject"]}')
    elif args.serve:
        print(f'panel on http://127.0.0.1:{args.port} (bind {HOST}; Ctrl+C to stop); days={len(available_days())} sectors={len(load_sectors())} '
              f'review log={LOG_PATH} demo={"on" if demo_mode.ON else "off"}'+(' data=sample/data (made up)' if SAMPLE else ''))
        if SAMPLE:
            print(f'start here: http://127.0.0.1:{args.port}/genel',flush=True)
        ThreadingHTTPServer((HOST,args.port),Handler).serve_forever()
    else:
        ap.error('give --serve, --stats or --self-test')


if __name__=='__main__':
    main()
