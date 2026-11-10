'''Chat page for the triage agent: one question box, answers from scripts/agent.py.

Served by panel.py (the start page "/"). The question goes to the same LangGraph agent as the
terminal command (route -> validate -> one tool); numbers and links still come from code.
No JavaScript: a plain form, the server renders the whole conversation (strict CSP in panel.py).
History lives only in this process's memory (cleared on restart, never written to disk).
Every text is HTML-escaped; only kap.org.tr links become clickable.

Usage:
  python scripts/chat.py --self-test
  python scripts/panel.py --serve        # http://127.0.0.1:8765
'''
import html
import re
import sys
import threading
import time
from datetime import datetime

MAX_QUESTION=500
MAX_HISTORY=50
URL_RE=re.compile(r'https?://[^\s|<>"]+')
KAP_RE=re.compile(r'^https://(www\.)?kap\.org\.tr/')
EXAMPLES=['Bugün neye bakmalıyım?','17 Eylül 2026 bildirimleri','ASELS son bir yılda hangi işleri aldı?',
          'KONTR 28 Ekim\'de neden yükseldi?','Irak\'taki projelerle ilgili bildirimler']
HISTORY=[]
LOCK=threading.Lock()  # one question at a time: Ollama runs one model call at once anyway

e=lambda x:html.escape('' if x is None else str(x))

CSS='''nav{margin-bottom:12px}nav a{margin-right:14px}
.msg{border-radius:10px;padding:10px 14px;margin:10px 0;max-width:85%}
.q{background:#e3f0ff;margin-left:auto}.a{background:#fff;border:1px solid #ddd}
.ah{font-weight:600;margin-bottom:4px}.a div{margin:2px 0}.err{border-left:5px solid #c62828}
.ask textarea{width:100%;box-sizing:border-box;font:inherit;padding:8px}
.ex{display:inline-block;margin:4px 6px 4px 0}.ex button{border-radius:14px;padding:4px 10px}
@media (prefers-color-scheme: dark){.q{background:#1e3a5f}.a{background:#1f1f1f;border-color:#333}}'''


def linkify(line):
    '''Escape a line; KAP links become "KAP bildirimi" links, other URLs stay plain text.'''
    out,pos=[],0
    for m in URL_RE.finditer(line):
        url=m.group(0).rstrip('.,;:)')
        out.append(e(line[pos:m.start()]))
        if KAP_RE.match(url):
            out.append(f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">KAP bildirimi</a>')
        else:
            out.append(e(url))
        pos=m.start()+len(url)
    out.append(e(line[pos:]))
    return ''.join(out)


def render_answer(text):
    lines=[]
    for raw in (text or '').splitlines():
        s=raw.rstrip()
        if not s:
            continue
        if s.startswith('# '):
            lines.append(f'<div class="ah">{linkify(s[2:])}</div>')
        else:
            lines.append(f'<div>{linkify(s)}</div>')
    return ''.join(lines)


def in_collection_window(now):
    return now.hour==23 and 40<=now.minute<=50


def default_runner(question):
    from agent import TOOLS, build_graph, llm_route, load_context
    ctx=load_context()  # one short read-only DB read per question, so a new night's data is seen
    return build_graph(llm_route,TOOLS,ctx).invoke({'question':question})


def ask(question,runner=None,now=None,history=None):
    '''Run one question and append the record to the history; never raises.'''
    history=HISTORY if history is None else history
    now=now or datetime.now()
    rec={'q':question,'at':now.strftime('%H:%M'),'intent':None,'seconds':0.0,'error':False}
    if in_collection_window(now):
        rec.update(a='Gece toplama penceresi (23:40-23:50): veritabanına dokunulmuyor. 23:50\'den sonra tekrar sorun.',error=True)
    else:
        t0=time.time()
        try:
            with LOCK:
                out=(runner or default_runner)(question)
            rec.update(a=out.get('answer') or '',intent=out.get('intent'))
        except Exception as ex:  # Ollama down, DB locked, ...: show the type, keep the page alive
            rec.update(a=f'Cevap üretilemedi ({type(ex).__name__}). Ollama açık mı? Terminalde "ollama list" ile kontrol edin.',
                       error=True)
        rec['seconds']=round(time.time()-t0,1)
    history.append(rec)
    del history[:-MAX_HISTORY]
    return rec


def render_body(history):
    out=['<nav><a href="/">Sohbet</a><a href="/days">Sabah listeleri</a></nav>',
         '<h1>KAP Bildirim Önceliklendirme Asistanı</h1>',
         '<p class="muted">Yeni iş ilişkisi bildirimleri hakkında sorun. Rakamlar ve linkler veritabanından gelir, '
         'model yalnızca soruyu yönlendirir. Her şey bu bilgisayarda çalışır.</p>']
    for i,r in enumerate(history):
        anchor=' id="son"' if i==len(history)-1 else ''
        out.append(f'<div class="msg q"{anchor}>{e(r["q"])}</div>')
        meta=f'{e(r["at"])} · {r["seconds"]:.1f} sn'.replace('.',',')+(f' · araç: {e(r["intent"])}' if r['intent'] else '')
        out.append(f'<div class="msg a{" err" if r["error"] else ""}">{render_answer(r["a"])}'
                   f'<div class="muted">{meta}</div></div>')
    out.append('<form class="ask" method="post" action="/chat">'
               f'<textarea name="q" rows="2" maxlength="{MAX_QUESTION}" required '
               'placeholder="Sorunuzu yazın, ör. Bugün neye bakmalıyım?"></textarea>'
               '<button>Sor</button> <span class="muted">Cevap birkaç saniye sürer; ilk arama modelleri yüklediği için daha uzun.</span>'
               '</form>')
    if not history:
        out.append('<p class="muted">Örnek sorular:</p>')
    out+= [f'<form class="ex" method="post" action="/chat"><input type="hidden" name="q" value="{e(q)}">'
           f'<button>{e(q)}</button></form>' for q in EXAMPLES]
    if history:
        out.append('<form class="ex" method="post" action="/chat/clear"><button>Sohbeti temizle</button></form>')
    out.append('<p class="muted">Kaynak: KAP bildirimleri ve Matriks verisi. Karar öncesi KAP metnini okuyun.</p>')
    return ''.join(out)


def _self_test():
    s=linkify('1. 2026-09-17 | AAA | https://www.kap.org.tr/tr/Bildirim/123.')
    assert '<a href="https://www.kap.org.tr/tr/Bildirim/123"' in s and s.endswith('KAP bildirimi</a>.')
    s=linkify('bak: javascript:alert(1) http://evil.example/x <b>')
    assert '<a' not in s and '&lt;b&gt;' in s and 'http://evil.example/x' in s
    a=render_answer('# Başlık\n\n- satır <i>\n')
    assert a=='<div class="ah">Başlık</div><div>- satır &lt;i&gt;</div>'
    h=[]
    r=ask('soru?',runner=lambda q:{'answer':'# ok','intent':'morning'},now=datetime(2026,11,10,12),history=h)
    assert r['intent']=='morning' and r['a']=='# ok' and not r['error'] and len(h)==1
    def boom(q):
        raise ConnectionError('x')
    r=ask('soru?',runner=boom,now=datetime(2026,11,10,12),history=h)
    assert r['error'] and 'ConnectionError' in r['a'] and len(h)==2
    called=[]
    r=ask('soru?',runner=lambda q:called.append(q),now=datetime(2026,11,10,23,45),history=h)
    assert r['error'] and not called and '23:40' in r['a']
    for i in range(MAX_HISTORY+5):
        ask(f'q{i}',runner=lambda q:{'answer':'x','intent':'unknown'},now=datetime(2026,11,10,12),history=h)
    assert len(h)==MAX_HISTORY and h[-1]['q']==f'q{MAX_HISTORY+4}'
    body=render_body([{'q':'<script>x</script>','a':'cevap','at':'12:00','seconds':1.25,'intent':'search','error':False}])
    assert '<script>' not in body and '&lt;script&gt;' in body and 'id="son"' in body and 'araç: search' in body
    assert 'Sohbeti temizle' in body and 'Örnek sorular' not in body
    empty=render_body([])
    assert 'Örnek sorular' in empty and empty.count('action="/chat"')==1+len(EXAMPLES)
    print('self-test ok: 10 checks')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        _self_test()
    else:
        sys.exit(__doc__)
