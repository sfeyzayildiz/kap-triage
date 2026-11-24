"""kap-kart (kap_triage/web/kart.py) with fake model readings and fake judges: no Ollama, no data."""

import subprocess
import sys

from kap_triage.analysis.defence import source_sentence
from kap_triage.analysis.morning import REVIEW_TR as MORNING_TR
import kap_triage.web.kart as kart
from kap_triage.web.kart import (
    EXPECTED,
    REVIEW_TR,
    analyze,
    examples,
    fmt_amount,
    marked,
    render_card_html,
    render_text,
    safe_link,
)

TEXT = 'Toplam 4.000.000 USD tutarında sipariş alınmıştır.'
CLEAN = {'amount': 4000000, 'currency': 'USD', 'needs_review_reasons': []}


def readings(*values):
    """A fake extraction that returns the given readings in order (an exception is raised)."""
    it = iter(values)

    def extract(_text):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return None if v is None else dict(v)

    return extract


def test_failures_are_flagged_never_missing():
    d = analyze('x', readings(RuntimeError('down')), lambda s: 'fact')
    assert d['needs_review_reasons'] == ['run_error'] and d['error'] == 'RuntimeError'
    assert analyze('x', readings(None), lambda s: 'fact')['error'] == 'invalid_output'


def test_second_reading_and_judge():
    # same amount twice (currency case does not matter) -> clean
    assert (
        analyze(TEXT, readings(CLEAN, {'amount': 4000000, 'currency': 'usd'}), lambda s: 'fact')['needs_review']
        is False
    )
    # a different second reading -> two_run_disagree
    assert analyze(TEXT, readings(CLEAN, {'amount': 400000, 'currency': 'USD'}), lambda s: 'fact')[
        'needs_review_reasons'
    ] == ['two_run_disagree']
    # the amount comes from an instruction-like sentence, or is not in the text at all
    assert analyze(TEXT, readings(CLEAN, CLEAN), lambda s: 'instruction')['needs_review_reasons'] == [
        'amount_from_instruction'
    ]
    other = {**CLEAN, 'amount': 9000000}
    assert analyze(TEXT, readings(other, other), lambda s: 'fact')['needs_review_reasons'] == ['amount_not_in_text']


def test_card_is_escaped():
    evil = '<script>alert(1)</script> 5.000.000 TL bedelli <b>iş</b>'
    d = analyze(
        evil,
        readings(*[{'amount': 5000000, 'currency': 'TRY', 'company': '<b>X</b>', 'needs_review_reasons': []}] * 2),
        lambda s: 'fact',
    )
    card = render_card_html(d, evil, safe_link('javascript:alert(1)'))
    assert (
        '<script' not in card
        and '<b>X</b>' not in card
        and 'href="javascript' not in card
        and '&lt;b&gt;X&lt;/b&gt;' in card
    )
    assert 'Uyarı yok.' in render_text(d, evil)


def test_display_helpers():
    assert fmt_amount(2750000) == '2.750.000' and fmt_amount(1250000.5) == '1.250.000,50'
    s, spans = source_sentence(TEXT, 4000000)
    assert '<mark>4.000.000' in marked(s, spans)
    # only kap.org.tr links, with or without www.
    assert safe_link('https://www.kap.org.tr/tr/Bildirim/1') == 'https://www.kap.org.tr/tr/Bildirim/1'
    assert safe_link('https://kap.org.tr/tr/Bildirim/1') == 'https://kap.org.tr/tr/Bildirim/1'
    assert safe_link('http://x.com') is None and safe_link('https://kap.org.tr.evil.example/') is None


def test_examples_and_texts():
    # four trap examples, each with its expected behaviour; every review code has the morning list's text
    assert len(examples()) == 4 and set(EXPECTED) == {p.stem for p in examples()}
    assert all(MORNING_TR.get(code, text) == text for code, text in REVIEW_TR.items())


def test_no_database_or_vendor_code():
    # importing the card loads no database driver and no collection code
    code = (
        'import sys, kap_triage.web.kart; '
        'bad=[m for m in sys.modules if m=="duckdb" or m.startswith("kap_triage.collect")]; print(bad)'
    )
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == '[]'


def test_examples_on_an_empty_folder(monkeypatch, tmp_path, capsys):
    # no example files (e.g. a copy without sample/): a message, not an IndexError
    monkeypatch.setattr(kart, 'EXAMPLES_DIR', tmp_path)
    kart.run_examples(runs=1)
    assert 'no examples' in capsys.readouterr().out
