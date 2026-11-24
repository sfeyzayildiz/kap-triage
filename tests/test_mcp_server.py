"""kap_triage/web/mcp_server.py: the checks of the v1 self-test in mcp_server.py, on made-up data (no network, no real data)."""

from datetime import date
from kap_triage.web.mcp_server import build_state, run_tool


def test_mcp_server():
    ctx = {
        'symbols': {'ASELS', 'SARAE'},
        'last_disclosure': date(2026, 11, 12),
        'last_bar': date(2026, 11, 10),
        'today': date(2026, 11, 14),
    }
    s, e = build_state('company_history', {'symbol': 'asels', 'period': 'son 3 ay'}, ctx)
    assert (
        e is None
        and s['intent'] == 'company'
        and s['symbol'] == 'ASELS'
        and s['period'] == ['2026-08-14', '2026-11-12']
    )
    assert build_state('company_history', {'symbol': 'XXXX'}, ctx)[1].startswith('XXXX')
    assert build_state('company_history', {'symbol': 'ASELS', 'period': 'önceki hafta'}, ctx)[1].startswith(
        'Dönem okunamadı'
    )
    s, _ = build_state('morning_list', {'day': ''}, ctx)
    assert s['intent'] == 'morning' and s['day'] == '2026-11-12' and s['note'] is None
    s, _ = build_state('morning_list', {'day': '2026-12-01'}, ctx)
    assert s['day'] == '2026-11-12' and 'henüz toplanmadı' in s['note']
    s, _ = build_state('why_moved', {'symbol': 'SARAE', 'day': '2026-09-18'}, ctx)
    assert s['day'] == '2026-09-18' and s['note'] is None
    assert build_state('why_moved', {'symbol': 'SARAE', 'day': '18.09.2026'}, ctx)[1].startswith('Tarih')
    assert build_state('search_disclosures', {'query': ' '}, ctx)[1].startswith('Arama')
    assert build_state('company_brief', {}, ctx)[1].startswith('Bu araç')
    assert build_state('nope', {}, ctx)[1] == 'unknown tool nope'
    got = []
    out = run_tool('search_disclosures', {'query': 'Irak'}, ctx, runner=lambda st: got.append(st) or {'answer': 'ok'})
    assert out == 'ok' and got[0]['intent'] == 'search' and got[0]['query'] == 'Irak'
    assert (
        run_tool('search_disclosures', {'query': 'Irak'}, ctx, runner=lambda st: 1 / 0)
        == 'Araç hatası: ZeroDivisionError'
    )
