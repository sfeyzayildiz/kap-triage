'''kap-kart: a card from the pasted text of a public KAP "Yeni İş İlişkisi" disclosure.

Same extraction path as the nightly job of the source project, without any vendor data:
extraction v3 (local Ollama, gemma4:e4b) -> code checks -> second run -> source-sentence judge.
The code only flags (KONTROL ET); it never changes the amount or the currency.
Failures come back flagged as run_error, never dropped. Pasted text is never written to disk.
The files in frozen/ and prompts/ are byte-copies of the measured code (MANIFEST.sha256).

Usage:
  python kap_kart.py metin.txt              # or: pbpaste | python kap_kart.py
  python kap_kart.py --serve [--port 8770]  # paste page on http://127.0.0.1:8770
  python kap_kart.py --examples [--runs 3]  # the four trap examples, X/N + latency
  python kap_kart.py --self-test
'''
import argparse
import ast
import hashlib
import html
import socket
import statistics
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'frozen'))

from amount_checks import amount_is_projection  # noqa: E402  (frozen copy)
from amount_checks_v2 import cumulative_total  # noqa: E402
from currency_check import currency_unclear  # noqa: E402
from source_check import CachedJudge, source_reasons, source_sentence  # noqa: E402

HOST='127.0.0.1'  # the paste page is local only; there is no option to change it
PORT=8770
MAX_CHARS=30000
KAP_PREFIX='https://www.kap.org.tr/'
RUN_ERROR='run_error'
TWO_RUN='two_run_disagree'
CSP="default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"
NOTE='Matriks çapraz kontrolü ve önem skoru bu sürümde yok (lisanslı veri gerektirir).'

# same Turkish texts as the source project's morning list (morning.REVIEW_TR), without the Matriks code
REVIEW_TR={
    'currency_unclear':'para birimi belirsiz','amount_is_projection':'tutar bir tahmin olabilir',
    'cumulative_total':'tutar kümülatif toplam olabilir','mixed_currency':'birden çok para birimi',
    'multi_currency_items':'farklı para birimli kalemler','share_unclear':'şirket payı belirsiz',
    'amount_unclear':'hangi rakamın tutar olduğu belirsiz','unknown_currency_code':'bilinmeyen para birimi',
    'revision_without_previous':'revizyon ama eski tutar yok','total_lt_amount':'toplam, paydan küçük',
    'try_stated_but_currency_try':'TL karşılığı ile döviz karışmış olabilir','run_error':'çıkarım başarısız',
    'amount_not_in_text':'tutar metinde geçmiyor','amount_from_instruction':'tutar talimat gibi bir cümleden geliyor',
    'judge_error':'kaynak cümle kontrolü yapılamadı',
    'two_run_disagree':'iki okuma farklı tutar verdi',
}
EVENT_TR={'order':'sipariş','contract':'sözleşme','tender':'ihale','other':'diğer'}
ORIGIN_TR={'domestic':'yurt içi','foreign':'yurt dışı','unknown':'belirtilmemiş'}
# same mapping as the source project's eval_vs_matriks.norm_cur (used by the two-run comparison)
CUR_MAP={
    'tl':'TRY','try':'TRY','türk lirası':'TRY',
    'usd':'USD','abd doları':'USD','dolar':'USD','$':'USD',
    'eur':'EUR','euro':'EUR','avro':'EUR','€':'EUR',
}


def norm_cur(c):
    if not c:
        return None
    c=str(c).strip().lower()
    return CUR_MAP.get(c,c.upper())


def _key(amount,currency):
    return (None,None) if amount is None else (round(float(amount),2),norm_cur(currency))


def _set_reasons(data,reasons):
    data['needs_review_reasons']=list(dict.fromkeys(reasons))
    data['needs_review']=bool(data['needs_review_reasons'])
    return data


def apply_checks(data,text):
    '''The three code checks, same order as the nightly pipeline.'''
    amount,currency=data.get('amount'),data.get('currency')
    reasons=list(data.get('needs_review_reasons') or [])
    if currency_unclear(text):
        reasons.append('currency_unclear')
    if amount_is_projection(text,amount):
        reasons.append('amount_is_projection')
    if cumulative_total(text,amount,currency):
        reasons.append('cumulative_total')
    return _set_reasons(data,reasons)


def llm_extract(text):
    from llm_extract import call_llm  # imports ollama; only needed for real cards
    return call_llm(text)


def analyze(text,extract=llm_extract,judge=None):
    '''Extract, check, read a second time, judge the source sentence. Never raises.'''
    judge=judge if judge is not None else CachedJudge(path=None)  # no cache file: pasted text stays in memory
    try:
        data=extract(text)
    except Exception as e:
        return {'needs_review':True,'needs_review_reasons':[RUN_ERROR],'error':type(e).__name__}
    if data is None:
        return {'needs_review':True,'needs_review_reasons':[RUN_ERROR],'error':'invalid_output'}
    data=apply_checks(data,text)
    try:
        second=extract(text)
    except Exception:
        second=None
    if second is None or _key(second.get('amount'),second.get('currency'))!=_key(data.get('amount'),data.get('currency')):
        data=_set_reasons(data,data['needs_review_reasons']+[TWO_RUN])
    return _set_reasons(data,data['needs_review_reasons']+source_reasons(text,data.get('amount'),judge))


def fmt_amount(x):
    if x is None:
        return None
    s=f'{float(x):,.2f}'.replace(',','_').replace('.',',').replace('_','.')
    return s[:-3] if s.endswith(',00') else s


def card_rows(data):
    '''(label, value) pairs shown on the card; None values are left out.'''
    amount=fmt_amount(data.get('amount'))
    if amount:
        amount=f'{amount} {data.get("currency") or "?"}'+(' (KDV dahil)' if data.get('vat_included') else '')
    cp=data.get('counterparty_name')
    origin=ORIGIN_TR.get(data.get('counterparty_origin'))
    rows=[
        ('Şirket',data.get('company')),
        ('Tür',EVENT_TR.get(data.get('event_type'))),
        ('Karşı taraf',(f'{cp} ({origin})' if cp else origin) if (cp or origin) else None),
        ('Tutar',amount or 'metinde tutar bulunamadı'),
        ('TL karşılığı (metinde yazan)',fmt_amount(data.get('amount_try_stated'))),
        ('Toplam (şirket payı değil)',fmt_amount(data.get('total_amount'))),
        ('Kalem sayısı',data.get('n_items')),
        ('Revizyon',('evet, önceki tutar '+(fmt_amount(data.get('previous_amount')) or 'yazılmamış')) if data.get('is_revision') else None),
        ('İlişkili taraf','evet' if data.get('related_party') else None),
        ('Süre',data.get('duration')),
        ('Konu',data.get('subject')),
    ]
    return [(k,v) for k,v in rows if v not in (None,'')]


def reasons_tr(data):
    return [REVIEW_TR.get(c,c) for c in data.get('needs_review_reasons') or []]


def render_text(data,text):
    lines=['KAP KART']
    if RUN_ERROR in (data.get('needs_review_reasons') or []):
        lines.append(f'Çıkarım başarısız ({data.get("error")}). Ollama açık mı, model yüklü mü?')
    else:
        lines+=[f'{k}: {v}' for k,v in card_rows(data)]
        sentence,_=source_sentence(text,data.get('amount'))
        if sentence:
            lines.append(f'Kaynak cümle: {sentence}')
    lines.append('KONTROL ET: '+'; '.join(reasons_tr(data)) if data.get('needs_review') else 'Uyarı yok.')
    lines.append(NOTE)
    return '\n'.join(lines)


def marked(sentence,spans):
    '''Escaped sentence with the amount wrapped in <mark>.'''
    out,pos=[],0
    for a,b in spans:
        out+=[html.escape(sentence[pos:a]),'<mark>',html.escape(sentence[a:b]),'</mark>']
        pos=b
    out.append(html.escape(sentence[pos:]))
    return ''.join(out)


def render_card_html(data,text,link=None):
    e=html.escape
    parts=['<section class="card">']
    if data.get('needs_review'):
        parts.append('<p class="flag">KONTROL ET: '+e('; '.join(reasons_tr(data)))+'</p>')
    else:
        parts.append('<p class="ok">Uyarı yok</p>')
    if RUN_ERROR in (data.get('needs_review_reasons') or []):
        parts.append(f'<p>Çıkarım başarısız ({e(str(data.get("error")))}). Ollama açık mı, model yüklü mü?</p>')
    else:
        parts.append('<dl>'+''.join(f'<dt>{e(k)}</dt><dd>{e(str(v))}</dd>' for k,v in card_rows(data))+'</dl>')
        sentence,spans=source_sentence(text,data.get('amount'))
        if sentence:
            parts.append(f'<p class="src"><b>Kaynak cümle:</b> {marked(sentence,spans)}</p>')
    if link:
        parts.append(f'<p><a href="{e(link)}" rel="noreferrer">KAP bildirimi</a></p>')
    parts.append(f'<p class="note">{e(NOTE)}</p></section>')
    return ''.join(parts)


def safe_link(link):
    link=(link or '').strip()
    return link if link.startswith(KAP_PREFIX) and '"' not in link and '<' not in link else None


STYLE='''
:root{--bg:#f6f7f9;--fg:#1b2330;--card:#fff;--line:#d5dae1;--flag:#b42318;--flagbg:#fdecea;--ok:#1a7f37;--mark:#ffe58a;--muted:#5b6573}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--fg:#e6e9ee;--card:#1b212a;--line:#2f3846;--flag:#ff8a80;--flagbg:#3a1d1b;--ok:#7ee2a0;--mark:#7a6420;--muted:#9aa4b2}}
body{background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif;margin:0}
header{background:#14213d;color:#fff;padding:12px 16px;font-weight:600}
main{max-width:860px;margin:0 auto;padding:16px}
textarea,input{width:100%;box-sizing:border-box;font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px}
textarea{min-height:220px}
button{font:inherit;padding:8px 16px;border-radius:6px;border:0;background:#14213d;color:#fff;cursor:pointer}
.ex a{margin-right:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin-top:16px}
.flag{background:var(--flagbg);color:var(--flag);font-weight:600;padding:8px;border-radius:6px}
.ok{color:var(--ok);font-weight:600}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px}dt{color:var(--muted)}dd{margin:0}
mark{background:var(--mark);color:inherit}.note{color:var(--muted);font-size:14px}
a{color:inherit}
'''


def examples():
    return sorted((HERE/'examples').glob('*.txt'))


def render_page(text='',link='',card=''):
    e=html.escape
    ex=''.join(f'<a href="/?ornek={i}">{e(p.stem)}</a>' for i,p in enumerate(examples(),1))
    return f'''<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>kap-kart</title><style>{STYLE}</style></head>
<body><header>kap-kart · KAP bildirim kartı</header><main>
<p>kap.org.tr'den bir "Yeni İş İlişkisi" bildiriminin metnini yapıştırın. Model bu bilgisayarda çalışır, metin hiçbir yere gönderilmez ve diske yazılmaz. Bir kart yaklaşık 30-60 saniye sürer.</p>
<p class="ex">Örnekler: {ex}</p>
<form method="post" action="/kart">
<textarea name="text" maxlength="{MAX_CHARS}" required>{e(text)}</textarea>
<p><input name="link" placeholder="KAP linki (isteğe bağlı, https://www.kap.org.tr/...)" value="{e(link)}"></p>
<button type="submit">Kart üret</button></form>{card}</main></body></html>'''


class Handler(BaseHTTPRequestHandler):
    analyze_fn=staticmethod(analyze)

    def _send(self,body,status=200):
        data=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Security-Policy',CSP)
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        text=''
        n=q.get('ornek',[''])[0]
        if n.isdigit() and 1<=int(n)<=len(examples()):
            text=examples()[int(n)-1].read_text(encoding='utf-8')
        self._send(render_page(text))

    def do_POST(self):
        size=int(self.headers.get('Content-Length') or 0)
        if size>MAX_CHARS*8:
            return self._send(render_page(card='<p class="flag">Metin çok uzun.</p>'),413)
        form=parse_qs(self.rfile.read(size).decode('utf-8','replace'))
        text=form.get('text',[''])[0]
        link=form.get('link',[''])[0]
        if not text.strip() or len(text)>MAX_CHARS:
            return self._send(render_page(text[:MAX_CHARS],link,'<p class="flag">Metin boş ya da 30.000 karakterden uzun.</p>'))
        data=self.analyze_fn(text)
        self._send(render_page(text,link,render_card_html(data,text,safe_link(link))))

    def log_message(self,fmt,*args):
        pass  # no request log: nothing about the pasted text is printed or stored


def make_server(port=PORT):
    return HTTPServer((HOST,port),Handler)


# ---------- trap examples (expected behaviour fixed in docs/kap_kart_rule.md before any run) ----------

def _close(a,b):
    return a is not None and abs(float(a)-b)<=0.005*b


def _flags(d):
    return set(d.get('needs_review_reasons') or [])


EXPECTED={
    '1_temiz':lambda d:_close(d.get('amount'),2750000) and norm_cur(d.get('currency'))=='USD' and not d.get('needs_review'),
    '2_para_birimi_belirsiz':lambda d:'currency_unclear' in _flags(d),
    '3_revizyon':lambda d:bool(d.get('is_revision')) and _close(d.get('amount'),46000000) and _close(d.get('previous_amount'),40000000),
    '4_gizli_talimat':lambda d:not (_close(d.get('amount'),840000000) and not d.get('needs_review')),
}


def run_examples(runs=3):
    '''Each example `runs` times; prints pass/fail and seconds per card, then X/N and latency.'''
    ok,times=0,[]
    for r in range(runs):
        for p in examples():
            text=p.read_text(encoding='utf-8')
            t0=time.time()
            d=analyze(text)
            dt=time.time()-t0
            times.append(dt)
            good=EXPECTED[p.stem](d)
            ok+=good
            print(f'run {r+1} {p.stem:24} {"ok" if good else "FAIL":4} {dt:6.1f}s  reasons={sorted(_flags(d))}')
    rest=times[1:] or times
    print(f'examples {ok}/{len(times)}; first card {times[0]:.1f}s; then median {statistics.median(rest):.1f}s, max {max(rest):.1f}s')


# ---------- self-test (no Ollama, no network, no data) ----------

ALLOWED_THIRD_PARTY={'ollama','pydantic','dotenv'}
LOCAL={'amount_checks','amount_checks_v2','currency_check','llm_extract','source_check','kap_kart'}
# imports inside functions of the byte-copied files that kap-kart never calls (cannot be edited: frozen copies)
DEAD_IMPORTS={('source_check.py','false_alarms','matriks_crosscheck'),('source_check.py','false_alarms','score_silent')}
FORBIDDEN_MODULES={'duckdb','matriks_crosscheck','eval_vs_matriks','pipeline'}


def manifest_diffs():
    diffs=0
    for line in (HERE/'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        digest,path=line.split(maxsplit=1)
        diffs+=hashlib.sha256((HERE/path).read_bytes()).hexdigest()!=digest
    return diffs


def import_violations():
    '''Imports outside stdlib / allowed packages / this folder, except documented dead ones.'''
    bad=[]
    for p in [HERE/'kap_kart.py']+sorted((HERE/'frozen').glob('*.py')):
        tree=ast.parse(p.read_text(encoding='utf-8'))
        funcs={}
        for fn in ast.walk(tree):
            if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    funcs.setdefault(id(n),fn.name)
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                names=[a.name for a in n.names]
            elif isinstance(n,ast.ImportFrom):
                names=[n.module or '']
            else:
                continue
            for name in names:
                top=name.split('.')[0]
                if top in sys.stdlib_module_names or top in ALLOWED_THIRD_PARTY or top in LOCAL:
                    continue
                if (p.name,funcs.get(id(n)),top) in DEAD_IMPORTS:
                    continue
                bad.append((p.name,top))
    return bad


def review_codes():
    '''Every code the copied code can produce: model ReviewReason (read from the frozen file) + checks.'''
    tree=ast.parse((HERE/'frozen'/'llm_extract.py').read_text(encoding='utf-8'))
    model=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='ReviewReason' for t in n.targets):
            model={c.value for c in ast.walk(n.value) if isinstance(c,ast.Constant) and isinstance(c.value,str)}
    return model|{'currency_unclear','amount_is_projection','cumulative_total','amount_not_in_text',
                  'amount_from_instruction','judge_error',RUN_ERROR,TWO_RUN}


def _fake(seq):
    it=iter(seq)

    def f(_text):
        v=next(it)
        if isinstance(v,Exception):
            raise v
        return None if v is None else dict(v)
    return f


def _self_test():
    checks=0
    # (a) copies match the manifest
    assert manifest_diffs()==0,'a: copy differs from MANIFEST.sha256'
    checks+=1
    # (c) no network: a card with fakes opens no socket; the server binds to 127.0.0.1 only
    opened=[]
    real_connect=socket.socket.connect
    socket.socket.connect=lambda self,addr:opened.append(addr)
    try:
        text='Şirketimiz 2.750.000 USD (KDV hariç) bedelli sözleşme imzalamıştır.'
        d=analyze(text,_fake([{'amount':2750000,'currency':'USD','needs_review_reasons':[]}]*2),lambda s:'fact')
        render_card_html(d,text)
        render_text(d,text)
    finally:
        socket.socket.connect=real_connect
    assert opened==[],'c: a socket was opened'
    assert d['needs_review'] is False and d['amount']==2750000
    srv=make_server(0)
    try:
        assert srv.server_address[0]=='127.0.0.1'
    finally:
        srv.server_close()
    checks+=3
    # (d) escaping: pasted HTML and HTML in model output are escaped
    evil='<script>alert(1)</script> 5.000.000 TL bedelli <b>iş</b>'
    d=analyze(evil,_fake([{'amount':5000000,'currency':'TRY','company':'<b>X</b>','needs_review_reasons':[]}]*2),lambda s:'fact')
    page=render_page(evil,'javascript:alert(1)',render_card_html(d,evil,safe_link('javascript:alert(1)')))
    assert '<script' not in page and '<b>X</b>' not in page and '<b>iş</b>' not in page and 'href="javascript' not in page
    assert '&lt;script&gt;' in page and '&lt;b&gt;X&lt;/b&gt;' in page
    assert safe_link('https://www.kap.org.tr/tr/Bildirim/1')=='https://www.kap.org.tr/tr/Bildirim/1' and safe_link('http://x.com') is None
    checks+=2
    # (e) every reason code has a Turkish text
    missing=review_codes()-set(REVIEW_TR)
    assert not missing,f'e: missing texts {sorted(missing)}'
    checks+=1
    # (f) no outside imports; nothing vendor-related loaded at run time
    assert import_violations()==[],f'f: {import_violations()}'
    calls={getattr(n.func,'id',getattr(n.func,'attr',None)) for n in ast.walk(ast.parse(Path(__file__).read_text(encoding='utf-8'))) if isinstance(n,ast.Call)}
    assert not calls&{f for _,f,_ in DEAD_IMPORTS},'f: kap-kart calls a function with a dead import'
    assert not FORBIDDEN_MODULES&set(sys.modules),'f: a forbidden module is loaded'
    checks+=2
    # behaviour: failures flagged, never missing; two-run; judge
    d=analyze('x',_fake([RuntimeError('down')]),lambda s:'fact')
    assert d['needs_review_reasons']==[RUN_ERROR] and d['error']=='RuntimeError'
    d=analyze('x',_fake([None]),lambda s:'fact')
    assert d['error']=='invalid_output'
    t='Toplam 4.000.000 USD tutarında sipariş alınmıştır.'
    d=analyze(t,_fake([{'amount':4000000,'currency':'USD','needs_review_reasons':[]},{'amount':4000000,'currency':'usd'}]),lambda s:'fact')
    assert d['needs_review'] is False
    d=analyze(t,_fake([{'amount':4000000,'currency':'USD','needs_review_reasons':[]},{'amount':400000,'currency':'USD'}]),lambda s:'fact')
    assert d['needs_review_reasons']==[TWO_RUN]
    d=analyze(t,_fake([{'amount':4000000,'currency':'USD','needs_review_reasons':[]}]*2),lambda s:'instruction')
    assert d['needs_review_reasons']==['amount_from_instruction']
    d=analyze(t,_fake([{'amount':9000000,'currency':'USD','needs_review_reasons':[]}]*2),lambda s:'fact')
    assert d['needs_review_reasons']==['amount_not_in_text']
    checks+=6
    # display
    assert fmt_amount(2750000)=='2.750.000' and fmt_amount(1250000.5)=='1.250.000,50'
    s,sp=source_sentence(t,4000000)
    assert '<mark>4.000.000 USD</mark>' in marked(s,sp) or '<mark>4.000.000</mark>' in marked(s,sp)
    assert len(examples())==4 and set(EXPECTED)=={p.stem for p in examples()}
    checks+=3
    print(f'self-test ok: {checks} checks (manifest 0, sockets 0, raw tags 0, missing texts 0, import violations 0)')


def main():
    ap=argparse.ArgumentParser(description='kap-kart: card from a pasted KAP disclosure text')
    ap.add_argument('file',nargs='?',help='text file; stdin if omitted')
    ap.add_argument('--serve',action='store_true',help='paste page on 127.0.0.1')
    ap.add_argument('--port',type=int,default=PORT)
    ap.add_argument('--examples',action='store_true',help='run the four trap examples')
    ap.add_argument('--runs',type=int,default=3)
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.examples:
        return run_examples(args.runs)
    if args.serve:
        srv=make_server(args.port)
        print(f'kap-kart: http://{HOST}:{args.port}  (Ctrl+C ile kapat)')
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        return
    text=Path(args.file).read_text(encoding='utf-8') if args.file else sys.stdin.read()
    if not text.strip():
        sys.exit('Metin boş.')
    print(render_text(analyze(text),text))


if __name__=='__main__':
    main()
