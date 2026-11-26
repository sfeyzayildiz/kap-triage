"""Combined extraction pipeline: v3 prompt plus the three code checks plus the layered
injection defence (docs/layered_defence_rule.md, adopted 2026-11-09): layer 1 Matriks
cross-check (amount_vs_matriks), layer 2 source-sentence check (amount_not_in_text,
amount_from_instruction, judge_error).

The LLM extracts facts. Code checks only flag: they never change the amount or the
currency. Failures are flagged as run_error, never dropped.
Output goes to data/pipeline_<label>.jsonl. Stdout shows only counts.

Usage:
  python -m kap_triage.analysis.pipeline --date 2026-10-30
  python -m kap_triage.analysis.pipeline --ids 123,456
"""

import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from kap_triage.analysis.rules import amount_is_projection, cumulative_total, currency_unclear, norm_cur
from kap_triage.analysis.llm import PROMPT_VERSION, MODEL, UNVERIFIED, call_llm, trace_inference
from kap_triage.analysis.defence import amount_vs_matriks, source_reasons
from kap_triage.settings import settings

DB_PATH = settings.path('kap.duckdb')
RUN_ERROR = 'run_error'
TWO_RUN = 'two_run_disagree'
SELECT = 'SELECT news_id,kap_url,symbol,published_at,aciklama FROM disclosures'


def apply_checks(data, text):
    """Add the code-check flags. Same inputs as level 2 in score_silent.py."""
    amount, currency = data.get('amount'), data.get('currency')
    reasons = list(data.get('needs_review_reasons') or [])
    if currency_unclear(text):
        reasons.append('currency_unclear')
    if amount_is_projection(text, amount):
        reasons.append('amount_is_projection')
    if cumulative_total(text, amount, currency):
        reasons.append('cumulative_total')
    data['needs_review_reasons'] = list(dict.fromkeys(reasons))
    data['needs_review'] = bool(data['needs_review_reasons'])
    return data


def apply_defence(data, text, matriks, judge):
    """Layered defence flags. matriks=(amount,cur,tcmb_ex_rt) or None; judge=callable(sentence)."""
    amount, currency = data.get('amount'), data.get('currency')
    reasons = list(data.get('needs_review_reasons') or [])
    if matriks and amount_vs_matriks(amount, currency, *matriks):
        reasons.append('amount_vs_matriks')
    if judge is not None:
        reasons += source_reasons(text, amount, judge)
    data['needs_review_reasons'] = list(dict.fromkeys(reasons))
    data['needs_review'] = bool(data['needs_review_reasons'])
    return data


def analyze(text, extract=call_llm, matriks=None, judge=None):
    """Extract and check one text. Any failure comes back flagged, never missing.
    judge=None skips layer 2 (self-tests only); callers pass defence_context()."""
    try:
        data = extract(text)
    except Exception as e:
        return {'needs_review': True, 'needs_review_reasons': [RUN_ERROR], 'error': type(e).__name__}
    if data is None:
        return {'needs_review': True, 'needs_review_reasons': [RUN_ERROR], 'error': 'invalid_output'}
    return apply_defence(apply_checks(data, text), text, matriks, judge)


def judge_pass(results, texts, judge, identities=None):
    """Layer 2 after all extractions, so Ollama does not switch num_ctx (8192 <-> 2048) per row."""
    for r, t in zip(results, texts):
        if RUN_ERROR not in r['needs_review_reasons']:
            events = r['provenance']['judge'] if identities is not None else None
            with trace_inference(identities, events):
                apply_defence(r, t, None, judge)
    return results


def _key(amount, currency):
    return (None, None) if amount is None else (round(float(amount), 2), norm_cur(currency))


def two_run_check(results, texts, extract=call_llm, identities=None):
    """ADOPT_TWO_RUN (docs/set_d_rule.md): a second extraction per text; a different (amount, currency)
    or a failed second call adds two_run_disagree. Values stay those of the first run. Run before judge_pass."""
    for r, t in zip(results, texts):
        if RUN_ERROR in r['needs_review_reasons']:
            continue
        try:
            events = r['provenance']['second_extraction'] if identities is not None else None
            with trace_inference(identities, events):
                second = extract(t)
        except Exception:
            second = None
        if second is None or _key(second.get('amount'), second.get('currency')) != _key(
            r.get('amount'), r.get('currency')
        ):
            r['needs_review_reasons'] = list(dict.fromkeys(r['needs_review_reasons'] + [TWO_RUN]))
            r['needs_review'] = True
    return results


def defence_context(news_ids):
    """Matriks records for these ids (one short read) and the cached judge."""
    from kap_triage.analysis.defence import CachedJudge, load_matriks

    return load_matriks(news_ids), CachedJudge()


def full_git_commit(root=None):
    try:
        root = root if root is not None else Path(__file__).resolve().parents[2]
        if (root / '.git').exists():
            result = subprocess.run(
                ['git', 'rev-parse', '--verify', 'HEAD'],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            commit = result.stdout.strip()
            if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
                return commit
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return UNVERIFIED


def analyze_rows(rows, matriks, judge, *, two_run=False, provenance=False):
    texts = [r[4] for r in rows]
    identities = {} if provenance else None
    commit = full_git_commit() if provenance and rows else UNVERIFIED
    results = []
    for row, text in zip(rows, texts):
        extraction = []
        with trace_inference(identities, extraction):
            result = analyze(text, matriks=matriks.get(str(row[0])))
        if provenance:
            result['provenance'] = {
                'git_commit': commit,
                'extraction': extraction,
                'second_extraction': [],
                'judge': [],
            }
        results.append(result)
    if two_run:
        two_run_check(results, texts, identities=identities)
    return judge_pass(results, texts, judge, identities=identities)


def load_rows(date_value, ids):
    import duckdb  # here, not at the top: kap-kart (web/kart.py) uses this module without a database

    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        if ids:
            marks = ','.join('?' for _ in ids)
            return con.execute(f'{SELECT} WHERE news_id IN ({marks}) ORDER BY published_at', ids).fetchall()
        return con.execute(
            f'{SELECT} WHERE CAST(published_at AS DATE)=? ORDER BY published_at', [date_value]
        ).fetchall()
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date')
    parser.add_argument('--ids')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if bool(args.date) == bool(args.ids):
        parser.error('give exactly one of --date or --ids')

    now = datetime.now()
    if now.hour == 23 and 40 <= now.minute <= 50:
        raise SystemExit('collection window, try after 23:50')

    ids = args.ids.split(',') if args.ids else None
    rows = load_rows(args.date, ids)[: args.limit]
    matriks, judge = defence_context([r[0] for r in rows])
    out_path = settings.path(f'pipeline_{args.date or "ids"}.jsonl')
    start = time.time()
    results = analyze_rows(rows, matriks, judge, provenance=True)
    flagged = errors = 0
    with open(out_path, 'w', encoding='utf-8') as f:
        for (news_id, url, symbol, published_at, text), result in zip(rows, results):
            flagged += result['needs_review']
            errors += RUN_ERROR in result['needs_review_reasons']
            result.update(
                {
                    'news_id': str(news_id),
                    'kap_url': url,
                    'symbol': symbol,
                    'published_at': str(published_at),
                    'prompt_version': PROMPT_VERSION,
                    'model': MODEL,
                    'git_commit': result['provenance']['git_commit'],
                }
            )
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    print(f'rows={len(rows)} flagged={flagged} run_errors={errors} seconds={time.time() - start:.0f} -> {out_path}')


if __name__ == '__main__':
    main()
