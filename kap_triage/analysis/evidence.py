"""Recount the Set C result from the published evidence file (evidence/set_c.jsonl).

    python main.py verify-results

The file has one line per Set C item (100): an id hash, whether the item was flagged, the reason
codes and the error type against the blind gold label (null = correct). It holds no licensed
content; it was written by evidence/export_set_c.py from the saved run, with the same functions as
the frozen scoring and the same totals (checked when it was written).

A silent error is an item that was not flagged and has an error (docs/metrics_faq.md). This
command recounts it and the 95% upper bound, and compares them with docs/results.md.
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


def main():
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
    if not same:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
