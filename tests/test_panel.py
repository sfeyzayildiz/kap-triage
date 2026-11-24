"""Panel pages (kap_triage/web/panel.py) on made-up items: escaping, review log, night window,
watchlist forms and request helpers. The HTTP routes are tested in test_app.py."""

import os
from datetime import datetime
import kap_triage.web.chat as chat
import kap_triage.web.form as form
import kap_triage.web.watchlist as watchlist
from kap_triage.web.panel import (
    CHART_DAYS,
    CSS,
    FILTER_PARAM,
    MSG_PARAM,
    UNASSIGNED,
    all_day_stats,
    by_desk,
    column_chart,
    day_counts,
    desk_of,
    flag_chart,
    host_ok,
    load_reviews,
    look_first_box,
    pretty_sector,
    reads_db,
    reason_stats,
    record_review,
    render_day,
    render_index,
    render_item,
    render_overview,
    render_reviews,
    render_themes_index,
    render_week,
    review_rows,
    safe_back,
    source_html,
    sources_for_items,
    stats,
    takip_message,
    theme_back,
    tr_time,
    window_block,
    with_message,
)


def test_panel():
    import tempfile

    imp = lambda score, level, flag: {
        'score': score,
        'level': level,
        'needs_review': bool(flag),
        'needs_review_reasons': flag,
        'reasons': [{'code': 'foreign_currency', 'currency': 'USD', 'points': 1}],
    }
    items = [
        {
            'news_id': '1',
            'symbol': 'AAA',
            'kap_url': 'https://www.kap.org.tr/tr/Bildirim/1',
            'amount': 1500000.0,
            'currency': 'USD',
            'importance': imp(4, 'high', []),
        },
        {
            'news_id': '2',
            'symbol': 'BBB',
            'kap_url': 'javascript:alert(1)',
            'amount': None,
            'importance': imp(0, 'low', ['amount_not_in_text']),
        },
        {
            'news_id': '3',
            'symbol': '<script>',
            'kap_url': 'https://kap.org.tr/x',
            'amount': None,
            'importance': imp(1, 'low', []),
        },
        {
            'news_id': '4',
            'symbol': 'CCC',
            'kap_url': 'https://www.kap.org.tr/tr/Bildirim/4',
            'amount': None,
            'importance': imp(1, 'low', []),
        },
    ]
    sectors = {'AAA': 'Savunma', 'BBB': 'Enerji', 'CCC': 'Savunma'}
    assert desk_of('AAA', sectors, {}) == 'Savunma' and desk_of('ZZZ', sectors, {}) == UNASSIGNED
    assert pretty_sector('GIDA , İÇECEK VE TÜTÜN') == 'Gıda, İçecek ve Tütün'
    assert (
        pretty_sector('METAL ESYA,MAKİNE,ELEKTRİKLİ CİHAZLAR,ULASIM ARAÇ')
        == 'Metal Eşya, Makine, Elektrikli Cihazlar, Ulaşım Araç'
    )
    assert (
        pretty_sector('TEKNOLOJİ - BİLİŞİM') == 'Teknoloji - Bilişim'
        and pretty_sector('İNŞAAT-TAAHHÜT') == 'İnşaat - Taahhüt'
        and pretty_sector(None) is None
    )
    assert (
        pretty_sector('TAS VE TOPRAĞA DAYALI') == 'Taş ve Toprağa Dayalı'
    )  # display only; mailbox unchanged (tas-ve-...)
    assert desk_of('BBB', sectors, {'Enerji': 'Enerji ve altyapı'}) == 'Enerji ve altyapı'
    g = by_desk(items, sectors, {})
    assert list(g) == ['Enerji', 'Savunma', UNASSIGNED]  # ties on look-first broken by name, unassigned last
    assert [i['symbol'] for i in g['Savunma']] == ['AAA', 'CCC']
    html_out = render_day('2026-11-09', items, sectors, {}, {})
    assert '<script>' not in html_out and '&lt;script&gt;' in html_out  # escaped
    assert 'href="javascript' not in html_out and 'KAP linki geçersiz' in html_out
    assert '4 bildirim, 3 masa; kontrol gereken 1, kontrol edilen 0.' in html_out
    assert 'KONTROL ET:</b> tutar metinde geçmiyor' in html_out and 'name="decision" value="confirm"' in html_out
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 'r.jsonl')
        record_review('2', '2026-11-09', 'reject', 'x', path=log, now=datetime(2026, 11, 10, 9))
        record_review('2', '2026-11-09', 'confirm', '', path=log, now=datetime(2026, 11, 10, 10))
        rv = load_reviews(log)
        assert rv['2']['decision'] == 'confirm' and stats(log) == {'reviewed': 1, 'confirm': 1, 'reject': 0}
        rs = reason_stats(
            {**rv, '9': {'news_id': '9', 'day': '2026-11-09', 'decision': 'reject'}}, load=lambda d: items
        )
        assert rs == {'amount_not_in_text': {'confirm': 1, 'reject': 0}, 'unknown_item': {'confirm': 0, 'reject': 1}}
        stored = record_review('4', '2026-11-09', 'reject', '', path=log, reasons=['currency_unclear'])
        rs2 = reason_stats(
            {'4': stored, '1': {'news_id': '1', 'day': '2026-11-09', 'decision': 'confirm'}}, load=lambda d: items
        )
        assert rs2 == {
            'currency_unclear': {'confirm': 0, 'reject': 1},
            'not_flagged_after_rebuild': {'confirm': 1, 'reject': 0},
        }
        try:
            record_review('2', '2026-11-09', 'maybe', None, path=log)
            raise AssertionError('bad decision accepted')
        except ValueError:
            pass
        out = render_day('2026-11-09', items, sectors, {}, rv)
        assert 'kontrol edilen 1' in out and 'Kontrol edildi: Doğru' in out and 'name="decision"' not in out
    assert 'Kayıtlı sabah listesi yok.' in render_index([]) and 'href="/days"' in render_index([])
    assert 'Bu gün yeni iş ilişkisi bildirimi yok.' in render_day('2026-11-01', [], {}, {}, {})
    assert 'href="/themes"' in render_index([]) and 'href="/themes"' in render_day('2026-11-01', [], {}, {}, {})

    view = [
        {
            'cluster': 1,
            'n': 2,
            'words': [],
            'companies_week': 1,
            'companies_all': 1,
            'avg_per_week': 0.25,
            'ratio': 8.0,
            'items': [
                {'news_id': '4', 'symbol': '<b>', 'published_at': '2026-11-11 09:00:00'},
                {'news_id': '5', 'symbol': 'CCC', 'published_at': '2026-11-12 08:00:00'},
            ],
        },
        {
            'cluster': 0,
            'n': 1,
            'words': ['savunma', '<i>x'],
            'companies_week': 1,
            'companies_all': 9,
            'avg_per_week': 1.5,
            'ratio': 0.7,
            'items': [{'news_id': '3', 'symbol': 'AAA', 'published_at': '2026-11-10 09:00:00'}],
        },
    ]
    w = render_week(
        '2026-11-09', view, sectors, {'4': 'javascript:alert(1)', '5': 'https://www.kap.org.tr/tr/Bildirim/5'}
    )
    assert '3 bildirim, 2 tema.' in w and '<b>' not in w and '<i>' not in w and '&lt;i&gt;x' in w  # escaped
    assert 'href="javascript' not in w and 'href="https://www.kap.org.tr/tr/Bildirim/5"' in w
    assert w.count('şablon etkisi') == 1 and 'normalde haftada 0,2 bildirim' in w and 'sektörler: Savunma 1' in w
    assert 'tema kelimesi yok' in w and 'kısmen yansıtır' in w
    assert '<figure class="chart">X</figure>' in render_day(
        '2026-11-09', items, sectors, {}, {}, charts={'1': '<figure class="chart">X</figure>'}
    )
    idx = render_themes_index([('2026-11-09', 3)], '2026-11-12 08:00:00', 2)
    assert 'href="/themes/2026-11-09"' in idx and 'Sonraki 2 bildirim henüz kümelenmedi' in idx
    assert 'clusters.json bulunamadı' in render_themes_index([], None, 0)
    assert (
        'class="top"' in html_out and 'href="/form"' in html_out and '<main>' in html_out
    )  # theme header on every page
    assert (
        '<a class="badge flag" href="#r2">kontrol et ↓</a>' in html_out
        and 'id="r2"' in html_out
        and 'class="badge high">yüksek · skor 4' in html_out
    )
    assert (
        ':root[data-theme=dark]{' in CSS
        and ':root:not([data-theme=light])' in CSS
        and 'href="/tema"' in render_index([])
    )
    # source sentence: verbatim, escaped, amount marked; missing -> stated, never invented; not read -> nothing
    src = source_html(('<b>X</b> ile 12.500.000 TL bedelli sözleşme.', [(13, 23)]))
    assert (
        src
        == '<div class="src">Kaynak cümle: “&lt;b&gt;X&lt;/b&gt; ile <mark>12.500.000</mark> TL bedelli sözleşme.”</div>'
    )
    assert 'aynen geçmiyor' in source_html((None, [])) and source_html(None) == ''
    assert 'Kaynak cümle: “a <mark>5</mark>”' in render_day(
        '2026-11-09', [dict(items[0], amount=5.0)], sectors, {}, {}, sources={items[0]['news_id']: ('a 5', [(2, 3)])}
    )
    assert (
        sources_for_items([{'news_id': '1', 'amount': None}]) == {}
        and sources_for_items([dict(items[0], amount=1.0)], db='/nonexistent.duckdb') == {}
    )
    # C6: nightly window blocks every DB-reading GET route (503, no DB read); other pages and other times are untouched
    at = lambda h, m: datetime(2026, 11, 20, h, m)
    sym_kind = next(k for k in form.TYPES if 'symbol' in form.FIELDS[k])
    db_routes = [
        ('/day/2026-11-09', ''),
        ('/api/v1/desks/latest', ''),
        ('/themes', ''),
        ('/themes/2026-11-09', ''),
        ('/form', f'type={sym_kind}'),
    ]
    free_routes = [('/', ''), ('/days', ''), ('/guvenilirlik', ''), ('/form', ''), ('/tema', ''), ('/nope', '')]
    for t in (at(23, 40), at(23, 45), at(23, 50)):
        assert all(window_block(p, q, t) and window_block(p, q, t)[0] == 503 for p, q in db_routes)
        assert all(window_block(p, q, t) is None for p, q in free_routes)
    assert all(window_block(p, q, t) is None for p, q in db_routes for t in (at(23, 39), at(23, 51), at(7, 30)))
    assert '23:50' in window_block('/day/2026-11-09', '', at(23, 45))[1] and window_block(
        '/api/v1/desks/latest', '', at(23, 45)
    )[2].startswith('application/json')
    # UI polish 19 Nov: Turkish review time, green "kontrol edildi"
    assert tr_time('2026-11-10T00:41:50') == '10 Kas 2026 00:41' and tr_time('x') == 'x'
    assert '.badge.done{color:var(--green)' in CSS
    # "Önce bak" box: look-first items (high or flagged) in priority order, linked to their cards
    box = look_first_box(items, {})
    assert 'Önce bak (2)' in box and box.index('href="#c1"') >= 0 and 'href="#c2"' in box and 'href="#c4"' not in box
    assert (
        'kontrol et:' in box
        and look_first_box([items[3]], {}) == ''
        and 'id="c1"' in render_day('2026-11-09', items, sectors, {}, {})
    )
    # overview and review history (22 Nov): counts, column chart, flag chart, decisions table
    c = day_counts(items, {'2': {}})
    assert c == {'n': 4, 'look': 2, 'flagged': 1, 'done': 1}
    dstats = all_day_stats(['2026-11-09', '2026-11-10'], {}, load=lambda d: items if d == '2026-11-09' else [])
    ch = column_chart(dstats)
    assert (
        ch.count('<a class="col"') == 2 and 'href="/day/2026-11-09"' in ch and 'class="seg flag" style="flex:1"' in ch
    )
    assert (
        'class="seg look" style="flex:1"' in ch
        and 'class="seg other" style="flex:2"' in ch
        and 'style="height:0%"' in ch
    )
    assert '9 Kas 2026: 4 bildirim · önce bak 2 · kontrol et 1 (kontrol edilen 0)' in ch and column_chart({}) == ''
    many = column_chart({f'2026-10-{d:02d}': {'n': 1, 'look': 0, 'flagged': 0, 'done': 0} for d in range(1, 32)})
    assert many.count('<a class="col"') == CHART_DAYS and 'href="/day/2026-10-01"' not in many  # last 30 only
    rlog = {
        '2': {
            'news_id': '2',
            'day': '2026-11-09',
            'decision': 'reject',
            'note': '<b>not</b>',
            'at': '2026-11-10T09:00:00',
            'reasons': ['amount_not_in_text'],
        },
        '9': {
            'news_id': '9',
            'day': '2026-11-09',
            'decision': 'confirm',
            'note': '',
            'at': '2026-11-10T10:00:00',
            'reasons': [],
        },
    }
    rows = review_rows(rlog, load=lambda d: items)
    assert [r['news_id'] for r, _ in rows] == ['9', '2'] and rows[0][1] is None and rows[1][1]['symbol'] == 'BBB'
    rs = reason_stats(rlog, load=lambda d: items)
    fc = flag_chart(rs)
    assert (
        'tutar metinde geçmiyor' in fc
        and '1 hata · 0 doğru' in fc
        and 'gerekçe kaydedilmemiş' in fc
        and flag_chart({}) == ''
    )
    rv = render_reviews(rows, rs)
    assert '2 karar: 1 bildirimde çıkarım hatalıydı' in rv and 'href="/day/2026-11-09#c2"' in rv and 'listede yok' in rv
    assert (
        '&lt;b&gt;not&lt;/b&gt;' in rv and '<b>not</b>' not in rv and 'Yanlış (çıkarım hatalı)' in rv and '.hbar{' in rv
    )
    assert 'Henüz kontrol kararı yok' in render_reviews([], {})
    ov = render_overview(dstats, items, {}, rows, rs)
    assert (
        all(f'<h2>{n}.' in ov for n in range(1, 7))
        and 'href="/day/2026-11-10"' in ov
        and 'href="/day/2026-11-10#c1"' in ov
    )
    assert 'href="/kontroller"' in ov and 'href="/guvenilirlik"' in ov and ov.count('<div class="tile">') == 7
    assert 'Kayıtlı sabah listesi yok' in render_overview({}, [], {}, [], {}) and '<h2>6.' not in render_overview(
        {}, [], {}, [], {}
    )
    assert (
        '.cols{' not in render_index([]) and not reads_db('/genel') and not reads_db('/kontroller')
    )  # other pages: no chart CSS
    # outside review 22 Nov: request hardening
    assert (
        theme_back('http://127.0.0.1:8765/day/2026-11-09') == '/day/2026-11-09'
        and theme_back('http://localhost//evil.example') == '/'
    )
    assert (
        theme_back('http://evil.example/day/x') == '/'
        and theme_back('http://localhost:8765/form?type=brief') == '/form?type=brief'
    )
    assert theme_back(None) == '/' and theme_back('http://localhost:8765/days?x=1') == '/days'
    assert (
        'şükrü'.encode('utf-8')[:-1].decode('utf-8', errors='replace').startswith('şükr')
    )  # a cut character no longer raises
    assert FILTER_PARAM != MSG_PARAM
    for bad in ('//kotu', '/\\kotu', 'https://kotu', '/genel\r\nX:1', '', '/a\nb', None):
        assert safe_back(bad) == '/genel'
    assert safe_back(f'/day/2026-11-04?{FILTER_PARAM}=1') == f'/day/2026-11-04?{FILTER_PARAM}=1'
    assert (
        with_message(f'/day/2026-11-04?{FILTER_PARAM}=1', 'removed')
        == f'/day/2026-11-04?{FILTER_PARAM}=1&{MSG_PARAM}=removed'
    )
    assert (
        with_message(f'/day/2026-11-04?{FILTER_PARAM}=1&{MSG_PARAM}=old', 'added')
        == f'/day/2026-11-04?{FILTER_PARAM}=1&{MSG_PARAM}=added'
    )
    assert (
        with_message('/genel', 'added') == f'/genel?{MSG_PARAM}=added'
        and with_message(f'/genel?{MSG_PARAM}=old', 'absent') == '/genel'
    )
    assert takip_message(f'{MSG_PARAM}=<script>') == '' and takip_message('') == ''
    assert watchlist.MESSAGES['added'] in takip_message(f'{MSG_PARAM}=added')
    # watchlist day rendering (4b): badge/form, filter, back preservation, escaping, broken warning, byte-identical default
    c_in = render_item(items[0], '2026-11-09', None, watched=True, back='/day/2026-11-09')
    c_out = render_item(items[1], '2026-11-09', None, watched=False, back='/day/2026-11-09')
    assert '<span class="badge">takipte</span>' in c_in and 'value="remove"' in c_in and 'Takipten çıkar' in c_in
    assert 'takipte</span>' not in c_out and 'value="add"' in c_out and 'Takibe al' in c_out
    assert render_item(items[0], '2026-11-09', None) == render_item(
        items[0], '2026-11-09', None, watched=None, back=None
    )
    w_all = render_day('2026-11-09', items, sectors, {}, {}, watch=['AAA'], query=f'{MSG_PARAM}=added')
    assert 'Sadece takip ettiklerim (1)' in w_all and watchlist.MESSAGES['added'] in w_all
    assert '<script>' not in w_all and 'name="symbol" value="&lt;script&gt;"' in w_all
    w_only = render_day('2026-11-09', items, sectors, {}, {}, watch=['AAA'], only_watched=True)
    assert (
        'id="c1"' in w_only
        and 'id="c2"' not in w_only
        and '1 bildirim, 1 masa; kontrol gereken 0, kontrol edilen 0.' in w_only
    )
    assert f'name="back" value="/day/2026-11-09?{FILTER_PARAM}=1"' in w_only
    w_empty = render_day('2026-11-09', items, sectors, {}, {}, watch=['ZZZ'], only_watched=True)
    assert 'takip listenizdeki şirketlerden bildirim yok' in w_empty
    w_broken = render_day('2026-11-09', items, sectors, {}, {}, watch=[], watch_broken=True)
    assert watchlist.MESSAGES['broken'] in w_broken and 'action="/takip"' not in w_broken
    assert (
        html_out == render_day('2026-11-09', items, sectors, {}, {}, watch=None) and 'action="/takip"' not in html_out
    )
    # watchlist layer on the overview (4c): links to the cards, add/remove forms, empty state, escaping, broken file,
    # byte-identical page without a watchlist; maxlength is only a convenience, the server check decides
    ov_w = render_overview(dstats, items, {}, rows, rs, watch=['AAA'], query=f'{MSG_PARAM}=added')
    assert (
        '<h2>Takip ettiklerin</h2>' in ov_w
        and 'href="/day/2026-11-10#c1"' in ov_w
        and watchlist.MESSAGES['added'] in ov_w
    )
    assert 'action="/takip"' in ov_w and 'name="action" value="add"' in ov_w and 'name="action" value="remove"' in ov_w
    assert 'name="back" value="/genel"' in ov_w and 'maxlength="6"' in ov_w
    assert watchlist.normalize('ABCDEFG') == (None, 'bad_code')
    ov_empty = render_overview(dstats, items, {}, rows, rs, watch=['ZZZ'])
    assert 'Son listede takip ettiğin şirketlerden bildirim yok.' in ov_empty
    ov_esc = render_overview(dstats, items, {}, rows, rs, watch=['<script>'])
    assert '<script>' not in ov_esc and 'name="symbol" value="&lt;script&gt;"' in ov_esc
    ov_broken = render_overview(dstats, items, {}, rows, rs, watch=[], watch_broken=True)
    assert watchlist.MESSAGES['broken'] in ov_broken and 'action="/takip"' not in ov_broken
    assert ov == render_overview(dstats, items, {}, rows, rs, watch=None) and 'Takip ettiklerin' not in ov
    # second outside review 22 Nov: Host check (DNS rebinding), ASCII-only back path, no night window on sample data
    assert all(host_ok(h) for h in ('127.0.0.1:8765', 'localhost:8765', 'panel:8765', '127.0.0.1', 'LOCALHOST:8765'))
    assert not any(
        host_ok(h)
        for h in ('evil.example:8765', 'localhost.evil.example', '127.0.0.1.evil.example:80', '', '[bad', None)
    )
    assert safe_back('/day/2026-11-04?x=ş') == '/genel' and safe_back('/genel') == '/genel'
    night = datetime(2026, 11, 20, 23, 45)
    saved_guard = chat.WINDOW_GUARD
    try:
        chat.WINDOW_GUARD = False  # what panel --sample sets: all four checks open at 23:45
        assert all(window_block(p, q, night) is None for p, q in db_routes) and not chat.in_collection_window(night)
        assert chat.ask('x', runner=lambda q: {'answer': 'ok', 'intent': 'help'}, now=night, history=[])['a'] == 'ok'
        assert not form.run({'type': 'zz'}, {'symbols': set()}, runner=lambda s: {'answer': 'ok'}, now=night)[
            'answer'
        ].startswith('Gece')
        chat.WINDOW_GUARD = True  # the real panel: still blocked
        assert (
            window_block(*db_routes[0], night)[0] == 503
            and chat.ask('x', runner=lambda q: {'answer': 'ok'}, now=night, history=[])['error']
        )
        assert form.run({'type': 'zz'}, {'symbols': set()}, runner=lambda s: {'answer': 'ok'}, now=night)[
            'answer'
        ].startswith('Gece')
    finally:
        chat.WINDOW_GUARD = saved_guard
