"""Small inline SVG price chart for the panel: stock vs XU100 around a disclosure.

Both series are rebased to 100 at the last close before the reaction day (the first trading day the
market could react, price_moves.reaction_day), so the gap between the lines is the move against the
index. Display only: no new measurement, no JavaScript, no external file; colours come from the
panel's CSS variables. Prices are unadjusted; a daily move above the split threshold is flagged.

Usage:
"""

from datetime import datetime, timedelta

from kap_triage.analysis.prices import INDEX, SPLIT_JUMP, load_closes, reaction_day
from kap_triage.settings import settings

DB_PATH = settings.path('kap.duckdb')
W, H, PAD = 360, 120, 10
BEFORE, AFTER = 10, 10  # trading days around the reaction day
RECENT = 30  # trading days for a company chart without one disclosure


def tr_pct(x):
    return ('+' if x >= 0 else '') + f'{x:.1f}'.replace('.', ',') + '%'


def rebase(points, base_close):
    return [(d, c / base_close * 100) for d, c in points]


def window(stock, mark_day, before=BEFORE, after=AFTER):
    """(points, index of the mark, base close) around the first trading day >= mark_day; None if no bar."""
    days = [d for d, _ in stock]
    later = [i for i, d in enumerate(days) if d >= mark_day]
    if not later:
        return None
    i = later[0]
    lo = max(0, i - before)
    base = stock[i - 1][1] if i > 0 else stock[i][1]
    return stock[lo : i + after + 1], i - lo, base


def svg(stock, index, mark_i=None):
    """Two rebased series on the stock's trading days; mark_i = position of the reaction day."""
    if len(stock) < 3:
        return ''
    idx = dict(index)
    lo = min(min(v for _, v in stock), min((idx[d] for d, _ in stock if d in idx), default=100))
    hi = max(max(v for _, v in stock), max((idx[d] for d, _ in stock if d in idx), default=100))
    if hi - lo < 1e-9:
        hi, lo = hi + 1, lo - 1
    n = len(stock)
    x = lambda i: PAD + i * (W - 2 * PAD) / (n - 1)
    y = lambda v: PAD + (hi - v) * (H - 2 * PAD) / (hi - lo)
    pts = lambda series: ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in series)
    s_line = pts(list(enumerate(v for _, v in stock)))
    i_line = pts([(i, idx[d]) for i, (d, _) in enumerate(stock) if d in idx])
    parts = [
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Hisse ve XU100, bildirim öncesine göre">',
        f'<line x1="{PAD}" x2="{W - PAD}" y1="{y(100):.1f}" y2="{y(100):.1f}" style="stroke:var(--line);stroke-width:1"/>',
    ]
    if mark_i is not None:
        parts.append(
            f'<line x1="{x(mark_i):.1f}" x2="{x(mark_i):.1f}" y1="{PAD}" y2="{H - PAD}" '
            'style="stroke:var(--amber);stroke-width:1.5;stroke-dasharray:3 3"/>'
        )
    parts.append(
        f'<polyline points="{i_line}" style="fill:none;stroke:var(--muted);stroke-width:1.5;stroke-dasharray:5 3"/>'
    )
    parts.append(f'<polyline points="{s_line}" style="fill:none;stroke:var(--accent);stroke-width:2.2"/>')
    parts.append('</svg>')
    return ''.join(parts)


def big_jump(points):
    return any(abs(c / p - 1) > SPLIT_JUMP for (_, p), (_, c) in zip(points, points[1:]))


def chart_html(con, symbol, published_at=None, marks=()):
    """Figure around a disclosure (published_at) or over the last RECENT trading days (with marks)."""
    from html import escape as e

    if published_at is not None:
        start, end = published_at.date() - timedelta(days=40), published_at.date() + timedelta(days=40)
    else:
        last = con.execute('SELECT max(date) FROM daily_bars WHERE symbol=?', [symbol]).fetchall()[0][0]
        if last is None:
            return ''
        start, end = last - timedelta(days=RECENT * 2), last
    series = load_closes(con, start, end, [symbol])
    stock, index = series.get(symbol, []), series.get(INDEX, [])
    if len(stock) < 3:
        return ''
    if published_at is not None:
        r = reaction_day(published_at, [d for d, _ in stock])
        w = window(stock, r) if r else None
        if not w:
            return ''
        pts, mark_i, base = w
        ib = dict(index).get(pts[mark_i - 1][0] if mark_i > 0 else pts[0][0])  # index close on the same base day
        cap = f'bildirimden önceki kapanış = 100 · turuncu çizgi: tepki günü {r}'
    else:
        pts, mark_i = stock[-RECENT:], None
        base = pts[0][1]
        ib = dict(index).get(pts[0][0])
        cap = f'son {len(pts)} işlem günü, ilk gün = 100'
    if not ib:
        return ''
    s = rebase(pts, base)
    ix = rebase([(d, c) for d, c in index if pts[0][0] <= d <= pts[-1][0]], ib)
    out = svg(s, ix, mark_i)
    if marks:
        days = [d for d, _ in pts]
        xs = [days.index(d) for d in marks if d in days]
        if xs:  # small ticks for the company's disclosures in the window
            ticks = ''.join(
                f'<line x1="{PAD + i * (W - 2 * PAD) / (len(days) - 1):.1f}" x2="{PAD + i * (W - 2 * PAD) / (len(days) - 1):.1f}" '
                f'y1="{H - PAD}" y2="{H - 2}" style="stroke:var(--amber);stroke-width:2"/>'
                for i in xs
            )
            out = out.replace('</svg>', ticks + '</svg>')
            cap += ' · turuncu çentik: yeni iş ilişkisi bildirimi'
    warn = (
        ' Fiyatlarda bölünme/bedelsiz olabilecek büyük bir sıçrama var; grafiği yorumlarken dikkat.'
        if big_jump(pts)
        else ''
    )
    return (
        f'<figure class="chart">{out}<figcaption class="muted">'
        f'<span class="k s">━</span> {e(symbol)} {tr_pct(s[-1][1] - 100)} · <span class="k i">┅</span> XU100 '
        f'{tr_pct(ix[-1][1] - 100) if ix else "-"} ({e(cap)}).{e(warn)}</figcaption></figure>'
    )


def charts_for_items(items, db=DB_PATH):
    """{news_id: figure html} for morning-list items (one short read-only connection); errors -> no chart."""
    import duckdb
    import os

    if not items or not os.path.exists(db):
        return {}
    out = {}
    con = duckdb.connect(db, read_only=True)
    try:
        for it in items:
            try:
                out[it['news_id']] = chart_html(con, it['symbol'], datetime.fromisoformat(str(it['published_at'])))
            except Exception:
                out[it['news_id']] = ''
    finally:
        con.close()
    return out


def chart_for_state(state, db=DB_PATH):
    """Figure for a guided-form answer: why_moved around the day, brief over the last trading days."""
    import duckdb
    import os

    kind, sym = state.get('intent'), state.get('symbol')
    if kind not in ('why_moved', 'brief') or not sym or not os.path.exists(db):
        return ''
    con = duckdb.connect(db, read_only=True)
    try:
        if kind == 'why_moved':
            day = datetime.fromisoformat(state['day']).replace(hour=10)
            return chart_html(con, sym, day)
        marks = [
            r[0]
            for r in con.execute(
                'SELECT DISTINCT CAST(published_at AS DATE) FROM disclosures WHERE symbol=?', [sym]
            ).fetchall()
        ]
        return chart_html(con, sym, None, marks=marks)
    finally:
        con.close()
