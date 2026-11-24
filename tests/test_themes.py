"""kap_triage/assistant/themes.py: the checks of the v1 self-test in themes.py, on made-up data (no network, no real data)."""

from datetime import date
from kap_triage.assistant.themes import last_clustered, n_weeks, profile, week_start, week_view, weeks


def test_themes():
    assert week_start('2026-11-12 09:30:00') == date(2026, 11, 9) and week_start('2026-11-09') == date(2026, 11, 9)
    assign = [
        {'news_id': '1', 'symbol': 'AAA', 'published_at': '2026-11-02 09:00:00', 'cluster': 0},
        {'news_id': '2', 'symbol': 'BBB', 'published_at': '2026-11-03 10:00:00', 'cluster': 0},
        {'news_id': '3', 'symbol': 'AAA', 'published_at': '2026-11-10 09:00:00', 'cluster': 0},
        {'news_id': '4', 'symbol': 'CCC', 'published_at': '2026-11-11 09:00:00', 'cluster': 1},
        {'news_id': '5', 'symbol': 'CCC', 'published_at': '2026-11-12 08:00:00', 'cluster': 1},
        {'news_id': '6', 'symbol': 'DDD', 'published_at': '2026-11-13 08:00:00', 'cluster': 2},
    ]
    out = {'k': 3, 'themes': {'0': ['savunma', 'teslimat'], '1': [], '2': ['enerji']}, 'assign': assign}
    assert n_weeks(assign) == 2 and n_weeks([]) == 0
    assert profile(assign) == {0: {'n': 3, 'companies': 2}, 1: {'n': 2, 'companies': 1}, 2: {'n': 1, 'companies': 1}}
    assert weeks(assign) == [('2026-11-09', 4), ('2026-11-02', 2)]
    assert last_clustered(assign) == '2026-11-13 08:00:00' and last_clustered([]) is None
    v = week_view(out, '2026-11-09')
    assert [x['cluster'] for x in v] == [
        1,
        2,
        0,
    ]  # 2 docs first; then 1 doc each, higher ratio first (2: 1/0.5, 0: 1/1.5)
    assert v[0]['n'] == 2 and v[0]['companies_week'] == 1 and v[0]['companies_all'] == 1 and v[0]['words'] == []
    assert (
        v[2]['words'] == ['savunma', 'teslimat']
        and abs(v[2]['avg_per_week'] - 1.5) < 1e-9
        and abs(v[1]['ratio'] - 2) < 1e-9
    )
    assert [a['news_id'] for a in v[0]['items']] == ['4', '5']  # oldest first
    assert week_view(out, '2026-10-26') == []
