"""Recount published results from the evidence files in evidence/ and compare them with docs/results.md.

    python main.py verify-results

evidence/set_c.jsonl has one line per Set C item (100): an id hash, whether the item was flagged,
the reason codes and the error type against the blind gold label (null = correct).
evidence/regex_set_c.jsonl has the same items twice, once per regex baseline (a, b): whether an
amount was found, the code-check reason codes and the error type. evidence/set_d.jsonl has the
50 Set D items with both live runs (flagged, reason codes, error type per run) and whether the two
runs disagree. No file holds licensed content. They were written by the evidence/export_*.py
scripts from the saved runs, with the same functions as the frozen scoring and the same totals
(checked when written; the regexes were also run again and gave the saved outputs).

A silent error is an item that was not flagged and has an error (docs/metrics_faq.md). A regex has
no flag of its own, so every regex error is silent; "with code checks" adds the frozen checks.
What it cannot show: that the error types are right. That needs the licensed texts and labels.
"""

import json
import re
from collections import Counter
from pathlib import Path

from kap_triage.web.reliability import upper95

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'evidence' / 'set_c.jsonl'
RESULTS_MD = ROOT / 'docs' / 'results.md'
# the Set C row of the extraction table in docs/results.md
ROW = re.compile(r'Set C \(held-out, (\d+)\) \| \*\*(\d+) silent errors? \(95% upper ([\d.]+)%\), (\d+) flagged\*\*')
REGEX_EVIDENCE = ROOT / 'evidence' / 'regex_set_c.jsonl'
# the two regex rows of the same table: "... (A) / A + all code checks | Set C | 25 / 23 silent errors out of 100"
REGEX_ROW = re.compile(r'\((A|B)\) / \1 \+ all code checks \| Set C \| (\d+) / (\d+) silent errors out of (\d+) \|')
SET_D_EVIDENCE = ROOT / 'evidence' / 'set_d.jsonl'
# the two-run row of the "Decisions" table and the "Test vs live flag rate" note in docs/results.md
SET_D_ROW = re.compile(
    r'disagree (\d+)/(\d+); new flags over run a \*\*(\d+)/\d+\*\* \(bar \d+\); run a silent (\d+)/\d+, '
    r'run b silent \*\*(\d+)/\d+\*\*, caught by the flag \((\d+)/(\d+)\); on the random (\d+) alone '
    r'(\d+)/\d+ \(95% upper ([\d.]+)%\) and (\d+)/\d+ \(([\d.]+)%\)'
)
SET_D_FLAGS = re.compile(r'on Set D: (\d+)-(\d+)% of (\d+) new texts, (\d+)-(\d+)% on the random (\d+)')
# Which layer of the live pipeline raises each reason code (kap_triage/analysis/llm.py postprocess,
# pipeline.apply_checks, pipeline.apply_defence). Any other code is the model's own flag (prompt v3).
# Fixed 25 Nov before the Set D breakdown was first counted; descriptive only, no decision.
LAYERS = (
    (
        'extraction code',
        {'unknown_currency_code', 'revision_without_previous', 'total_lt_amount', 'try_stated_but_currency_try'},
    ),
    ('code checks', {'currency_unclear', 'amount_is_projection', 'cumulative_total'}),
    ('Matriks cross-check', {'amount_vs_matriks'}),
    ('source check (judge)', {'amount_not_in_text', 'amount_from_instruction', 'judge_error'}),
    ('run error', {'run_error'}),
)
MODEL_LAYER = "model's own flag"
INJECTION_EVIDENCE = ROOT / 'evidence' / 'injection_set_c.jsonl'
# the layered-defence row of the "Security" table and the "Injection batches" note in docs/results.md
INJECTION_ROW = re.compile(
    r'Layered: [^|]*\| texts (\d+)-(\d+) \| silent \*\*(\d+) → (\d+)\*\* \(95% upper ([\d.]+)%\)'
)
INJECTION_ALONE = re.compile(r'On \d+-\d+ each layer alone also reached (\d+)/(\d+)')


def published(path=RESULTS_MD):
    """The Set C numbers as docs/results.md states them."""
    hits = ROW.findall(path.read_text(encoding='utf-8'))
    if len(hits) != 1:
        raise SystemExit(f'expected one Set C row in {path.name}, found {len(hits)}')
    n, silent, upper, flagged = hits[0]
    return {'n': int(n), 'silent': int(silent), 'upper': float(upper), 'flagged': int(flagged)}


def load(path=EVIDENCE):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def recount(rows):
    return {
        'n': len(rows),
        'silent': sum(1 for r in rows if not r['flagged'] and r['error']),
        'flagged': sum(1 for r in rows if r['flagged']),
        'caught': sum(1 for r in rows if r['flagged'] and r['error']),
        'errors': Counter(r['error'] for r in rows if r['error']),
        'reasons': Counter(x for r in rows for x in r['reasons']),
    }


def matches(c, p):
    """True when the recount equals the published row (counts, and the bound to one decimal)."""
    upper = round(upper95(c['silent'], c['n']) * 100, 1)
    return (c['n'], c['silent'], c['flagged'], upper) == (p['n'], p['silent'], p['flagged'], p['upper'])


def published_regex(path=RESULTS_MD):
    """The regex numbers as docs/results.md states them, per baseline ('a', 'b')."""
    hits = REGEX_ROW.findall(path.read_text(encoding='utf-8'))
    out = {name.lower(): {'silent': int(s), 'with_checks': int(w), 'n': int(n)} for name, s, w, n in hits}
    if len(hits) != 2 or set(out) != {'a', 'b'}:
        raise SystemExit(f'expected one regex row each for A and B in {path.name}, found {len(hits)}')
    return out


def recount_regex(rows):
    """Per baseline: items, amounts found, silent errors alone and with the code checks."""
    out = {}
    for name in sorted({r['baseline'] for r in rows}):
        mine = [r for r in rows if r['baseline'] == name]
        out[name] = {
            'n': len(mine),
            'found': sum(1 for r in mine if r['found']),
            'silent': sum(1 for r in mine if r['error']),
            'with_checks': sum(1 for r in mine if r['error'] and not r['reasons']),
            'flagged': sum(1 for r in mine if r['reasons']),
            'errors': Counter(r['error'] for r in mine if r['error']),
        }
    return out


def regex_matches(c, p):
    """True when every baseline's recount equals its published row."""
    return set(c) == set(p) and all(
        (c[k]['n'], c[k]['silent'], c[k]['with_checks']) == (p[k]['n'], p[k]['silent'], p[k]['with_checks']) for k in p
    )


def published_set_d(path=RESULTS_MD):
    """The Set D numbers as docs/results.md states them."""
    text = path.read_text(encoding='utf-8')
    rows, flags = SET_D_ROW.findall(text), SET_D_FLAGS.findall(text)
    if len(rows) != 1 or len(flags) != 1:
        raise SystemExit(
            f'expected one Set D row and one flag-rate note in {path.name}, found {len(rows)}, {len(flags)}'
        )
    d, n, t1, sa, sb, caught, silent_b, nr, sar, uar, sbr, ubr = rows[0]
    lo, hi, n2, rlo, rhi, nr2 = flags[0]
    if (n, nr) != (n2, nr2) or int(sb) != int(silent_b):
        raise SystemExit(f'Set D row and flag-rate note in {path.name} disagree on n')
    keys = ('n', 'disagree', 't1', 'silent_a', 'silent_b', 'caught_b', 'n_r', 'silent_a_r', 'silent_b_r')
    out = dict(zip(keys, map(int, (n, d, t1, sa, sb, caught, nr, sar, sbr))))
    out.update(upper_a_r=float(uar), upper_b_r=float(ubr))
    out.update(flag_lo=int(lo), flag_hi=int(hi), flag_r_lo=int(rlo), flag_r_hi=int(rhi))
    return out


def recount_set_d(rows):
    """The same numbers, counted from the evidence rows."""
    rand = [r for r in rows if r['stratum'] == 'R']

    def silent(rs, run):
        return [r for r in rs if r[f'error_{run}'] and not r[f'flagged_{run}']]

    def pct(rs, run):
        return round(100 * sum(r[f'flagged_{run}'] for r in rs) / len(rs))

    return {
        'n': len(rows),
        'disagree': sum(r['disagree'] for r in rows),
        't1': sum(1 for r in rows if r['disagree'] and not r['flagged_a']),
        'silent_a': len(silent(rows, 'a')),
        'silent_b': len(silent(rows, 'b')),
        'caught_b': sum(1 for r in silent(rows, 'b') if r['disagree']),
        'n_r': len(rand),
        'silent_a_r': len(silent(rand, 'a')),
        'silent_b_r': len(silent(rand, 'b')),
        'upper_a_r': round(upper95(len(silent(rand, 'a')), len(rand)) * 100, 1),
        'upper_b_r': round(upper95(len(silent(rand, 'b')), len(rand)) * 100, 1),
        'flag_lo': min(pct(rows, 'a'), pct(rows, 'b')),
        'flag_hi': max(pct(rows, 'a'), pct(rows, 'b')),
        'flag_r_lo': min(pct(rand, 'a'), pct(rand, 'b')),
        'flag_r_hi': max(pct(rand, 'a'), pct(rand, 'b')),
    }


def layer_of(code):
    return next((name for name, codes in LAYERS if code in codes), MODEL_LAYER)


def layer_counts(rows, run):
    """Per layer: items it flags (any of its codes), and items only it flags."""
    out = {}
    for r in rows:
        layers = {layer_of(c) for c in r[f'reasons_{run}']}
        for name in layers:
            x = out.setdefault(name, {'items': 0, 'only': 0})
            x['items'] += 1
            x['only'] += len(layers) == 1
    return out


def main_set_d():
    rows = load(SET_D_EVIDENCE)
    c, p = recount_set_d(rows), published_set_d()
    same = c == p
    print(f'Set D, live pipeline, two separate runs: {c["n"]} items ({c["n_r"]} random)')
    print(
        f'  silent errors: run a {c["silent_a"]}/{c["n"]}, run b {c["silent_b"]}/{c["n"]} '
        f'(caught by the two-run flag: {c["caught_b"]}); random {c["n_r"]}: {c["silent_a_r"]} '
        f'(upper {c["upper_a_r"]}%) and {c["silent_b_r"]} (upper {c["upper_b_r"]}%)'
    )
    print(f'  disagree {c["disagree"]}/{c["n"]}, new flags over run a {c["t1"]}')
    print(f'  flagged {c["flag_lo"]}-{c["flag_hi"]}%, random {c["flag_r_lo"]}-{c["flag_r_hi"]}%')
    for run in 'ab':
        flagged = sum(r[f'flagged_{run}'] for r in rows)
        parts = ', '.join(f'{k} {v["items"]} (only {v["only"]})' for k, v in sorted(layer_counts(rows, run).items()))
        print(f'  run {run}, {flagged} flagged, by layer (an item can have several): {parts}')
    print('  docs/results.md (read now): ' + ('MATCH' if same else f'MISMATCH, it says {p}'))
    return same


def published_injection(path=RESULTS_MD):
    """The layered-defence numbers as docs/results.md states them."""
    text = path.read_text(encoding='utf-8')
    rows, alone = INJECTION_ROW.findall(text), INJECTION_ALONE.findall(text)
    if len(rows) != 1 or len(alone) != 1:
        raise SystemExit(
            f'expected one layered-defence row and one note in {path.name}, found {len(rows)}, {len(alone)}'
        )
    first, last, silent, both, upper = rows[0]
    k, n = map(int, alone[0])
    if int(last) - int(first) + 1 != n:
        raise SystemExit(f'layered-defence row and note in {path.name} disagree on n')
    return {'n': n, 'silent': int(silent), 'both': int(both), 'upper': float(upper), 'layer_alone': k}


def recount_injection(rows):
    """Per attack: items that count, successes, silent successes, and those left by layer 1, 2 and both."""
    out = {}
    for attack in sorted({r['attack'] for r in rows}):
        mine = [r for r in rows if r['attack'] == attack and r['counts']]
        silent = [r for r in mine if r['success'] and not r['flagged']]
        out[attack] = {
            'n': len(mine),
            'success': sum(r['success'] for r in mine),
            'silent': len(silent),
            'layer1': sum(1 for r in silent if not r['caught_layer1']),
            'layer2': sum(1 for r in silent if not r['caught_layer2']),
            'both': sum(1 for r in silent if not (r['caught_layer1'] or r['caught_layer2'])),
        }
    return out


def injection_matches(c, p):
    """The published row is the amount attack; it must also be the total over all four attacks."""
    a = c['amount']
    total = {k: sum(x[k] for x in c.values()) for k in ('silent', 'both')}
    upper = round(upper95(a['both'], a['n']) * 100, 1)
    return (
        (a['n'], a['silent'], a['both'], upper) == (p['n'], p['silent'], p['both'], p['upper'])
        and a['layer1'] == a['layer2'] == p['layer_alone']
        and total == {'silent': a['silent'], 'both': a['both']}
    )


def main_injection():
    rows = load(INJECTION_EVIDENCE)
    c, p = recount_injection(rows), published_injection()
    same = injection_matches(c, p)
    texts = len({r['id_hash'] for r in rows})
    with_record = len({r['id_hash'] for r in rows if r['matriks_record']})
    print(f'Prompt injection, layered defence: {texts} texts ({with_record} with a Matriks record), sealed attacks')
    for k, x in c.items():
        print(
            f'  {k}: {x["success"]}/{x["n"]} succeeded, {x["silent"]} silent; left silent by layer 1 alone '
            f'{x["layer1"]}, layer 2 alone {x["layer2"]}, both {x["both"]}'
        )
    a = c['amount']
    print(f'  amount, both layers: {a["both"]}/{a["n"]}, 95% upper bound {upper95(a["both"], a["n"]):.1%}')
    print(
        f'  docs/results.md (read now) says {p["silent"]} → {p["both"]} of {p["n"]} (upper {p["upper"]}%), '
        f'each layer alone {p["layer_alone"]}: ' + ('MATCH' if same else 'MISMATCH')
    )
    return same


def main_regex():
    c = recount_regex(load(REGEX_EVIDENCE))
    p = published_regex()
    same = regex_matches(c, p)
    print('Regex baselines on Set C (no LLM; a regex has no flag, so every error is silent):')
    for k, x in c.items():
        types = ', '.join(f'{e} {v}' for e, v in sorted(x['errors'].items())) or '-'
        print(
            f'  {k.upper()}: amount found {x["found"]}/{x["n"]}, silent errors {x["silent"]}/{x["n"]} ({types}), '
            f'with code checks {x["with_checks"]}/{x["n"]} ({x["flagged"]} flagged)'
        )
    stated = ', '.join(f'{k.upper()} {v["silent"]} / {v["with_checks"]}' for k, v in sorted(p.items()))
    print(f'  docs/results.md (read now) says {stated} of 100: ' + ('MATCH' if same else 'MISMATCH'))
    return same


def main_set_c():
    c = recount(load())
    p = published()
    same = matches(c, p)
    print(f'Set C, level 2: {c["n"]} items')
    print(f'  silent errors: {c["silent"]}/{c["n"]}, 95% upper bound {upper95(c["silent"], c["n"]):.1%}')
    print(f'  flagged: {c["flagged"]}/{c["n"]} ({c["flagged"] / c["n"]:.0%}); wrong extractions flagged: {c["caught"]}')
    print('  error types: ' + (', '.join(f'{k} {v}' for k, v in sorted(c['errors'].items())) or '-'))
    print('  reason codes: ' + ', '.join(f'{k} {v}' for k, v in sorted(c['reasons'].items())))
    print(
        f'  docs/results.md (read now) says {p["silent"]}/{p["n"]} silent, upper {p["upper"]}%, '
        f'{p["flagged"]} flagged: ' + ('MATCH' if same else 'MISMATCH')
    )
    return same


def main():
    ok = main_set_c()
    ok = main_regex() and ok  # run all, so a mismatch in one does not hide the others
    ok = main_set_d() and ok
    ok = main_injection() and ok
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
