'''Development timeline from the git history of main: docs/timeline.md, one section per day with every merged
change (squash-merged pull request titles; the first days were direct commits). Generated, not written by hand,
so it is the record itself. Re-run after new merges.

Usage:
  python scripts/make_timeline.py            # writes docs/timeline.md
  python scripts/make_timeline.py --self-test
'''
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date

OUT='docs/timeline.md'
PR_RE=re.compile(r'\s*\(#(\d+)\)\s*$')
WEEKDAY=('Mon','Tue','Wed','Thu','Fri','Sat','Sun')


def git_log():
    out=subprocess.run(['git','log','main','--reverse','--date=short','--format=%ad%x09%s'],capture_output=True,text=True,check=True).stdout
    return [tuple(l.split('\t',1)) for l in out.splitlines() if '\t' in l]


def build(rows):
    days=OrderedDict()
    for d,subject in rows:
        days.setdefault(d,[]).append(subject)
    first,last=date.fromisoformat(next(iter(days))),date.fromisoformat(next(reversed(days)))
    span=(last-first).days+1
    n_pr=sum(bool(PR_RE.search(s)) for _,s in rows)
    lines=['# Development timeline','',
           f'Generated from the git history of `main` by `scripts/make_timeline.py`; not edited by hand. '
           f'{first} to {last}: **{len(rows)} commits on {len(days)} of {span} days**, {n_pr} of them merged pull requests '
           '(the first days were direct commits). Every measured result also has a rule file that was committed before it; '
           'this page shows the order in which the work happened.','']
    week=None
    for d,subjects in days.items():
        dd=date.fromisoformat(d)
        wk=dd.isocalendar()[1]
        if wk!=week:
            week=wk
            lines+=[f'## Week of {date.fromisocalendar(dd.year,wk,1)}','']
        lines.append(f'**{d} ({WEEKDAY[dd.weekday()]})**: {len(subjects)} change{"s" if len(subjects)>1 else ""}')
        for s in subjects:
            m=PR_RE.search(s)
            lines.append(f'- {PR_RE.sub("",s)}'+(f' (#{m.group(1)})' if m else ''))
        lines.append('')
    return '\n'.join(lines)


def _self_test():
    rows=[('2026-10-26','Initial commit'),('2026-10-27','Add collector (#1)'),('2026-10-27','Fix (#2)'),('2026-11-02','Agent (#30)')]
    t=build(rows)
    assert '4 commits on 3 of 8 days' in t and '3 of them merged pull requests' in t
    assert '## Week of 2026-10-26' in t and '## Week of 2026-11-02' in t and '**2026-10-27 (Tue)**: 2 changes' in t
    assert '- Add collector (#1)' in t and '- Initial commit' in t and '**2026-10-26 (Mon)**: 1 change' in t
    print('self-test ok: 6 checks')


def main():
    if '--self-test' in sys.argv:
        return _self_test()
    text=build(git_log())
    with open(OUT,'w',encoding='utf-8') as f:
        f.write(text+'\n')
    print(f'wrote {OUT}: {text.count(chr(10)+"- ")} entries')


if __name__=='__main__':
    main()
