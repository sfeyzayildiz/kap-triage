'''Tests moved from price_chart.py (v1 self-test).'''
from datetime import datetime, timedelta
from kap_triage.analysis.prices import INDEX
from kap_triage.web.charts import AFTER, big_jump, chart_for_state, chart_html, rebase, svg, window


def test_price_chart():
    import duckdb
    from datetime import date
    con=duckdb.connect()
    con.execute('CREATE TABLE daily_bars (symbol VARCHAR, date DATE, close DOUBLE)')
    con.execute('CREATE TABLE disclosures (symbol VARCHAR, published_at TIMESTAMP)')
    days=[date(2026,9,1)+timedelta(days=i) for i in range(40) if (date(2026,9,1)+timedelta(days=i)).weekday()<5]
    rows=[('AAA',d,100+i) for i,d in enumerate(days)]+[(INDEX,d,1000+i) for i,d in enumerate(days)]
    con.executemany('INSERT INTO daily_bars VALUES (?,?,?)',rows)
    stock=[(d,100+i) for i,d in enumerate(days)]
    pts,mi,base=window(stock,date(2026,9,15))
    assert pts[mi][0]==date(2026,9,15) and base==stock[days.index(date(2026,9,15))-1][1] and len(pts)==mi+AFTER+1
    assert window(stock,date(2027,1,1)) is None
    s=svg(rebase(pts,base),rebase(pts,base),mi)
    assert s.startswith('<svg') and s.count('<polyline')==2 and 'var(--amber)' in s and '<script' not in s
    assert svg([(1,100),(2,101)],[],None)==''
    h=chart_html(con,'AAA',datetime(2026,9,15,19,0))   # after 18:00 -> reaction next trading day
    assert '<figure class="chart">' in h and 'tepki günü 2026-09-16)' in h and '))' not in h and 'AAA +' in h
    assert chart_html(con,'ZZZ',datetime(2026,9,15,10))==''
    h2=chart_html(con,'AAA',None,marks=[date(2026,10,5)])
    assert 'son 29 işlem günü' in h2 and 'turuncu çentik' in h2
    assert big_jump([(1,100),(2,130)]) and not big_jump([(1,100),(2,109)])
    assert chart_for_state({'intent':'search','symbol':'AAA'})==''
