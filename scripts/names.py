'''Company name -> ticker lookup (docs/router_v2_rule.md).

Name table data/company_names.txt, one line per disclosure symbol, filled by Feyza:
  FONET: Fonet; Fonet Bilgi Teknolojileri
Empty after the colon = no name. Lines starting with # are comments.

mentions(question, symbols, names): companies written in the question, in order of appearance:
tickers written in capitals (as agent.validate does today) plus name matches (Turkish lower case,
ASCII fold; a name's words in order as whole words, the last word may carry a suffix if it has
at least 4 letters).

Usage:
  python scripts/names.py --self-test
  python scripts/names.py --template     # write the table with every disclosure symbol (refuses to overwrite)
  python scripts/names.py --check        # counts and sha1 only
'''
import argparse
import hashlib
import os
import re

NAMES_PATH='data/company_names.txt'
DB_PATH='data/kap.duckdb'
TOKEN_RE=re.compile(r'[^\W_]+')
FOLD=str.maketrans({'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u','â':'a','î':'i','û':'u'})
MIN_SUFFIX_WORD=4


def fold(word):
    return word.replace('İ','i').replace('I','ı').lower().translate(FOLD)


def tokens(text):
    '''(original, folded) words of a text.'''
    return [(m.group(0),fold(m.group(0))) for m in TOKEN_RE.finditer(text or '')]


def parse_names(text):
    '''[(folded words tuple, symbol)] from the table text; also the number of symbols with a name.'''
    out,filled=[],0
    for line in (text or '').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        sym,_,rest=line.partition(':')
        sym=sym.strip().upper()
        names=[n.strip() for n in rest.split(';') if n.strip()]
        filled+=bool(names)
        for n in names:
            words=tuple(f for _,f in tokens(n))
            if words and sum(len(w) for w in words)>=3:
                out.append((words,sym))
    return out,filled


def load_names(path=NAMES_PATH):
    if not os.path.exists(path):
        return []
    with open(path,encoding='utf-8') as f:
        return parse_names(f.read())[0]


def file_sha1(path=NAMES_PATH):
    with open(path,'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def _match_at(q,i,words):
    n=len(words)
    if i+n>len(q):
        return False
    if any(q[i+j]!=words[j] for j in range(n-1)):
        return False
    last=words[-1]
    return q[i+n-1]==last or (len(last)>=MIN_SUFFIX_WORD and q[i+n-1].startswith(last))


def mentions(question,symbols,names):
    '''Symbols written in the question (ticker in capitals or a name), ordered by first position.'''
    toks=tokens(question)
    folded=[f for _,f in toks]
    first={}
    for i,(orig,_) in enumerate(toks):
        if orig.isupper() and orig in symbols and orig not in first:
            first[orig]=i
    for words,sym in names:
        if sym not in symbols:
            continue
        for i in range(len(folded)):
            if _match_at(folded,i,words):
                first[sym]=min(first.get(sym,i),i)
                break
    return [s for s,_ in sorted(first.items(),key=lambda kv:kv[1])]


def template(path=NAMES_PATH):
    import duckdb
    if os.path.exists(path):
        raise SystemExit(f'{path} exists; not overwritten')
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        syms=[r[0] for r in con.execute('SELECT DISTINCT symbol FROM disclosures WHERE symbol IS NOT NULL ORDER BY 1').fetchall()]
    finally:
        con.close()
    with open(path,'w',encoding='utf-8') as f:
        f.write('# One line per company: CODE: name; other name. Distinctive names only (not "Holding" or "Enerji" alone).\n')
        for s in syms:
            f.write(f'{s}: \n')
    print(f'template written: {len(syms)} symbols -> {path}')


def check(path=NAMES_PATH):
    if not os.path.exists(path):
        raise SystemExit(f'{path} missing; run --template first')
    with open(path,encoding='utf-8') as f:
        names,filled=parse_names(f.read())
    syms=[l.split(':')[0].strip() for l in open(path,encoding='utf-8') if ':' in l and not l.startswith('#')]
    clash={}
    for words,sym in names:
        clash.setdefault(words,set()).add(sym)
    shared=sum(len(v)>1 for v in clash.values())
    print(f'symbols={len(syms)} with_name={filled} names={len(names)} shared_names={shared} sha1={file_sha1(path)}')


def _self_test():
    table='# c\nFONET: Fonet; Fonet Bilgi Teknolojileri\nASELS: Aselsan\nASTOR: Astor Enerji\nTUPRS: \nX: ab\n'
    names,filled=parse_names(table)
    assert filled==4 and ('ab',) not in [w for w,_ in names]                       # too short a name is dropped
    syms={'FONET','ASELS','ASTOR','TUPRS','KONTR'}
    assert mentions('Fonet Bilgi Teknolojileri\'nin Aydın sözleşmesi',syms,names)==['FONET']
    assert mentions('Aselsan\'ın Irak işi',syms,names)==['ASELS']                    # suffix after apostrophe
    assert mentions('Aselsanın son işleri',syms,names)==['ASELS']                    # suffix glued on
    assert mentions('ASELSAN İŞLERİ',syms,names)==['ASELS']                           # capitals fold
    assert mentions('Aselsan ASTOR ile anlaştı mı',syms,names)==['ASELS','ASTOR']    # order of appearance
    assert mentions('ASTOR ile Aselsan',syms,names)==['ASTOR','ASELS']
    assert mentions('astor enerjinin sözleşmesi',syms,names)==['ASTOR']
    assert mentions('KONTR neden yükseldi',syms,names)==['KONTR']                   # ticker without a name row
    assert mentions('kontr neden yükseldi',syms,names)==[]                          # lower-case ticker is not a ticker
    assert mentions('enerji sözleşmeleri',syms,names)==[]                           # a later word alone does not match
    assert mentions('Fonetik bir soru',syms,[(('fon',),'FONET')])==[]               # short name: no suffix match
    assert fold('İSTANBUL')=='istanbul' and fold('IĞDIR')=='igdir'
    print('self-test ok: 13 checks')


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group(required=True)
    for flag in ('--template','--check','--self-test'):
        g.add_argument(flag,action='store_true')
    a=ap.parse_args()
    if a.self_test:
        _self_test()
    elif a.template:
        template()
    else:
        check()


if __name__=='__main__':
    main()
