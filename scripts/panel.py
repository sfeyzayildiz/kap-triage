'''Desk panel: the morning list per sector desk, with a human confirm step for flagged items.

Local only (binds 127.0.0.1). Reads the saved morning list data/morning_<day>.jsonl (no LLM,
no network). Desk = Matriks sector of the symbol (table symbol_sectors), optionally grouped by
DESKS below ({"sector name": "desk name"}, filled after the sector load); no sector -> "Atanmamış".
Reviewer decisions for flagged items are appended to data/review_log.jsonl (not the DB, so the
panel never holds a DB lock the nightly job needs). Latest decision per news_id wins.
All text is HTML-escaped (KAP text is external input); KAP links are shown only for kap.org.tr.

Usage:
  python scripts/panel.py --self-test
  python scripts/panel.py --serve            # http://127.0.0.1:8765
  python scripts/panel.py --stats            # counts only: confirmed / rejected, overall and per reason code
'''
import argparse
import glob
import html
import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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


def load_reviews(path=LOG_PATH):
    '''news_id -> latest decision record.'''
    out={}
    if path and os.path.exists(path):
        with open(path,encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r=json.loads(line)
                    out[r['news_id']]=r
    return out


def record_review(news_id,day,decision,note,path=LOG_PATH,now=None):
    if decision not in DECISIONS:
        raise ValueError('decision')
    r={'news_id':str(news_id),'day':day,'decision':decision,'note':(note or '')[:500],
       'at':(now or datetime.now()).isoformat(timespec='seconds')}
    with open(path,'a',encoding='utf-8') as f:
        f.write(json.dumps(r,ensure_ascii=False)+'\n')
    return r


def available_days():
    days=[os.path.basename(p)[len('morning_'):-len('.jsonl')] for p in glob.glob('data/morning_*.jsonl')]
    return sorted((d for d in days if DAY_RE.match(d)),reverse=True)


def kap_link(url):
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">KAP</a>' if url and KAP_RE.match(url) \
        else f'<span class="muted">KAP linki geçersiz: {e(url)}</span>'


CSS='''body{font-family:system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px;color:#1a1a1a;background:#fafafa}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:28px;border-bottom:1px solid #ccc;padding-bottom:4px}
.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px 14px;margin:10px 0}
.flag{border-left:5px solid #c62828}.high{border-left:5px solid #ef6c00}
.muted{color:#666;font-size:.9rem}.review{background:#fff4f4;padding:8px;border-radius:4px;margin-top:6px}
.done{background:#eef7ee}button{margin-right:6px}input[type=text]{width:60%}
@media (prefers-color-scheme: dark){body{background:#151515;color:#e6e6e6}.card{background:#1f1f1f;border-color:#333}
.review{background:#3a1f1f}.done{background:#1f331f}.muted{color:#aaa}a{color:#8ab4f8}}'''


def page(title,body):
    return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
            f'<style>{CSS}</style></head><body>{body}</body></html>')


def render_item(item,day,review):
    from morning import LEVEL_TR, REVIEW_TR, reaction_text, reason_text, tr_num
    imp=item['importance']
    cls='flag' if imp['needs_review'] else ('high' if imp['level']=='high' else '')
    out=[f'<div class="card {cls}"><b>{e(item["symbol"])}</b> - {e(LEVEL_TR.get(imp["level"],imp["level"]))} '
         f'(skor {e(imp["score"])}) · {kap_link(item.get("kap_url"))}']
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
            out.append(f'<div class="review"><b>KONTROL ET:</b> {e(codes)}<br>'
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
    body=[f'<p><a href="/">← günler</a></p><h1>Sabah listesi: {e(day)}</h1>',
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
    return page('Masa paneli',f'<h1>Masa paneli</h1><ul>{links}</ul>')


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
            return self.send(200,render_index(available_days()))
        m=re.match(r'^/day/(\d{4}-\d{2}-\d{2})$',path)
        if m:
            items=load_day(m.group(1))
            if items is None:
                return self.send(404,page('Yok','<p>Bu gün için sabah listesi yok.</p>'))
            return self.send(200,render_day(m.group(1),items,load_sectors(),DESKS,load_reviews()))
        self.send(404,page('Yok','<p>Sayfa yok.</p>'))

    def do_POST(self):
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).hostname not in (HOST,'localhost'):
            return self.send(403,page('Hayır','<p>Yalnızca yerel istek.</p>'))
        if urlparse(self.path).path!='/review':
            return self.send(404,page('Yok','<p>Sayfa yok.</p>'))
        n=min(int(self.headers.get('Content-Length') or 0),4096)
        form={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode('utf-8')).items()}
        day=form.get('day','')
        if not DAY_RE.match(day) or form.get('decision') not in DECISIONS or not form.get('news_id'):
            return self.send(400,page('Hata','<p>Geçersiz istek.</p>'))
        items=load_day(day) or []
        if form['news_id'] not in {i['news_id'] for i in items if i['importance']['needs_review']}:
            return self.send(400,page('Hata','<p>Bu bildirim o günün kontrol listesinde yok.</p>'))
        record_review(form['news_id'],day,form['decision'],form.get('note'))
        self.send(303,'',location=f'/day/{day}')


def stats(path=LOG_PATH):
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
        if r['day'] not in days:
            days[r['day']]={i['news_id']:i for i in (load(r['day']) or [])}
        item=days[r['day']].get(nid)
        codes=item['importance']['needs_review_reasons'] if item else ['unknown_item']
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
        try:
            record_review('2','2026-11-09','maybe',None,path=log)
            raise AssertionError('bad decision accepted')
        except ValueError:
            pass
        out=render_day('2026-11-09',items,sectors,{},rv)
        assert 'kontrol edilen 1' in out and 'Kontrol edildi: Doğru' in out and 'name="decision"' not in out
    assert 'Kayıtlı sabah listesi yok.' in render_index([])
    assert 'Bu gün yeni iş ilişkisi bildirimi yok.' in render_day('2026-11-01',[],{},{},{})
    print('self-test ok: 16 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--serve',action='store_true')
    ap.add_argument('--port',type=int,default=PORT)
    ap.add_argument('--stats',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.stats:
        print(' '.join(f'{k}={v}' for k,v in stats().items()))
        for code,c in reason_stats(load_reviews()).items():
            print(f'  {code} confirm={c["confirm"]} reject={c["reject"]}')
    elif args.serve:
        print(f'panel on http://{HOST}:{args.port} (Ctrl+C to stop); days={len(available_days())} sectors={len(load_sectors())}')
        ThreadingHTTPServer((HOST,args.port),Handler).serve_forever()
    else:
        ap.error('give --serve, --stats or --self-test')


if __name__=='__main__':
    main()
