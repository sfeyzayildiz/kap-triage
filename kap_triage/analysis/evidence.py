"""Recount published results from the evidence files in evidence/ and compare them with docs/results.md.

    python main.py verify-results

evidence/set_c.jsonl has one line per Set C item (100): an id hash, whether the item was flagged,
the reason codes and the error type against the blind gold label (null = no recorded scoring error).
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

import argparse
import json
import re
from collections import Counter
from itertools import combinations
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
# These codes can come from the model or code, and the frozen export deduplicates reasons.
SHARED_REASON_CODES = {'currency_unclear'} | LAYERS[0][1]
TECHNICAL_REASONS = {'run_error': 'run error', 'judge_error': 'judge error'}
UNAVAILABLE_LAYER = 'unattributed review'
PROTECTED_SOURCES = {*TECHNICAL_REASONS.values(), UNAVAILABLE_LAYER}
DISAGREE_LAYER = 'two-read disagreement'
SET_C_NOT_RUN = {'Matriks cross-check', 'source check (judge)', 'judge error'}
INJECTION_EVIDENCE = ROOT / 'evidence' / 'injection_set_c.jsonl'
# the layered-defence row of the "Security" table and the "Injection batches" note in docs/results.md
INJECTION_ROW = re.compile(
    r'Layered: [^|]*\| texts (\d+)-(\d+) \| silent \*\*(\d+) → (\d+)\*\* \(95% upper ([\d.]+)%\)'
)
INJECTION_ALONE = re.compile(r'On \d+-\d+ each layer alone also reached (\d+)/(\d+)')
RAG_EVIDENCE = ROOT / 'evidence' / 'rag_set_d.jsonl'
# the rerank row of the "Search" table in docs/results.md
RAG_ROW = re.compile(
    r'\+ cross-encoder rerank [^|]*\| Set D \((\d+)\) \| top 1 (\d+) → \*\*(\d+)\*\*, top 5 \*\*(\d+)/(\d+)\*\*'
)


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


def review_sources(row, suffix, two_read):
    reasons = row[f'reasons{suffix}']
    if bool(reasons) != row[f'flagged{suffix}']:
        raise ValueError('Frozen flag and reasons disagree')
    sources = set()
    for code in reasons:
        if code in TECHNICAL_REASONS:
            sources.add(TECHNICAL_REASONS[code])
        elif code == 'other':  # export replaced the original code
            sources.add(UNAVAILABLE_LAYER)
        else:
            sources.add(layer_of(code))
    if two_read and row['disagree']:
        sources.add(DISAGREE_LAYER)
    return sources


def ratio(count, denominator):
    return count / denominator if denominator else None


def policy_metrics(cases, removed=None):
    if removed in PROTECTED_SOURCES:
        raise ValueError('Mandatory review sources cannot be removed')
    counts = Counter((bool(sources - {removed}), has_error) for sources, has_error in cases)
    n = len(cases)
    caught, silent = counts[True, True], counts[False, True]
    reviewed_without_error, automatic_without_error = counts[True, False], counts[False, False]
    reviewed = caught + reviewed_without_error
    automatic = n - reviewed
    return {
        'n': n,
        'reviewed': reviewed,
        'automatic': automatic,
        'flagged_errors': caught,
        'silent_errors': silent,
        'reviewed_no_recorded_error': reviewed_without_error,
        'automatic_no_recorded_error': automatic_without_error,
        'review_rate': ratio(reviewed, n),
        'automatic_coverage': ratio(automatic, n),
        'silent_error_rate': ratio(silent, n),
        'selective_risk': ratio(silent, automatic),
    }


def attribution_view(rows, run=None, two_read=False):
    suffix = f'_{run}' if run else ''
    cases = [(review_sources(row, suffix, two_read), row[f'error{suffix}'] is not None) for row in rows]
    not_run = SET_C_NOT_RUN if run is None else set()
    layers = {name for name, _ in LAYERS} | {MODEL_LAYER} | PROTECTED_SOURCES
    if two_read:
        layers.add(DISAGREE_LAYER)
    observed = Counter(layer for sources, _ in cases for layer in sources)
    if observed.keys() & not_run:
        raise ValueError('Frozen evidence contains a reason from a layer outside the experiment')

    baseline = policy_metrics(cases)
    by_layer = {}
    for layer in sorted(layers):
        if layer in not_run:
            by_layer[layer] = {'status': 'NOT_RUN_IN_EXPERIMENT'}
            continue
        unique = [has_error for sources, has_error in cases if sources == {layer}]
        stats = {
            'status': 'UNAVAILABLE' if layer == UNAVAILABLE_LAYER else 'IN_SCOPE',
            'flagged': observed[layer],
            'unique_flags': len(unique),
            'unique_catches': sum(unique),
            'protected': layer in PROTECTED_SOURCES,
        }
        if layer not in PROTECTED_SOURCES:
            without = policy_metrics(cases, removed=layer)
            stats['leave_one_out'] = without
            stats['marginal_reviewed'] = baseline['reviewed'] - without['reviewed']
            stats['marginal_catches'] = without['silent_errors'] - baseline['silent_errors']
        by_layer[layer] = stats

    overlap = []
    for a, b in combinations(sorted(layers - not_run), 2):
        both = sum(a in sources and b in sources for sources, _ in cases)
        overlap.append(
            {
                'a': a,
                'b': b,
                'intersection': both,
                'p_b_given_a': ratio(both, observed[a]),
                'p_a_given_b': ratio(both, observed[b]),
            }
        )

    multiplicity = Counter(len(sources) for sources, _ in cases)
    error_multiplicity = Counter(len(sources) for sources, has_error in cases if has_error)
    return {
        'baseline': baseline,
        'attribution_unit': 'recorded_reason_code_group',
        'shared_reason_code_producers': dict.fromkeys(sorted(SHARED_REASON_CODES), 'UNAVAILABLE'),
        'layers': by_layer,
        'pairwise_overlap': overlap,
        'coverage_multiplicity': [
            {'review_sources': k, 'cases': multiplicity[k], 'recorded_errors': error_multiplicity[k]}
            for k in sorted(multiplicity)
        ],
    }


def attribution_report():
    d_rows = load(SET_D_EVIDENCE)
    groups = {'all': d_rows, **{s: [row for row in d_rows if row['stratum'] == s] for s in ('R', 'U')}}
    return {
        'notes': [
            'Layer labels name frozen groups of recorded reason codes. Unique and marginal contributions '
            'measure those groups. The actual producer of a shared code is UNAVAILABLE.',
            'Baseline and leave-one-out metrics give empirical risk-coverage points for each view.',
            'Leave-one-out removes recorded reasons and holds outputs and frozen error labels fixed. '
            'It cannot recreate inference, short-circuits, downstream checks, or causal layer ablation.',
            'Run and judge errors remain mandatory review sources. Multiplicity counts recorded sources, '
            'including mandatory ones, rather than independent checks.',
            'Set D A and B are paired readings of the same cases. Two-read views add frozen disagreement '
            'to the selected reading and keep that reading’s frozen error label.',
            'Null error means no recorded frozen scoring error. Gold uncertainty, company identity, '
            'and case-level Matriks availability and source-check execution are UNAVAILABLE.',
            'In-scope checks can be skipped after extraction failure or lack required inputs. '
            'Source-check reasons can be produced without a judge call.',
            'Rates are empirical for these samples. Selecting a policy here does not establish generalization.',
        ],
        'set_c': attribution_view(load()),
        'set_d': {
            group: {
                'a': attribution_view(rows, 'a'),
                'b': attribution_view(rows, 'b'),
                'two_read_a': attribution_view(rows, 'a', two_read=True),
                'two_read_b': attribution_view(rows, 'b', two_read=True),
            }
            for group, rows in groups.items()
        },
    }


def main_attribution():
    argparse.ArgumentParser(description='Report aggregate attribution from frozen Set C and D evidence.').parse_args()
    print(json.dumps(attribution_report(), indent=2))


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


def published_rag(path=RESULTS_MD):
    """The Set D search numbers as docs/results.md states them."""
    hits = RAG_ROW.findall(path.read_text(encoding='utf-8'))
    if len(hits) != 1:
        raise SystemExit(f'expected one rerank row in {path.name}, found {len(hits)}')
    n, embed1, rerank1, rerank5, n5 = map(int, hits[0])
    if n != n5:
        raise SystemExit(f'rerank row in {path.name} disagrees on n')
    return {'n': n, 'embed_at1': embed1, 'rerank_at1': rerank1, 'rerank_at5': rerank5}


def recount_rag(rows):
    def at(k, key):
        return sum(1 for r in rows if r[key] is not None and r[key] <= k)

    return {
        'n': len(rows),
        'embed_at1': at(1, 'rank_embed'),
        'rerank_at1': at(1, 'rank_rerank'),
        'rerank_at5': at(5, 'rank_rerank'),
    }


def main_rag():
    rows = load(RAG_EVIDENCE)
    c, p = recount_rag(rows), published_rag()
    same = c == p
    embed5 = sum(1 for r in rows if r['rank_embed'] is not None and r['rank_embed'] <= 5)
    wrong_same = sum(1 for r in rows if r['rank_rerank'] != 1 and r['same_company_top1'])
    print(f'Search, Set D ({c["n"]} questions; rerun equal to the saved run, top 10 of every question)')
    print(f'  embedding only: rank 1 {c["embed_at1"]}/{c["n"]}, top 5 {embed5}/{c["n"]}')
    print(f'  + rerank: rank 1 {c["rerank_at1"]}/{c["n"]}, top 5 {c["rerank_at5"]}/{c["n"]}')
    print(f'  rank-1 misses with the right company first: {wrong_same} of {c["n"] - c["rerank_at1"]}')
    print(
        f'  docs/results.md (read now) says rank 1 {p["embed_at1"]} → {p["rerank_at1"]}, '
        f'top 5 {p["rerank_at5"]}/{p["n"]}: ' + ('MATCH' if same else 'MISMATCH')
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
    argparse.ArgumentParser(description='Check all five frozen results against public evidence.').parse_args()
    ok = main_set_c()
    ok = main_regex() and ok  # run all, so a mismatch in one does not hide the others
    ok = main_set_d() and ok
    ok = main_injection() and ok
    ok = main_rag() and ok
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
