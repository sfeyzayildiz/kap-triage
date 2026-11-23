'''Tests moved from chat.py (v1 self-test).'''
from datetime import datetime
from kap_triage.web.chat import EXAMPLES, MAX_HISTORY, ask, linkify, render_answer, render_body


def test_chat():
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
    assert '<script>' not in body and '&lt;script&gt;' in body and 'id="son"' in body and '· konu araması' in body
    assert 'Sohbeti temizle' in body and 'Örnek sorular' not in body
    empty=render_body([])
    assert 'Örnek sorular' in empty and empty.count('action="/chat"')==1+len(EXAMPLES)
    assert 'kart olarak' in empty and 'Fonet' in empty
    h=render_answer('## 1. Son bildirim\n# Başlık\nsatır')
    assert '##' not in h and '<div class="ah">1. Son bildirim</div>' in h and '<div class="ah">Başlık</div>' in h
