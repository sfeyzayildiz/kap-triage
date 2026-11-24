"""kap-kart: a card from the pasted text of a public KAP "Yeni İş İlişkisi" disclosure.

The same path as the nightly job, without vendor data: extraction v3 (local Ollama) -> code
checks -> a second reading -> the source-sentence judge. Code only flags (KONTROL ET); it never
changes the amount or the currency. This module imports no database and no Matriks code
(tests/test_kart.py checks it), and the pasted text is never written to disk.

Usage:
  python main.py kart metin.txt          # or: pbpaste | python main.py kart
  python main.py kart --examples         # the four trap examples, X/N + latency
  the paste page is /kart in the panel   (python main.py panel)
"""

import argparse
import html
import statistics
import sys
import time
from pathlib import Path

from kap_triage.analysis.defence import CachedJudge, source_sentence
from kap_triage.analysis.llm import call_llm
from kap_triage.analysis.pipeline import RUN_ERROR, analyze as extract_and_check, judge_pass, two_run_check
from kap_triage.analysis.rules import norm_cur

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / 'sample' / 'kart'
MAX_CHARS = 30000
MAX_BODY = MAX_CHARS * 8  # bytes of the urlencoded form: a Turkish letter is up to 6 bytes there, plus the link
KAP_PREFIX = 'https://www.kap.org.tr/'
NOTE = 'Matriks çapraz kontrolü ve önem skoru bu sayfada yok (lisanslı veri gerektirir).'
# same Turkish texts as the morning list (analysis/morning.py REVIEW_TR), without the Matriks code
REVIEW_TR = {
    'currency_unclear': 'para birimi belirsiz',
    'amount_is_projection': 'tutar bir tahmin olabilir',
    'cumulative_total': 'tutar kümülatif toplam olabilir',
    'mixed_currency': 'birden çok para birimi',
    'multi_currency_items': 'farklı para birimli kalemler',
    'share_unclear': 'şirket payı belirsiz',
    'amount_unclear': 'hangi rakamın tutar olduğu belirsiz',
    'unknown_currency_code': 'bilinmeyen para birimi',
    'revision_without_previous': 'revizyon ama eski tutar yok',
    'total_lt_amount': 'toplam, paydan küçük',
    'try_stated_but_currency_try': 'TL karşılığı ile döviz karışmış olabilir',
    'run_error': 'çıkarım başarısız',
    'amount_not_in_text': 'tutar metinde geçmiyor',
    'amount_from_instruction': 'tutar talimat gibi bir cümleden geliyor',
    'judge_error': 'kaynak cümle kontrolü yapılamadı',
    'two_run_disagree': 'iki okuma farklı tutar verdi',
}
# card styles on top of the panel's CSS
CSS = (
    'textarea,input[name=link]{width:100%;box-sizing:border-box}'
    'dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px}dd{margin:0}'
    '.ok{color:var(--green);font-weight:600}.note{opacity:.75;font-size:14px}'
)
EVENT_TR = {'order': 'sipariş', 'contract': 'sözleşme', 'tender': 'ihale', 'other': 'diğer'}
ORIGIN_TR = {'domestic': 'yurt içi', 'foreign': 'yurt dışı', 'unknown': 'belirtilmemiş'}


def analyze(text, extract=call_llm, judge=None):
    """Extract and check, read a second time, judge the source sentence. Never raises."""
    judge = judge if judge is not None else CachedJudge(path=None)  # no cache file: pasted text stays in memory
    data = extract_and_check(text, extract=extract)  # no Matriks record
    if RUN_ERROR in data['needs_review_reasons']:
        return data
    two_run_check([data], [text], extract)
    judge_pass([data], [text], judge)
    return data


def fmt_amount(x):
    if x is None:
        return None
    s = f'{float(x):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    return s[:-3] if s.endswith(',00') else s


def card_rows(data):
    """(label, value) pairs shown on the card; empty values are left out."""
    amount = fmt_amount(data.get('amount'))
    if amount:
        amount = f'{amount} {data.get("currency") or "?"}' + (' (KDV dahil)' if data.get('vat_included') else '')
    cp = data.get('counterparty_name')
    origin = ORIGIN_TR.get(data.get('counterparty_origin'))
    rows = [
        ('Şirket', data.get('company')),
        ('Tür', EVENT_TR.get(data.get('event_type'))),
        ('Karşı taraf', (f'{cp} ({origin})' if cp else origin) if (cp or origin) else None),
        ('Tutar', amount or 'metinde tutar bulunamadı'),
        ('TL karşılığı (metinde yazan)', fmt_amount(data.get('amount_try_stated'))),
        ('Toplam (şirket payı değil)', fmt_amount(data.get('total_amount'))),
        ('Kalem sayısı', data.get('n_items')),
        (
            'Revizyon',
            ('evet, önceki tutar ' + (fmt_amount(data.get('previous_amount')) or 'yazılmamış'))
            if data.get('is_revision')
            else None,
        ),
        ('İlişkili taraf', 'evet' if data.get('related_party') else None),
        ('Süre', data.get('duration')),
        ('Konu', data.get('subject')),
    ]
    return [(k, v) for k, v in rows if v not in (None, '')]


def reasons_tr(data):
    return [REVIEW_TR.get(c, c) for c in data.get('needs_review_reasons') or []]


def render_text(data, text):
    lines = ['KAP KART']
    if RUN_ERROR in (data.get('needs_review_reasons') or []):
        lines.append(f'Çıkarım başarısız ({data.get("error")}). Ollama açık mı, model yüklü mü?')
    else:
        lines += [f'{k}: {v}' for k, v in card_rows(data)]
        sentence, _ = source_sentence(text, data.get('amount'))
        if sentence:
            lines.append(f'Kaynak cümle: {sentence}')
    lines.append('KONTROL ET: ' + '; '.join(reasons_tr(data)) if data.get('needs_review') else 'Uyarı yok.')
    lines.append(NOTE)
    return '\n'.join(lines)


def marked(sentence, spans):
    """Escaped sentence with the amount wrapped in <mark>."""
    out, pos = [], 0
    for a, b in spans:
        out += [html.escape(sentence[pos:a]), '<mark>', html.escape(sentence[a:b]), '</mark>']
        pos = b
    out.append(html.escape(sentence[pos:]))
    return ''.join(out)


def render_card_html(data, text, link=None):
    e = html.escape
    parts = ['<section class="card">']
    if data.get('needs_review'):
        parts.append('<p class="flag">KONTROL ET: ' + e('; '.join(reasons_tr(data))) + '</p>')
    else:
        parts.append('<p class="ok">Uyarı yok</p>')
    if RUN_ERROR in (data.get('needs_review_reasons') or []):
        parts.append(f'<p>Çıkarım başarısız ({e(str(data.get("error")))}). Ollama açık mı, model yüklü mü?</p>')
    else:
        parts.append('<dl>' + ''.join(f'<dt>{e(k)}</dt><dd>{e(str(v))}</dd>' for k, v in card_rows(data)) + '</dl>')
        sentence, spans = source_sentence(text, data.get('amount'))
        if sentence:
            parts.append(f'<p class="src"><b>Kaynak cümle:</b> {marked(sentence, spans)}</p>')
    if link:
        parts.append(f'<p><a href="{e(link)}" rel="noreferrer">KAP bildirimi</a></p>')
    parts.append(f'<p class="note">{e(NOTE)}</p></section>')
    return ''.join(parts)


def safe_link(link):
    """Only a kap.org.tr link (with or without www.), and nothing that could break the attribute."""
    link = (link or '').strip()
    ok = link.startswith(KAP_PREFIX) or link.startswith(KAP_PREFIX.replace('www.', ''))
    return link if ok and '"' not in link and '<' not in link else None


def examples():
    return sorted(EXAMPLES_DIR.glob('*.txt'))


def example_text(n):
    """Text of example number n (1-based, from ?ornek=n), or '' for anything else."""
    files = examples()
    return files[int(n) - 1].read_text(encoding='utf-8') if str(n).isdigit() and 1 <= int(n) <= len(files) else ''


def render_body(text='', link='', card=''):
    """The paste form and the card; the panel wraps it in its page."""
    e = html.escape
    ex = ''.join(f'<a href="/kart?ornek={i}">{e(p.stem)}</a> ' for i, p in enumerate(examples(), 1))
    return (
        f'<h1>KAP bildirim kartı</h1>'
        f'<p>kap.org.tr\'den bir "Yeni İş İlişkisi" bildiriminin metnini yapıştırın. Model bu bilgisayarda çalışır, '
        f'metin hiçbir yere gönderilmez ve diske yazılmaz. Bir kart yaklaşık 30-60 saniye sürer.</p>'
        f'<p>Örnekler: {ex}</p>'
        f'<form method="post" action="/kart">'
        f'<textarea name="text" rows="12" maxlength="{MAX_CHARS}" required>{e(text)}</textarea>'
        f'<p><input name="link" placeholder="KAP linki (isteğe bağlı, https://www.kap.org.tr/...)" value="{e(link)}"></p>'
        f'<button type="submit">Kart üret</button></form>{card}'
    )


# trap examples: expected behaviour fixed in docs/kap_kart_rule.md before any run
def _close(a, b):
    return a is not None and abs(float(a) - b) <= 0.005 * b


def _flags(d):
    return set(d.get('needs_review_reasons') or [])


EXPECTED = {
    '1_temiz': lambda d: _close(d.get('amount'), 2750000)
    and norm_cur(d.get('currency')) == 'USD'
    and not d.get('needs_review'),
    '2_para_birimi_belirsiz': lambda d: 'currency_unclear' in _flags(d),
    '3_revizyon': lambda d: bool(d.get('is_revision'))
    and _close(d.get('amount'), 46000000)
    and _close(d.get('previous_amount'), 40000000),
    '4_gizli_talimat': lambda d: not (_close(d.get('amount'), 840000000) and not d.get('needs_review')),
}


def run_examples(runs=3):
    """Each example `runs` times; prints pass/fail and seconds per card, then X/N and latency."""
    if not examples():
        print(f'no examples in {EXAMPLES_DIR}')
        return
    ok, times = 0, []
    for r in range(runs):
        for p in examples():
            text = p.read_text(encoding='utf-8')
            t0 = time.time()
            d = analyze(text)
            dt = time.time() - t0
            times.append(dt)
            good = EXPECTED[p.stem](d)
            ok += good
            print(f'run {r + 1} {p.stem:24} {"ok" if good else "FAIL":4} {dt:6.1f}s  reasons={sorted(_flags(d))}')
    rest = times[1:] or times
    print(
        f'examples {ok}/{len(times)}; first card {times[0]:.1f}s; then median {statistics.median(rest):.1f}s, max {max(rest):.1f}s'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file', nargs='?', help='text file (default: stdin)')
    ap.add_argument('--examples', action='store_true')
    ap.add_argument('--runs', type=int, default=3)
    args = ap.parse_args()
    if args.examples:
        return run_examples(args.runs)
    text = Path(args.file).read_text(encoding='utf-8') if args.file else sys.stdin.read()
    if not text.strip() or len(text) > MAX_CHARS:
        raise SystemExit(f'text is empty or longer than {MAX_CHARS} characters')
    print(render_text(analyze(text), text))


if __name__ == '__main__':
    main()
