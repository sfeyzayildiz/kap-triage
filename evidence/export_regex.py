"""Write evidence/regex_set_c.jsonl: the regex baselines on Set C per item, without licensed content.

Runs only in the private working repository, where the licensed texts, the gold labels and the
saved baseline runs are (data/ is never committed). Rule: docs/regex_baseline_rule.md.

  A = the October regex (experiments/baseline.py), B = the money regex written for the code checks.

Before writing, it checks three things and writes nothing if one fails:
  1. both regexes run again on the Set C texts give exactly the saved amounts and currencies;
  2. its totals equal the frozen scoring script (score_silent.py) at level 0 (regex alone)
     and level 2 (regex + all code checks);
  3. the 100 id hashes are the same as in evidence/set_c.jsonl.

Each line holds: the baseline (a or b), an id hash, whether an amount was found, the code-check
reason codes and the error type against the gold label (null = correct). No amount, currency,
text, company or KAP link. `python main.py verify-results` recounts the published numbers.

    cd <private repo> && PYTHONPATH=scripts:experiments .venv/bin/python <this repo>/evidence/export_regex.py
"""

import hashlib
import json
import re
from pathlib import Path

import score_silent as ss
from regex_baseline import BASELINES

RESULTS = {'a': 'data/eval_regex_a_set_c.jsonl', 'b': 'data/eval_regex_b_set_c.jsonl'}
GOLD = 'data/gold_set_c.jsonl'
HERE = Path(__file__).resolve().parent
OUT = HERE / 'regex_set_c.jsonl'
SET_C = HERE / 'set_c.jsonl'
KEYS = {'baseline', 'id_hash', 'found', 'reasons', 'error'}


def id_hash(nid):
    return hashlib.sha256(nid.encode()).hexdigest()[:16]


def reasons_for(text, amount, currency):
    """The frozen code checks of score_silent.py level 2, as reason codes."""
    out = []
    if ss.currency_unclear(text):
        out.append('currency_unclear')
    if ss.amount_is_projection(text, amount):
        out.append('amount_is_projection')
    if ss.cumulative_total(text, amount, currency):
        out.append('cumulative_total')
    return out


def row_for(name, nid, r, g, text):
    return {
        'baseline': name,
        'id_hash': id_hash(nid),
        'found': r.get('llm_amount') is not None,
        'reasons': reasons_for(text, r.get('llm_amount'), r.get('llm_cur')),
        'error': ss.compare(r, g['amount'], g['currency']),
    }


def check_one(name, rows, gold, texts):
    """Rerun, recount and compare with score_silent; returns the evidence rows or stops."""
    if any(r.get('needs_review_reasons') or r.get('error') for r in rows.values()):
        raise SystemExit(f'STOP: regex {name} rows carry flags or run errors')
    rerun_same = sum(
        1 for nid, r in rows.items() if BASELINES[name](texts[nid]) == (r.get('llm_amount'), r.get('llm_cur'))
    )
    out = [row_for(name, nid, rows[nid], gold[nid], texts[nid]) for nid in sorted(rows)]
    silent0 = sum(1 for o in out if o['error'])
    silent2 = sum(1 for o in out if o['error'] and not o['reasons'])
    flagged2 = sum(1 for o in out if o['reasons'])
    s0 = ss.score(rows, gold, texts, 0)[0]
    s2 = ss.score(rows, gold, texts, 2)[0]
    same = (s0['silent'], s0['flagged'], s2['silent'], s2['flagged']) == (silent0, 0, silent2, flagged2)
    print(
        f'regex {name}: n={len(out)} found={sum(o["found"] for o in out)} rerun_same={rerun_same}/{len(rows)} '
        f'silent={silent0} with_checks={silent2} flagged={flagged2} | score_silent: silent={s0["silent"]} '
        f'with_checks={s2["silent"]} flagged={s2["flagged"]} -> {"MATCH" if same else "MISMATCH"}'
    )
    if rerun_same != len(rows) or not same:
        raise SystemExit('STOP: not written')
    return out


def main():
    gold = {str(g['news_id']): g for g in ss.load_jsonl(GOLD)}
    runs = {name: ss.load_results(path) for name, path in RESULTS.items()}
    texts = ss.load_texts(set(gold))
    for name, rows in runs.items():
        if set(rows) != set(gold) or set(gold) - set(texts):
            raise SystemExit(f'STOP: ids differ (regex {name} {len(rows)}, gold {len(gold)}, texts {len(texts)})')
    published_ids = {json.loads(line)['id_hash'] for line in SET_C.read_text(encoding='utf-8').splitlines()}
    if {id_hash(nid) for nid in gold} != published_ids:
        raise SystemExit('STOP: Set C ids differ from evidence/set_c.jsonl')
    out = [o for name in sorted(runs) for o in check_one(name, runs[name], gold, texts)]
    for o in out:
        if set(o) != KEYS or not re.fullmatch(r'[0-9a-f]{16}', o['id_hash']):
            raise SystemExit('STOP: unexpected field')
    OUT.write_text(''.join(json.dumps(o, sort_keys=True) + '\n' for o in out), encoding='utf-8')
    print(f'written {len(out)} lines -> {OUT.name}')


if __name__ == '__main__':
    main()
