"""Write evidence/set_c.jsonl: the Set C result per item, without any licensed content.

Runs only in the private working repository, where the licensed texts, the gold labels and the
saved model run are (data/ is never committed). It uses the same functions as the frozen scoring
script (score_silent.py, level 2, the Set C decision) and checks that its totals are the same.

Each line holds: an id hash, whether the item was flagged (sent to a person), the reason codes,
and the error type against the gold label (null = correct). No amount, currency, text, company
or KAP link. `python main.py verify-results` recounts the published numbers from this file.

    cd <private repo> && PYTHONPATH=scripts .venv/bin/python <this repo>/evidence/export_set_c.py
"""

import hashlib
import json
import re
from pathlib import Path

import score_silent as ss

RESULTS = 'data/eval_set_c.jsonl'
GOLD = 'data/gold_set_c.jsonl'
OUT = Path(__file__).resolve().parent / 'set_c.jsonl'
LEVEL = 2  # the Set C decision level (docs/set_c_plan.md)
CODE = re.compile(r'^[a-z_]{1,40}$')
KEYS = {'id_hash', 'flagged', 'reasons', 'error'}


def row_for(nid, r, g, text):
    run_error = bool(r.get('error'))
    reasons = [x if CODE.match(str(x)) else 'other' for x in (r.get('needs_review_reasons') or [])]
    if run_error:
        reasons.append('run_error')
    if LEVEL >= 1 and ss.currency_unclear(text):
        reasons.append('currency_unclear')
    if LEVEL >= 2 and ss.amount_is_projection(text, r.get('llm_amount')):
        reasons.append('amount_is_projection')
    if LEVEL >= 2 and ss.cumulative_total(text, r.get('llm_amount'), r.get('llm_cur')):
        reasons.append('cumulative_total')
    return {
        'id_hash': hashlib.sha256(nid.encode()).hexdigest()[:16],
        'flagged': bool(reasons),
        'reasons': sorted(set(reasons)),
        'error': ss.compare(r, g['amount'], g['currency']),
    }


def main():
    rows = ss.load_results(RESULTS)
    gold = {str(g['news_id']): g for g in ss.load_jsonl(GOLD)}
    texts = ss.load_texts(set(rows))
    if set(rows) != set(gold) or set(rows) - set(texts):
        raise SystemExit(f'STOP: ids differ (results {len(rows)}, gold {len(gold)}, texts {len(texts)})')
    out = [row_for(nid, rows[nid], gold[nid], texts.get(nid)) for nid in sorted(rows)]
    for o in out:
        if set(o) != KEYS or not re.fullmatch(r'[0-9a-f]{16}', o['id_hash']):
            raise SystemExit('STOP: unexpected field')
    silent = sum(1 for o in out if not o['flagged'] and o['error'])
    flagged = sum(1 for o in out if o['flagged'])
    stats = ss.score(rows, gold, texts, LEVEL)[0]
    same = (stats['n'], stats['silent'], stats['flagged']) == (len(out), silent, flagged)
    print(
        f'n={len(out)} silent={silent} flagged={flagged} score_silent: n={stats["n"]} '
        f'silent={stats["silent"]} flagged={stats["flagged"]} -> {"MATCH" if same else "MISMATCH"}'
    )
    if not same:
        raise SystemExit('STOP: not written')
    OUT.write_text(''.join(json.dumps(o, sort_keys=True) + '\n' for o in out), encoding='utf-8')
    print(f'written {len(out)} lines -> {OUT.name}')


if __name__ == '__main__':
    main()
