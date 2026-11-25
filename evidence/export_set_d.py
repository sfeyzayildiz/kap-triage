"""Write evidence/set_d.jsonl: the two live runs on Set D per item, without licensed content.

Runs only in the private working repository, where the licensed texts, the gold labels and the
saved runs are (data/ is never committed). Rule: docs/set_d_rule.md (scored once, 15 Nov).

Before writing, it checks and writes nothing if one check fails:
  1. both runs have the same 50 ids as the gold labels and the sample, and the same commit;
  2. its totals equal the frozen scoring script (set_d.py): silent errors and flags per run,
     overall and on the random stratum; disagreements; new flags over run a; caught / missed;
  3. no id hash is also in evidence/set_c.jsonl (the sets do not overlap).

Each line holds: an id hash, the stratum (U = every pool text with "ABD Doları" and cumulative
wording, R = random), whether the two runs disagree, and per run (a, b) whether the item was
flagged, the reason codes and the error type against the gold label (null = correct). No amount,
currency, text, company, KAP link or timing. `python main.py verify-results` recounts it.

    cd <private repo> && PYTHONPATH=scripts:experiments .venv/bin/python <this repo>/evidence/export_set_d.py
"""

import hashlib
import json
import re
from pathlib import Path

import set_d as sd
from score_silent import compare

HERE = Path(__file__).resolve().parent
OUT = HERE / 'set_d.jsonl'
SET_C = HERE / 'set_c.jsonl'
CODE = re.compile(r'^[a-z_]{1,40}$')
KEYS = {'id_hash', 'stratum', 'disagree'} | {f'{k}_{run}' for k in ('flagged', 'reasons', 'error') for run in 'ab'}


def id_hash(nid):
    return hashlib.sha256(nid.encode()).hexdigest()[:16]


def reasons_of(r):
    out = [x if CODE.match(str(x)) else 'other' for x in (r.get('needs_review_reasons') or [])]
    if r.get('error'):
        out.append('run_error')
    return sorted(set(out))


def row_for(nid, stratum, ra, rb, g):
    out = {'id_hash': id_hash(nid), 'stratum': stratum, 'disagree': sd.disagree(ra, rb)}
    for run, r in (('a', ra), ('b', rb)):
        out[f'flagged_{run}'] = sd.flagged(r)
        out[f'reasons_{run}'] = reasons_of(r)
        out[f'error_{run}'] = compare(r, g['amount'], g['currency'])
    return out


def frozen_totals(sample, gold, ra, rb):
    """The numbers set_d.py --score prints, from its own functions."""
    t = sd.two_run(gold, ra, rb)
    out = {'disagree': len(t['disagree']), 't1': len(t['t1'])}
    for run, rows in (('a', ra), ('b', rb)):
        for st in ('all', 'R'):
            ids = [i for i in gold if st == 'all' or sample[i]['stratum'] == st]
            out[f'silent_{run}_{st}'] = sum(1 for i in ids if sd.silent_err(rows[i], gold[i]))
            out[f'flagged_{run}_{st}'] = sum(1 for i in ids if sd.flagged(rows[i]))
        out[f'caught_{run}'] = len(t[f'caught_{run}'])
        out[f'missed_{run}'] = len(t[f'missed_{run}'])
    return out


def evidence_totals(rows):
    """The same numbers, counted only from the evidence rows."""
    out = {'disagree': sum(r['disagree'] for r in rows), 't1': sum(r['disagree'] and not r['flagged_a'] for r in rows)}
    for run in 'ab':
        for st in ('all', 'R'):
            mine = [r for r in rows if st == 'all' or r['stratum'] == st]
            out[f'silent_{run}_{st}'] = sum(1 for r in mine if r[f'error_{run}'] and not r[f'flagged_{run}'])
            out[f'flagged_{run}_{st}'] = sum(1 for r in mine if r[f'flagged_{run}'])
        silent = [r for r in rows if r[f'error_{run}'] and not r[f'flagged_{run}']]
        out[f'caught_{run}'] = sum(1 for r in silent if r['disagree'])
        out[f'missed_{run}'] = sum(1 for r in silent if not r['disagree'])
    return out


def main():
    sample = {str(r['news_id']): r for r in sd.read_jsonl(sd.SET_D)}
    gold = {str(r['news_id']): r for r in sd.read_jsonl(sd.GOLD)}
    ra = {str(r['news_id']): r for r in sd.read_jsonl(sd.RUNS['a'])}
    rb = {str(r['news_id']): r for r in sd.read_jsonl(sd.RUNS['b'])}
    if not (len(gold) == sd.N and set(gold) == set(sample) == set(ra) == set(rb)):
        raise SystemExit(f'STOP: ids differ (sample {len(sample)}, gold {len(gold)}, a {len(ra)}, b {len(rb)})')
    commits = {r.get('git_commit') for r in list(ra.values()) + list(rb.values())}
    if len(commits) != 1:
        raise SystemExit(f'STOP: runs use {len(commits)} commits')
    set_c_ids = {json.loads(line)['id_hash'] for line in SET_C.read_text(encoding='utf-8').splitlines()}
    out = [row_for(i, sample[i]['stratum'], ra[i], rb[i], gold[i]) for i in sorted(gold)]
    overlap = len({o['id_hash'] for o in out} & set_c_ids)
    for o in out:
        if set(o) != KEYS or not re.fullmatch(r'[0-9a-f]{16}', o['id_hash']) or o['stratum'] not in ('U', 'R'):
            raise SystemExit('STOP: unexpected field')
    frozen, mine = frozen_totals(sample, gold, ra, rb), evidence_totals(out)
    same = frozen == mine
    print(f'n={len(out)} commit={commits.pop()} overlap_with_set_c={overlap}')
    print('evidence: ' + ' '.join(f'{k}={v}' for k, v in sorted(mine.items())))
    print('set_d.py: ' + ' '.join(f'{k}={v}' for k, v in sorted(frozen.items())))
    print('MATCH' if same else 'MISMATCH')
    if not same or overlap:
        raise SystemExit('STOP: not written')
    OUT.write_text(''.join(json.dumps(o, sort_keys=True) + '\n' for o in out), encoding='utf-8')
    print(f'written {len(out)} lines -> {OUT.name}')


if __name__ == '__main__':
    main()
