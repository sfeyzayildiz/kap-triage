"""kap_triage/web/reliability.py: the checks of the v1 self-test in reliability.py, on made-up data (no network, no real data)."""

from kap_triage.web.reliability import ATTACK, bars, paired, render_body, upper95


def test_reliability():
    assert abs(upper95(1, 100) - 0.0466) < 0.0005 and abs(upper95(0, 100) - 0.0295) < 0.0005  # notes: 4.7% and 3.0%
    assert abs(upper95(0, 18) - 0.153) < 0.001 and upper95(5, 5) == 1.0  # notes: 0/18 -> 15.3%
    s = bars([('A', 4, 8.8, False, '4/100', 't'), ('<b>', 1, 4.7, True, '1/100', 't')], 25, 'u')
    assert (
        '100 bildirimde sessiz hata' in s
        and '>15</text>' in s
        and s.count('<rect') == 2
        and 'var(--accent)' in s
        and '&lt;b&gt;' in s
        and '<b>' not in s
        and '<script' not in s
    )
    p = paired(ATTACK)
    assert p.count('<rect') == 6 and '0/18 savunmalı' in p and '%100' in p
    body = render_body('<nav></nav>')
    assert body.count('<figure class="rel">') == 3 and body.count('<summary>Tablo</summary>') == 3 and '%4,7' in body
    assert (
        body.count('<td>reddedildi</td>') == 3 and '29/185&#x27;i' in body and '<h2>4.' in body
    )  # 2 attack rows + scope v2
