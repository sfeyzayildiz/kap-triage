"""Recount published results from the evidence files in evidence/ and compare them with docs/results.md.

    python main.py verify-results

evidence/set_c.jsonl has one line per Set C item (100): an id hash, whether the item was flagged,
the reason codes and the error type against the blind gold label (null = correct).
evidence/regex_set_c.jsonl has the same items twice, once per regex baseline (a, b): whether an
amount was found, the code-check reason codes and the error type. Neither file holds licensed
content. They were written by evidence/export_set_c.py and evidence/export_regex.py from the saved
runs, with the same functions as the frozen scoring and the same totals (checked when written; the
regexes were also run again and gave the saved outputs).

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
    ok = main_regex() and ok  # run both, so a mismatch in one does not hide the other
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
