"""Morning list: one command from a day's disclosures to a ranked report with KAP links.

Steps: extraction v3 + code checks (pipeline.py) -> importance score (importance.py)
-> similar earlier disclosures of the company (rag_index.py)
-> price reaction (price_moves.py) -> company history (SQL) -> Markdown report.
The report contains amounts, so it goes to data/morning_<date>.md; stdout shows only counts.

Usage:
  python -m kap_triage.analysis.morning --date 2026-10-30
  python -m kap_triage.analysis.morning --date 2026-10-28 --from-pipeline data/pipeline_2026-10-28.jsonl
"""

import argparse
import json
import os
from datetime import date, datetime, timedelta

import duckdb

from kap_triage.analysis.importance import score_result
from kap_triage.analysis.prices import INDEX, abnormal, daily_returns, event_reaction, load_closes
from kap_triage.assistant.search import similar_earlier, update as rag_update
from kap_triage.settings import settings

DB_PATH = settings.path('kap.duckdb')
HISTORY_DAYS = 365
SIMILAR_K = 2

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
    'amount_vs_matriks': 'tutar Matriks kaydından 2 kattan fazla farklı',
    'amount_not_in_text': 'tutar metinde geçmiyor',
    'amount_from_instruction': 'tutar talimat gibi bir cümleden geliyor',
    'judge_error': 'kaynak cümle kontrolü yapılamadı',
    'two_run_disagree': 'iki okuma farklı tutar verdi',
}
TWO_RUN = True  # ADOPT_TWO_RUN (docs/set_d_rule.md): nightly / command-line list reads every disclosure twice
LEVEL_TR = {'high': 'yüksek', 'medium': 'orta', 'low': 'düşük'}


def tr_num(x, digits=0):
    s = f'{x:,.{digits}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def reason_text(r):
    code = r['code']
    if code == 'size_vs_history':
        return f'şirketin önceki işlerinin medyanının {tr_num(r["ratio"], 1)} katı ({r["n_history"]} iş)'
    if code == 'size_vs_revenue':
        src = 'ilgili bilanço' if r.get('source') == 'own' else 'son yıl sonu bilançosu'
        text = f'tutar / şirketin yıllık geliri: %{tr_num(r["ratio"] * 100, 1)} ({src})'
        return text + (' - olağandışı oran, tutarı kontrol edin' if r.get('extreme') else '')
    if code == 'size_absolute':
        return f'TL karşılığına göre büyüklük (şirketin önceki iş sayısı az: {r["n_history"]})'
    return {
        'foreign_currency': f'döviz ({r.get("currency")})',
        'foreign_counterparty': 'yurt dışı karşı taraf',
        'long_contract': f'süre {tr_num(r.get("years", 0), 1)} yıl',
        'related_party': 'ilişkili taraf (grup içi)',
        'revision': 'revizyon: yalnızca artış puanlandı',
        'no_amount': 'tutar yok',
        'no_rate': f'{r.get("currency")} için kur yok, büyüklük hesaplanmadı',
        'no_increase': 'tutar artmamış',
    }.get(code, code)


def history(con, symbol, published_at):
    """Earlier disclosures of the company in the last HISTORY_DAYS: count, updates, last date."""
    rows = con.execute(
        """SELECT count(*),count(*) FILTER (WHERE is_update OR is_correction),max(published_at)
        FROM disclosures WHERE symbol=? AND published_at<? AND published_at>=?""",
        [symbol, published_at, published_at - timedelta(days=HISTORY_DAYS)],
    ).fetchall()[0]
    return {'n': rows[0], 'n_updates': rows[1], 'last': str(rows[2].date()) if rows[2] else None}


def reaction(con, symbol, published_at):
    series = load_closes(
        con, published_at.date() - timedelta(days=150), published_at.date() + timedelta(days=10), [symbol]
    )
    if symbol not in series or INDEX not in series:
        return {'status': 'no_symbol_bars'}
    ar = abnormal(daily_returns(series[symbol]), daily_returns(series[INDEX]))
    return event_reaction(ar, [d for d, _ in series[INDEX]], published_at)


def reaction_text(rx):
    if rx['status'] == 'too_early':
        return 'henüz tepki günü yok (fiyat verisi bu tarihe ulaşmıyor)'
    if rx['status'] in ('no_symbol_bars', 'no_bar'):
        return 'fiyat verisi yok'
    text = f"tepki günü {rx['t0']}: XU100'e göre {'+' if rx['ar0'] >= 0 else ''}{tr_num(rx['ar0'] * 100, 1)}%"
    if rx.get('z0') is not None:
        text += f' (z {tr_num(rx["z0"], 1)})'
    if rx.get('possible_split'):
        text += ' - olası bölünme/bedelsiz, hareketi yorumlama'
    return text


ORDER_V2 = (
    True  # docs/importance_v2_rule.md: ADOPT_V2 (round 2, 12 days: C3 AUC 0.877 vs v1 0.792, top-1 11 vs 5.5 of 12)
)


def priority(item):
    """Look-first items (high or flagged) on top; inside each group v2 = long contract first, then TRY amount."""
    imp = item['importance']
    group = not (imp['needs_review'] or imp['level'] == 'high')
    if not ORDER_V2:
        return (group, -imp['score'])
    long = 'long_contract' in {r.get('code') for r in imp.get('reasons', [])}
    a = imp.get('amount_try')
    return (group, not long, -(a if a is not None else float('-inf')))


def render(day, items):
    look = [i for i in items if i['importance']['needs_review'] or i['importance']['level'] == 'high']
    lines = [
        f'# Sabah listesi: {day}',
        '',
        f'{len(items)} bildirim; önce bakılacak: {len(look)} (yüksek önem veya kontrol gerekli).',
        '',
    ]
    if not items:
        lines.append('Bugün yeni iş ilişkisi bildirimi yok.')
    for n, item in enumerate(sorted(items, key=priority), 1):
        imp = item['importance']
        from kap_triage.assistant.names import company_label

        lines.append(f'## {n}. {company_label(item["symbol"])} - {LEVEL_TR[imp["level"]]} (skor {imp["score"]})')
        lines.append(f'- KAP: {item["kap_url"]}')
        if item.get('amount') is not None:
            lines.append(f'- Tutar: {tr_num(item["amount"], 0)} {item.get("currency") or ""}'.rstrip())
        if item.get('subject'):
            lines.append(f'- Konu: {item["subject"]}')
        reasons = [reason_text(r) for r in imp['reasons']]
        if reasons:
            lines.append('- Neden: ' + '; '.join(reasons))
        if imp['needs_review']:
            codes = [REVIEW_TR.get(c, c) for c in imp['needs_review_reasons']]
            lines.append('- KONTROL ET: ' + '; '.join(codes) + " (metni KAP'ta okuyun)")
        lines.append(f'- Fiyat: {reaction_text(item["reaction"])}')
        h = item['history']
        lines.append(
            f'- Geçmiş: son 12 ayda {h["n"]} bildirim'
            + (f', {h["n_updates"]} güncelleme/düzeltme' if h['n_updates'] else '')
            + (f', sonuncusu {h["last"]}' if h['last'] else '')
        )
        for s in item.get('similar', []):
            lines.append(
                f'- Benzer eski bildirim: {s["published_at"][:10]} (benzerlik {tr_num(s["score"], 2)}) {s["kap_url"]}'
            )
        lines.append('')
    lines.append(
        'Kaynak: KAP bildirimleri ve Matriks verisi. Skor kurallı bir sıralamadır, tahmin değildir; '
        'çıkarım hatası olabilir, karar öncesi KAP metnini okuyun.'
    )
    return '\n'.join(lines) + '\n'


def extract_day(day, two_run=False, provenance=False):
    """Run extraction v3 + code checks on every disclosure of day.
    two_run: second extraction per disclosure (ADOPT_TWO_RUN, docs/set_d_rule.md); only the batch
    command line turns it on, interactive callers (agent) stay single-run for latency."""
    from kap_triage.analysis.pipeline import analyze_rows, defence_context, load_rows

    rows = load_rows(str(day), None)
    matriks, judge = defence_context([r[0] for r in rows])
    found = analyze_rows(rows, matriks, judge, two_run=two_run, provenance=provenance)
    results = []
    for (news_id, url, symbol, published_at, text), res in zip(rows, found):
        results.append(
            {**res, 'news_id': str(news_id), 'kap_url': url, 'symbol': symbol, 'published_at': str(published_at)}
        )
    return results


def enrich(results):
    """Add importance, price reaction, history and similar earlier disclosures."""
    index, _ = rag_update()  # embeds only disclosures not yet in the index
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        items = []
        for r in results:
            published = datetime.fromisoformat(r['published_at'])
            items.append(
                {
                    **r,
                    'importance': score_result(con, r),
                    'reaction': reaction(con, r['symbol'], published),
                    'history': history(con, r['symbol'], published),
                    'similar': similar_earlier(index, r['news_id'], k=SIMILAR_K),
                }
            )
    finally:
        con.close()
    return items


def save(day, items):
    out_path = settings.path(f'morning_{day}.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(render(str(day), items))
    with open(settings.path(f'morning_{day}.jsonl'), 'w', encoding='utf-8') as f:
        for i in items:
            f.write(json.dumps(i, ensure_ascii=False, default=str) + '\n')
    return out_path


def load_saved(day):
    """Items of an earlier morning run, or None."""
    path = settings.path(f'morning_{day}.jsonl')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', type=date.fromisoformat)
    ap.add_argument('--from-pipeline', help='reuse a pipeline output instead of running the LLM')
    ap.add_argument(
        '--allow-window',
        action='store_true',
        help='only for the nightly job (run_morning), which runs right after the collection',
    )
    args = ap.parse_args()
    if not args.date:
        ap.error('give --date')
    now = datetime.now()
    if now.hour == 23 and 40 <= now.minute <= 50 and not args.allow_window:
        raise SystemExit('collection window, try after 23:50')

    if args.from_pipeline:
        with open(args.from_pipeline, encoding='utf-8') as f:
            results = [json.loads(l) for l in f if l.strip()]
        other = sum(r['published_at'][:10] != str(args.date) for r in results)
        if other:
            raise SystemExit(f'{other} rows in {args.from_pipeline} are not from {args.date}')
    else:
        results = extract_day(args.date, two_run=TWO_RUN, provenance=True)
    items = enrich(results)
    out_path = save(args.date, items)
    look = sum(i['importance']['needs_review'] or i['importance']['level'] == 'high' for i in items)
    run_errors = sum('run_error' in (i.get('needs_review_reasons') or []) for i in items)
    print(
        f'disclosures={len(items)} look_first={look} flagged={sum(i["importance"]["needs_review"] for i in items)} '
        f'run_errors={run_errors} -> {out_path}'
    )


if __name__ == '__main__':
    main()
