'''Operational quantities in a disclosure text, found by code (rule: docs/card_quantities_rule.md).

find_quantities(text): a number (Turkish format, optional bin/milyon/milyar) directly followed by a unit
from a fixed list; written as in the text, in text order, at most 6, duplicates removed. No LLM.

Usage:
  python scripts/quantities.py --self-test
  python scripts/quantities.py --review     # Feyza: 15 sampled disclosures, y/n + missed count (resumable)
  python scripts/quantities.py --score      # counts only, decision
'''
import argparse
import json
import os
import random
import re
import sys
import textwrap

DB_PATH='data/kap.duckdb'
REVIEW='data/quantities_review.jsonl'
QUESTION_FILES=('data/rag_questions.jsonl','data/rag_questions_c.jsonl','data/rag_questions_d.jsonl',
                'data/card_questions.jsonl','data/v2_questions.jsonl')
SEED=20261110
N_REVIEW=15
BAR=14
MAX_ITEMS=6

WORD_UNITS=('metrekare','kilometre','megavat','adet','ton')   # may carry a Turkish suffix (adetlik, tonluk)
SYMBOL_UNITS=('MWm','MWe','MWp','MWh','kWh','kWp','GWh','MW','kW','GW','km','m²','m2','m³','m3')
# Turkish case/derivation suffixes a word unit may carry ("adetlik", "tonluk", "adetten"); nothing else
SUFFIX=r"(?:'?(?:lık|lik|luk|lük|dan|den|tan|ten|da|de|ta|te|lar|ler|u|ü|ı|i|a|e|un|ün|ın|in))?"
NUM=r'(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)'
SCALE=r'(?:\s*(?:bin|milyon|milyar))?'
QTY_RE=re.compile(NUM+SCALE+r'\s*(?:'
                  r'(?:'+'|'.join(WORD_UNITS)+r')(?='+SUFFIX+r'(?![A-Za-zÇĞİÖŞÜçğıöşü0-9]))'
                  r'|(?:'+'|'.join(re.escape(u) for u in SYMBOL_UNITS)+r')(?![A-Za-zÇĞİÖŞÜçğıöşü0-9²³])'
                  r')',re.I)


def find_quantities(text):
    out=[]
    for m in QTY_RE.finditer(text or ''):
        q=' '.join(m.group(0).split())
        if q not in out:
            out.append(q)
        if len(out)>=MAX_ITEMS:
            break
    return out


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path,encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def sample(rows,excluded,seed=SEED,n=N_REVIEW):
    pool=sorted((r for r in rows if str(r[0]) not in excluded and (r[1] or '').strip()),key=lambda r:str(r[0]))
    random.Random(seed).shuffle(pool)
    return pool[:n]


def review():
    import duckdb
    excluded={str(q['news_id']) for p in QUESTION_FILES for q in read_jsonl(p)}
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        rows=con.execute('SELECT news_id,aciklama FROM disclosures').fetchall()
    finally:
        con.close()
    rows=[r for r in rows if find_quantities(r[1])]  # Amendment 1: only texts where the code finds a quantity
    picked=sample(rows,excluded)
    done={r['news_id'] for r in read_jsonl(REVIEW)}
    print(f'{len(picked)} disclosures, {len(done)} reviewed. q stops.')
    for i,(nid,text) in enumerate(picked,1):
        if str(nid) in done:
            continue
        print('\n'+'='*90+f'\n[{i}/{len(picked)}] news_id={nid}\n'+'-'*90)
        for para in text.splitlines():
            if para.strip():
                print(textwrap.fill(para,100))
        found=find_quantities(text)
        print('-'*90+'\nfound by code: '+('; '.join(found) if found else '(none)'))
        while True:
            a=input('(a) is every listed item a real quantity of this deal? [y/n, q=quit] ').strip().lower()
            if a in ('y','n','q'):
                break
        if a=='q':
            return
        while True:
            m=input('(b) how many quantities with these units did the code miss? [number] ').strip()
            if m.isdigit():
                break
        with open(REVIEW,'a',encoding='utf-8') as f:
            f.write(json.dumps({'news_id':str(nid),'ok':a=='y','missed':int(m),'found':len(found)})+'\n')
    print('review complete; next: --score')


def score(rows):
    return {'n':len(rows),'ok':sum(r['ok'] for r in rows),'found':sum(r['found'] for r in rows),
            'with_any':sum(r['found']>0 for r in rows),'missed':sum(r['missed'] for r in rows),
            'show':len(rows)==N_REVIEW and sum(r['ok'] for r in rows)>=BAR}


def print_score():
    rows=read_jsonl(REVIEW)
    if len(rows)!=N_REVIEW:
        raise SystemExit(f'INCOMPLETE {len(rows)}/{N_REVIEW}')
    s=score(rows)
    print(f'list correct {s["ok"]}/{s["n"]} (bar {BAR})  disclosures with a quantity {s["with_any"]}  '
          f'items found {s["found"]}  missed {s["missed"]}')
    print('decision: '+('SHOW_QUANTITIES' if s['show'] else 'QUANTITIES_OFF'))


def _self_test():
    t='Şirketimiz 20 adet araç ve 1.250 adetlik yedek parça için anlaşmıştır. 505 MWm kapasiteli santral; 12,5 MW ek.'
    assert find_quantities(t)==['20 adet','1.250 adet','505 MWm','12,5 MW']
    assert find_quantities('3 milyon ton cevher, 150 km hat, 25.000 m² alan, 40 MWh depolama')==\
        ['3 milyon ton','150 km','25.000 m²','40 MWh']
    assert find_quantities('15.000.000 USD tutarında, 3 yıl süreli, 2026 yılında')==[]          # money, duration, year
    assert find_quantities('20 adetten fazla')==['20 adet'] and find_quantities('5 tonluk')==['5 ton']
    assert find_quantities('10 kmh değil, 7 kmlik')==[]                                       # symbol units take no suffix
    assert find_quantities('Tonga 3 Tonga')==[] and find_quantities('5 MW 5 MW')==['5 MW']
    assert len(find_quantities(' '.join(f'{i} adet' for i in range(1,10))))==MAX_ITEMS
    rows=[(str(i),'x') for i in range(40)]+[('99','')]
    a=sample(rows,{'3'})
    assert len(a)==N_REVIEW and '3' not in [r[0] for r in a] and a==sample(list(reversed(rows)),{'3'})
    rv=[{'ok':True,'missed':1,'found':2}]*14+[{'ok':False,'missed':0,'found':1}]
    assert score(rv)['show'] and not score(rv[:13]+[rv[-1]]*2)['show'] and score(rv)['missed']==14
    print('self-test ok: 9 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    for flag in ('--review','--score','--self-test'):
        g.add_argument(flag,action='store_true')
    a=ap.parse_args()
    if a.self_test:
        _self_test()
    elif a.review:
        review()
    else:
        print_score()


if __name__=='__main__':
    main()
