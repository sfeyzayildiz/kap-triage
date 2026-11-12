'''Desk panel: chat with the agent (start page) and the morning list per sector desk, with a human
confirm step for flagged items.

Local only (binds 127.0.0.1). Reads the saved morning list data/morning_<day>.jsonl (no LLM,
no network). Desk = Matriks sector of the symbol (table symbol_sectors), optionally grouped by
DESKS below ({"sector name": "desk name"}, filled after the sector load); no sector -> "Atanmamış".
Reviewer decisions for flagged items are appended to data/review_log.jsonl (not the DB, so the
panel never holds a DB lock the nightly job needs). Latest decision per news_id wins.
All text is HTML-escaped (KAP text is external input); KAP links are shown only for kap.org.tr.

Usage:
  python scripts/panel.py --self-test
  python scripts/panel.py --serve            # http://127.0.0.1:8765 (chat), /days (morning lists)
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
import form
import themes

DB_PATH='data/kap.duckdb'
DESKS={}  # sector name -> desk name; empty until the sector names are known
LOG_PATH='data/review_log.jsonl'
HOST='127.0.0.1'
PORT=8765
UNASSIGNED='Atanmamış'
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
        return {s:n for s,n in con.execute('SELECT symbol,sector_name FROM symbol_sectors').fetchall()}
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


CSS=''':root{--bg:#f3f5f8;--surface:#fff;--ink:#14213d;--muted:#5b6474;--line:#dde2ea;--brand:#0b1f3a;
--accent:#0f766e;--amber:#b45309;--red:#b91c1c;--green:#15803d;--tint-red:#fdf1f1;--tint-green:#eef8f1;--q:#e8f0fb}
@media (prefers-color-scheme: dark){:root{--bg:#0c121c;--surface:#141d2b;--ink:#e6ebf2;--muted:#9aa5b5;--line:#26324a;
--brand:#08111f;--accent:#2dd4bf;--amber:#f59e0b;--red:#f87171;--green:#4ade80;--tint-red:#2a1719;--tint-green:#13261b;--q:#1a2a42}}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:var(--bg);
color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.45}
header.top{background:var(--brand);border-bottom:3px solid var(--accent);padding:10px 16px}
.topin{max-width:980px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px 22px}
.brand{color:#fff;font-weight:700;letter-spacing:.02em}.brand span{color:var(--accent);margin-right:6px}
.brand small{color:#9fb0c6;font-weight:400;margin-left:8px}
nav a{color:#d3dce8;text-decoration:none;margin-right:16px;font-size:.95rem}nav a:hover{color:#fff;text-decoration:underline}
main{max-width:980px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:1.35rem;margin:6px 0 10px}
h2{font-size:.82rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:28px 0 8px;
padding-left:8px;border-left:3px solid var(--accent)}
a{color:var(--accent)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}
.flag{border-left:4px solid var(--red)}.high{border-left:4px solid var(--amber)}
.badge{display:inline-block;font-size:.75rem;font-weight:600;padding:1px 8px;border-radius:10px;border:1px solid var(--line);
color:var(--muted);margin-left:6px}.badge.high{color:var(--amber);border-color:var(--amber)}
.badge.flag{color:var(--red);border-color:var(--red)}a.badge{text-decoration:none}
.muted{color:var(--muted);font-size:.9rem}
.review{background:var(--tint-red);padding:8px;border-radius:6px;margin-top:6px}.done{background:var(--tint-green)}
button{font:inherit;background:var(--accent);color:#fff;border:0;border-radius:6px;padding:6px 12px;margin-right:6px;cursor:pointer}
input,select,textarea{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
input[type=text]{width:60%}
.choices{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin-top:12px}
.choice{display:flex;flex-direction:column;gap:4px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;color:var(--ink);text-decoration:none}
.choice:hover{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}.choice .ic{font-size:1.4rem;color:var(--accent)}
.choice.free{border-style:dashed}
form.guided{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:14px}
form.guided label{display:flex;flex-direction:column;font-size:.85rem;color:var(--muted);gap:4px}
form.guided .wide{grid-column:1/-1}form.guided input[type=text]{width:100%}form.guided button{justify-self:start}
@media (max-width:640px){form.guided{grid-template-columns:1fr}input[type=text]{width:100%}}'''+chat.CSS


def page(title,body):
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<style>{CSS}</style></head><body>{chat.HEADER}<main>{body}</main></body></html>')


def render_item(item,day,review):
    from morning import LEVEL_TR, REVIEW_TR, reaction_text, reason_text, tr_num
    imp=item['importance']
    cls='flag' if imp['needs_review'] else ('high' if imp['level']=='high' else '')
    badges=f'<span class="badge {"high" if imp["level"]=="high" else ""}">{e(LEVEL_TR.get(imp["level"],imp["level"]))} · skor {e(imp["score"])}</span>'
    if imp['needs_review']:
        badges+=(f'<a class="badge flag" href="#r{e(item["news_id"])}">kontrol et ↓</a>' if not review
                 else '<span class="badge flag">kontrol edildi</span>')
    from names import company_label
    out=[f'<div class="card {cls}"><b>{e(company_label(item["symbol"],short=True))}</b> '
         f'<span class="muted">{e(item["symbol"])}</span>{badges} · {kap_link(item.get("kap_url"))}']
    if item.get('amount') is not None:
        out.append(f'<div>Tutar: {e(tr_num(item["amount"],0))} {e(item.get("currency"))}</div>')
    reasons=[reason_text(r) for r in imp.get('reasons',[])]
    if reasons:
        out.append(f'<div>Neden: {e("; ".join(reasons))}</div>')
    if item.get('reaction'):
        out.append(f'<div class="muted">Fiyat: {e(reaction_text(item["reaction"]))}</div>')
    if imp['needs_review']:
        codes='; '.join(REVIEW_TR.get(c,c) for c in imp['needs_review_reasons'])
        if review:
            out.append(f'<div class="review done">Kontrol edildi: {e(DECISIONS[review["decision"]])} '
                       f'({e(review["at"])}){" - "+e(review["note"]) if review.get("note") else ""}</div>')
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


def render_day(day,items,sectors,desks,reviews):
    groups=by_desk(items,sectors,desks)
    flagged=[i for i in items if i['importance']['needs_review']]
    done=sum(i['news_id'] in reviews for i in flagged)
    body=[chat.NAV+f'<h1>Sabah listesi: {e(day)}</h1>',
          f'<p>{len(items)} bildirim, {len(groups)} masa; kontrol gereken {len(flagged)}, kontrol edilen {done}.</p>']
    if not items:
        body.append('<p>Bu gün yeni iş ilişkisi bildirimi yok.</p>')
    for desk,its in groups.items():
        body.append(f'<h2>{e(desk)} ({len(its)})</h2>')
        body+= [render_item(i,day,reviews.get(i['news_id'])) for i in its]
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
        sec=Counter(desk_of(a['symbol'],sectors,{}) for a in v['items'])
        notes.append('sektörler: '+', '.join(f'{s} {c}' for s,c in sec.most_common()))
        body.append(f'<p class="muted">{e("; ".join(notes))}</p><ul>')
        body+= [f'<li>{e(a["symbol"])} · {e(a["published_at"][:10])} · {kap_link(urls.get(a["news_id"]))}</li>'
                for a in v['items']]
        body.append('</ul>')
    body.append(f'<p class="muted">{e(THEME_LIMIT)}</p>')
    return page(f'Temalar {start}',''.join(body))


def load_day(day):
    from morning import load_saved
    return load_saved(day)


class Handler(BaseHTTPRequestHandler):
    def send(self,code,body,ctype='text/html; charset=utf-8',location=None):
        data=body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        if location:
            self.send_header('Location',location)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self,*args):  # no request lines (paths carry dates only, but keep stdout quiet)
        pass

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/':
            return self.send(200,page('KAP asistanı',chat.render_body(chat.HISTORY)))
        if path=='/days':
            return self.send(200,render_index(available_days()))
        m=re.match(r'^/day/(\d{4}-\d{2}-\d{2})$',path)
        if m:
            items=load_day(m.group(1))
            if items is None:
                return self.send(404,page('Yok','<p>Bu gün için sabah listesi yok.</p>'))
            return self.send(200,render_day(m.group(1),items,load_sectors(),DESKS,load_reviews()))
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
        if origin and urlparse(origin).hostname not in (HOST,'localhost'):
            return self.send(403,page('Hayır','<p>Yalnızca yerel istek.</p>'))
        path=urlparse(self.path).path
        if path not in ('/review','/chat','/chat/clear','/form'):
            return self.send(404,page('Yok','<p>Sayfa yok.</p>'))
        n=min(int(self.headers.get('Content-Length') or 0),4096)
        form_data={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode('utf-8')).items()}
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
    idx=render_themes_index([('2026-11-09',3)],'2026-11-12 08:00:00',2)
    assert 'href="/themes/2026-11-09"' in idx and 'Sonraki 2 bildirim henüz kümelenmedi' in idx
    assert 'clusters.json bulunamadı' in render_themes_index([],None,0)
    assert 'class="top"' in html_out and 'href="/form"' in html_out and '<main>' in html_out    # theme header on every page
    assert '<a class="badge flag" href="#r2">kontrol et ↓</a>' in html_out and 'id="r2"' in html_out and 'class="badge high">yüksek · skor 4' in html_out
    print('self-test ok: 26 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serve',action='store_true')
    ap.add_argument('--port',type=int,default=PORT)
    ap.add_argument('--stats',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    ap.add_argument('--review-log',help='another review log, e.g. data/review_log_test.jsonl for a clean test (the real log stays untouched)')
    args=ap.parse_args()
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
        print(f'panel on http://{HOST}:{args.port} (Ctrl+C to stop); days={len(available_days())} sectors={len(load_sectors())} '
              f'review log={LOG_PATH}')
        ThreadingHTTPServer((HOST,args.port),Handler).serve_forever()
    else:
        ap.error('give --serve, --stats or --self-test')


if __name__=='__main__':
    main()
