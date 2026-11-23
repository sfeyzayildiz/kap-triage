'''HTTP routes of the FastAPI app (kap_triage/web/app.py) on an empty data folder: local-only
checks, error pages, the theme cookie, the JSON API and the kap-kart page with a fake model.'''
import html
from types import SimpleNamespace

from fastapi.testclient import TestClient

import kap_triage.web.app as app_module
import kap_triage.web.chat as chat
import kap_triage.web.kart as kart

LOCAL='http://127.0.0.1:8765'
client=TestClient(app_module.app,base_url=LOCAL)


def test_local_hosts_only():
    # DNS rebinding: a page is served only for a local Host header (or 'panel', the n8n service name)
    assert client.get('/guvenilirlik').status_code==200
    assert client.get('/guvenilirlik',headers={'Host':'localhost:8765'}).status_code==200
    assert client.get('/guvenilirlik',headers={'Host':'panel:8765'}).status_code==200
    assert client.get('/guvenilirlik',headers={'Host':'evil.example:8765'}).status_code==403


def test_post_from_another_site_is_refused():
    assert client.post('/chat/clear',headers={'Origin':'https://evil.example'},follow_redirects=False).status_code==403
    r=client.post('/chat/clear',headers={'Origin':LOCAL},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/'


def test_security_headers_and_error_pages():
    r=client.get('/guvenilirlik')
    assert r.headers['content-security-policy'].startswith("default-src 'none'")
    assert r.headers['content-type']=='text/html; charset=utf-8'
    # unknown page and wrong method: the same plain 404 page, not a JSON error
    for r in (client.get('/nope'),client.get('/review'),client.post('/nope')):
        assert r.status_code==404 and 'Sayfa yok.' in r.text
    # the API docs page is off (it would load outside scripts)
    assert client.get('/docs').status_code==404 and client.get('/openapi.json').status_code==404


def test_bad_form_requests():
    # a review for a day without a list, a broken Content-Length, an unknown watchlist action
    assert client.post('/review',data={'day':'2026-11-09','decision':'confirm','news_id':'1'}).status_code==400
    assert client.post('/review',content=b'x',headers={'Content-Length':'abc'}).status_code==400
    assert client.post('/takip',data={'action':'drop','symbol':'AAA'}).status_code==400
    assert client.post('/chat',data={'q':''}).status_code==400


def test_theme_cookie():
    # /tema cycles auto -> dark -> light; the page then carries data-theme on <html>
    r=client.get('/tema',headers={'Referer':f'{LOCAL}/days'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/days' and 'theme=dark' in r.headers['set-cookie']
    assert '<html lang="tr" data-theme="dark">' in TestClient(app_module.app,base_url=LOCAL,cookies={'theme':'dark'}).get('/days').text
    assert '<html lang="tr">' in TestClient(app_module.app,base_url=LOCAL).get('/days').text   # a client without the cookie


def test_json_api_on_empty_data():
    assert client.get('/api/v1/days').json()=={'days':[]}
    assert client.get('/api/v1/day/2026-11-09').status_code==404
    r=client.get('/api/v1/desks/latest')
    assert r.status_code==404 and r.json()['error']=='no morning list'


def test_night_window(monkeypatch):
    # 23:40-23:50: pages that read the DB answer 503 (JSON for the API); other pages stay open
    monkeypatch.setattr(chat,'in_collection_window',lambda now:True)
    assert client.get('/day/2026-11-09').status_code==503
    r=client.get('/api/v1/desks/latest')
    assert r.status_code==503 and r.json()['retry_after']=='23:50'
    assert client.get('/guvenilirlik').status_code==200


def test_kart_page(monkeypatch):
    # GET: the paste form, an example filled in; POST: the card from a fake model, everything escaped
    assert 'name="text"' in client.get('/kart').text
    assert html.escape(kart.example_text(1))[:60] in client.get('/kart?ornek=1').text
    fake={'amount':5000000.0,'currency':'TRY','company':'<b>X</b>','needs_review':False,'needs_review_reasons':[]}
    monkeypatch.setattr(kart,'analyze',lambda text:dict(fake))
    r=client.post('/kart',data={'text':'<script>alert(1)</script> 5.000.000 TL bedelli iş','link':'javascript:alert(1)'})
    assert r.status_code==200 and 'Uyarı yok' in r.text
    assert '<script>alert' not in r.text and '&lt;b&gt;X&lt;/b&gt;' in r.text and 'href="javascript' not in r.text
    assert 'Metin boş' in client.post('/kart',data={'text':'  '}).text
    assert client.post('/kart',content=b'x',headers={'Content-Length':str(kart.MAX_CHARS*8+1)}).status_code==413


def test_chat_question_with_a_fake_agent(monkeypatch):
    seen=[]
    monkeypatch.setattr(chat,'ask',lambda q:seen.append(q) or {'intent':'help','seconds':0.0,'error':False})
    r=client.post('/chat',data={'q':'ASELS son işleri'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/#son' and seen==['ASELS son işleri']


def no_card(text):
    return {'amount':None,'needs_review':False,'needs_review_reasons':[]}


def test_kart_long_turkish_text_and_link(monkeypatch):
    # 6,500 Turkish characters (up to 6 bytes each in the form) arrive whole, and the link after them too
    seen=[]
    monkeypatch.setattr(kart,'analyze',lambda text:seen.append(text) or no_card(text))
    text=('Şirketimiz ile müşteri arasında işçiliği ve güçlendirme çalışmalarını kapsayan sözleşme imzalanmıştır. '*70)[:6500]
    link='https://www.kap.org.tr/tr/Bildirim/123'
    r=client.post('/kart',data={'text':text,'link':link})
    assert r.status_code==200 and seen==[text] and f'href="{link}"' in r.text


def test_body_is_never_cut(monkeypatch):
    seen=[]
    monkeypatch.setattr(kart,'analyze',lambda text:seen.append(text) or no_card(text))
    form={'Content-Type':'application/x-www-form-urlencoded'}
    # a negative or broken Content-Length is refused (400), on the card page and on the other forms
    assert client.post('/kart',content=b'text=abc',headers={**form,'Content-Length':'-1'}).status_code==400
    assert client.post('/review',content=b'day=x',headers={**form,'Content-Length':'-1'}).status_code==400
    # a body sent in chunks (no Content-Length) is read whole; over the limit it is refused (413)
    r=client.post('/kart',content=iter([b'text=',b'Sirketimiz+5.000.000+TL']),headers=form)
    assert r.status_code==200 and seen==['Sirketimiz 5.000.000 TL']
    assert client.post('/chat',content=iter([b'q=',b'x'*5000]),headers=form).status_code==413


def test_malformed_origin_is_refused():
    assert client.post('/chat/clear',headers={'Origin':'http://[bad'},follow_redirects=False).status_code==403


def test_theme_only_on_html_pages():
    request=SimpleNamespace(cookies={'theme':'dark'})
    body='{"text":"<html lang=\\"tr\\">"}'
    assert app_module.send(request,200,body,ctype=app_module.JSON).body.decode()==body
    assert b'data-theme="dark"' in app_module.send(request,200,'<html lang="tr">').body
