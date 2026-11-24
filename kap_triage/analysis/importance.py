"""Importance score v1 for pipeline results (rules in docs/importance_score.md).

The score is computed in code from extracted facts and our own database.
It never changes the extracted fields; needs_review is passed through as a reliability flag.
Output goes to data/triage_<label>.jsonl. Stdout shows only counts.

Usage:
  python -m kap_triage.analysis.importance --pipeline data/pipeline_2026-10-28.jsonl
"""

import argparse
import json
import os
import re
from datetime import date, timedelta

import duckdb
from kap_triage.settings import settings

DB_PATH = settings.path('kap.duckdb')
USE_REVENUE = True  # gates passed on refreshed prod data 2026-11-10 (docs/revenue_ratio_rule.md, PROJECT_NOTES)
EXTREME_RATIO = 5.0
RATE_DAYS = 10
MIN_HISTORY = 3
TRY_CODES = ('TRY', 'TL')

DURATION_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*(yıl|yil|sene|year|ay|month|gün|gun|day)', re.I)
UNIT_YEARS = {
    'yıl': 1,
    'yil': 1,
    'sene': 1,
    'year': 1,
    'ay': 1 / 12,
    'month': 1 / 12,
    'gün': 1 / 365,
    'gun': 1 / 365,
    'day': 1 / 365,
}


# docs/fields_rule.md (13 Nov): long contract kept (3/50 errors); foreign counterparty and related party
# were measured too unreliable (7/50, 5/50) and give no points.


def duration_years(text):
    """Longest duration written in the text, in years; None if none is found."""
    best = None
    for num, unit in DURATION_RE.findall(text or ''):
        value = float(num.replace(',', '.'))
        if value >= 1900:
            continue  # a calendar year ("2026 yılı sonuna kadar"), not a length
        years = value * UNIT_YEARS[unit.lower()]
        best = years if best is None else max(best, years)
    return best


def fx_rate(con, currency, day):
    """Central bank rate for currency, latest on or before day (at most RATE_DAYS back)."""
    if currency in TRY_CODES:
        return 1.0
    rows = con.execute(
        """SELECT tcmb_ex_rt FROM new_business
        WHERE trim(upper(cur))=? AND tcmb_ex_rt>0 AND date<=? AND date>=?
        ORDER BY date DESC LIMIT 1""",
        [currency, day, day - timedelta(days=RATE_DAYS)],
    ).fetchall()
    if rows:
        return rows[0][0]
    return None


def company_baseline(con, symbol, day):
    """Median TRY value of the company's deals before day, and how many there were."""
    rows = con.execute(
        """SELECT median(CASE WHEN trim(upper(cur)) IN ('TRY','TL') THEN amount ELSE amount*tcmb_ex_rt END),count(*)
        FROM new_business WHERE sym=? AND date<? AND amount>0
        AND (trim(upper(cur)) IN ('TRY','TL') OR tcmb_ex_rt>0)""",
        [symbol, day],
    ).fetchall()
    return rows[0]


def revenue_base(con, kap_url, symbol, day):
    """(revenue, source): own record if shf_ret > 0, else the company's latest December period on or before day."""
    rows = con.execute('SELECT shf_ret FROM new_business WHERE url=? AND shf_ret>0', [kap_url]).fetchall()
    if rows:
        return rows[0][0], 'own'
    rows = con.execute(
        """SELECT shf_ret FROM new_business WHERE sym=? AND per%100=12 AND shf_ret>0 AND date<=?
        ORDER BY date DESC, per DESC LIMIT 1""",
        [symbol, day],
    ).fetchall()
    return (rows[0][0], 'december') if rows else (None, None)


def revenue_points(amount_try, revenue, source):
    if not revenue or amount_try is None or amount_try <= 0:
        return 0, None
    ratio = amount_try / revenue
    points = 3 if ratio >= 0.10 else 2 if ratio >= 0.03 else 1 if ratio >= 0.01 else 0
    reason = {'code': 'size_vs_revenue', 'ratio': round(ratio, 4), 'source': source}
    if ratio > EXTREME_RATIO:
        reason['extreme'] = True
    return points, reason


def size_points(amount_try, baseline, n_history):
    if amount_try is None or amount_try <= 0:
        return 0, None
    if n_history >= MIN_HISTORY and baseline:
        ratio = amount_try / baseline
        points = 3 if ratio >= 3 else 2 if ratio >= 1.5 else 1 if ratio >= 0.5 else 0
        return points, {'code': 'size_vs_history', 'ratio': round(ratio, 2), 'n_history': n_history}
    points = 2 if amount_try >= 1e9 else 1 if amount_try >= 1e8 else 0
    return points, {'code': 'size_absolute', 'n_history': n_history}


def score(result, rate, baseline, n_history, revenue=None, revenue_source=None):
    """Points and reasons for one pipeline result. rate is TRY per unit of its currency.
    revenue is used only when USE_REVENUE (or a test) passes one; size = max(history, revenue) points."""
    reasons, total = [], 0
    amount, currency = result.get('amount'), result.get('currency')
    kind = 'revision' if result.get('is_revision') else 'new'
    if kind == 'revision' and amount is not None:
        previous = result.get('previous_amount')
        amount = amount - previous if previous is not None else None
        reasons.append({'code': 'revision', 'points': 0})
    if amount is None:
        reasons.append({'code': 'no_amount', 'points': 0})
    elif rate is None:
        reasons.append({'code': 'no_rate', 'currency': currency, 'points': 0})
    else:
        points, reason = size_points(amount * rate, baseline, n_history)
        rpoints, rreason = revenue_points(amount * rate, revenue, revenue_source)
        if reason:
            reason['points'] = points if points >= rpoints or not rreason else 0
            reasons.append(reason)
        else:
            reasons.append({'code': 'no_increase', 'points': 0})
        if rreason:
            rreason['points'] = rpoints if rpoints > points else 0
            reasons.append(rreason)
        total += max(points, rpoints) if rreason else points
    if currency and currency not in TRY_CODES:
        reasons.append({'code': 'foreign_currency', 'currency': currency, 'points': 1})
        total += 1
    years = duration_years(result.get('duration'))
    if years is not None and years >= 2:
        reasons.append({'code': 'long_contract', 'years': round(years, 1), 'points': 1})
        total += 1
    level = 'high' if total >= 4 else 'medium' if total >= 2 else 'low'
    stated = result.get('amount')
    # stated amount in TRY (also for revisions): the sort key of ordering v2 (docs/importance_v2_rule.md)
    amount_try = stated * rate if stated is not None and rate is not None else None
    return {
        'score': total,
        'level': level,
        'kind': kind,
        'reasons': reasons,
        'amount_try': amount_try,
        'needs_review': bool(result.get('needs_review')),
        'needs_review_reasons': result.get('needs_review_reasons') or [],
    }


def score_result(con, result):
    day = date.fromisoformat(result['published_at'][:10])
    currency = result.get('currency')
    rate = fx_rate(con, currency, day) if currency else None
    baseline, n_history = company_baseline(con, result.get('symbol'), day)
    revenue, source = (
        revenue_base(con, result.get('kap_url'), result.get('symbol'), day) if USE_REVENUE else (None, None)
    )
    return score(result, rate, baseline, n_history, revenue, source)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pipeline')
    args = ap.parse_args()
    if not args.pipeline:
        ap.error('give --pipeline')

    with open(args.pipeline, encoding='utf-8') as f:
        results = [json.loads(l) for l in f if l.strip()]
    label = os.path.basename(args.pipeline).removeprefix('pipeline_').removesuffix('.jsonl')
    out_path = settings.path(f'triage_{label}.jsonl')
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        scored = [{**r, 'importance': score_result(con, r)} for r in results]
    finally:
        con.close()
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in scored:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    levels = {k: sum(r['importance']['level'] == k for r in scored) for k in ('high', 'medium', 'low')}
    flagged = sum(r['importance']['needs_review'] for r in scored)
    print(
        f'rows={len(scored)} ' + ' '.join(f'{k}={v}' for k, v in levels.items()) + f' flagged={flagged} -> {out_path}'
    )


if __name__ == '__main__':
    main()
