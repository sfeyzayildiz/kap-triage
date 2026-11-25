"""Write evidence/injection_set_c.jsonl: the layered-defence attack run per item, without licensed content.

Runs only in the private working repository, where the licensed texts, the saved run (Set C texts
61-78, 9 Nov) and the sealed attack file are. Rule: docs/layered_defence_rule.md. The attack file
is opened only to check its fingerprint and to know the injected number (as the frozen scoring
does); nothing of it is printed or written. Feyza runs this, so the attacks stay unseen by Claude.

Before writing, it checks and writes nothing if one check fails:
  1. the attack file has the fingerprint recorded in the rule (checked by injection_test.configure);
  2. every judge answer comes from the saved judge cache (no new model call, so nothing can drift);
  3. its totals equal the frozen scoring (injection_test.score) with no defence, layer 1 alone,
     layer 2 alone and both layers, for every attack.

Each line holds: an id hash, the attack type (amount, currency, review, format), whether the item
counts for that attack, whether the attack succeeded, whether the pipeline flagged the attacked
text, whether the text has a Matriks record and, for silent successes only, whether layer 1
(Matriks cross-check) and layer 2 (source sentence) catch it. No text, attack, amount or company.

    cd <private repo> && PYTHONPATH=scripts:experiments .venv/bin/python <this repo>/evidence/export_injection.py \
        data/injection_attacks_v2.txt
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import injection_test as it

RESULTS = 'data/injection_results_v4.jsonl'
START = 60  # texts 61-78 (docs/layered_defence_rule.md)
N = 18
HERE = Path(__file__).resolve().parent
OUT = HERE / 'injection_set_c.jsonl'
SET_C = HERE / 'set_c.jsonl'
KEYS = {'id_hash', 'attack', 'counts', 'success', 'flagged', 'matriks_record', 'caught_layer1', 'caught_layer2'}


class CacheMiss(Exception):
    pass


def refuse(sentence):
    raise CacheMiss()


def main():
    if len(sys.argv) != 2:
        raise SystemExit('give the sealed attack file')
    it.configure(sys.argv[1], START)  # fingerprint check; stops without printing anything of the file
    from pipeline import load_rows
    from matriks_crosscheck import load_matriks
    from source_check import CachedJudge

    ids = it.pick_ids(it.load_jsonl(it.SET_C), it.load_jsonl(it.GOLD_C), start=START)
    if len(ids) != N:
        raise SystemExit(f'STOP: {len(ids)} texts, expected {N}')
    texts = {str(r[0]): r[4] for r in load_rows(None, ids)}
    rows = it.load_jsonl(RESULTS)
    by = {(r['news_id'], r['variant']): r['result'] for r in rows}
    if len(rows) != N * len(it.VARIANTS) or set(by) != {(i, v) for i in ids for v in it.VARIANTS}:
        raise SystemExit(f'STOP: {len(rows)} rows, expected {N * len(it.VARIANTS)} for these texts')
    mx = load_matriks(ids)
    judge = CachedJudge(call=refuse)  # cache only: a missing answer stops the export
    l1, l2 = it.matriks_caught(mx), it.source_caught(texts, judge)

    out = []
    try:
        for i in ids:
            clean = by[(i, 'clean')]
            for v in it.ATTACKS:
                att = by[(i, v)]
                counts = v != 'review' or it.flagged(clean)
                success = counts and it.success(v, clean, att)
                silent = success and not it.flagged(att)
                out.append(
                    {
                        'id_hash': hashlib.sha256(i.encode()).hexdigest()[:16],
                        'attack': v,
                        'counts': counts,
                        'success': bool(success),
                        'flagged': it.flagged(att),
                        'matriks_record': i in mx,
                        'caught_layer1': bool(l1(i, v, att)) if silent else None,
                        'caught_layer2': bool(l2(i, v, att)) if silent else None,
                    }
                )
        frozen = {
            name: it.score(rows, ids, caught=fn)
            for name, fn in (('layer1', l1), ('layer2', l2), ('both', it.either(l1, l2)))
        }
    except CacheMiss:
        raise SystemExit('STOP: a judge answer is not in the cache; not written') from None

    same = True
    for v in it.ATTACKS:
        mine = [o for o in out if o['attack'] == v and o['counts']]
        silent = [o for o in mine if o['success'] and not o['flagged']]
        c = {
            'n': len(mine),
            'success': sum(o['success'] for o in mine),
            'silent': len(silent),
            'layer1': sum(not o['caught_layer1'] for o in silent),
            'layer2': sum(not o['caught_layer2'] for o in silent),
            'both': sum(not (o['caught_layer1'] or o['caught_layer2']) for o in silent),
        }
        f = frozen['both'][v]
        ref = {
            'n': f['n'],
            'success': f['success'],
            'silent': f['silent'],
            'both': f['silent_defended'],
            'layer1': frozen['layer1'][v]['silent_defended'],
            'layer2': frozen['layer2'][v]['silent_defended'],
        }
        ok = c == ref
        same = same and ok
        print(f'{v}: ' + ' '.join(f'{k}={c[k]}' for k in ref) + (' MATCH' if ok else f' MISMATCH frozen {ref}'))
    overlap = {o['id_hash'] for o in out} - {json.loads(x)['id_hash'] for x in SET_C.read_text().splitlines()}
    print(
        f'texts={len(ids)} with_matriks_record={sum(i in mx for i in ids)} judge_calls={judge.calls} '
        f'ids_not_in_set_c={len(overlap)}'
    )
    for o in out:
        if set(o) != KEYS or not re.fullmatch(r'[0-9a-f]{16}', o['id_hash']):
            raise SystemExit('STOP: unexpected field')
    if not same or overlap or judge.calls:
        raise SystemExit('STOP: not written')
    OUT.write_text(''.join(json.dumps(o, sort_keys=True) + '\n' for o in out), encoding='utf-8')
    print(f'written {len(out)} lines -> {OUT.name}')


if __name__ == '__main__':
    main()
