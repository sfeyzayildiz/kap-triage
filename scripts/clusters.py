'''Theme clusters over all disclosures (rules: docs/clustering_rule.md).

Embeds each disclosure's normalized text WITHOUT the header (no symbol), runs spherical
k-means, names each cluster by its most distinctive words, and (after the sector pull)
compares company-level clusters with Matriks sector labels.
Outputs go to data/ (theme words come from disclosure text). Stdout: counts and metrics only.

Usage:
  python scripts/clusters.py --self-test
  python scripts/clusters.py --build --k 12          # provisional, development only
  python scripts/clusters.py --evaluate              # once, after the sector labels exist
  python scripts/clusters.py --week 2026-11-05       # cluster counts for that ISO week
'''
import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import date, timedelta

import numpy as np

SEED=20261109
N_INIT=10
MAX_ITER=100
VECTORS_PATH='data/cluster_vectors.npz'
OUT_PATH='data/clusters.json'
SECTOR_TABLE='symbol_sectors'  # (symbol, sector), written by the sector loader
WORD_RE=re.compile(r'[a-zçğıöşüâîû]{4,}')
N_SHUFFLES=1000


# --- k-means on unit vectors ---
def kmeanspp(X,k,rng):
    centers=[int(rng.integers(len(X)))]
    dist=1-X@X[centers[0]]
    for _ in range(1,k):
        p=np.clip(dist,0,None)**2
        p=p/p.sum() if p.sum()>0 else np.full(len(X),1/len(X))
        centers.append(int(rng.choice(len(X),p=p)))
        dist=np.minimum(dist,1-X@X[centers[-1]])
    return X[centers].copy()


def spherical_kmeans(X,k,seed=SEED,n_init=N_INIT,max_iter=MAX_ITER):
    '''Returns (labels, centroids, total cosine to the assigned centroid) of the best restart.'''
    rng=np.random.default_rng(seed)
    best=None
    for _ in range(n_init):
        C=kmeanspp(X,k,rng)
        labels=None
        for _ in range(max_iter):
            new=np.argmax(X@C.T,axis=1)
            if labels is not None and np.array_equal(new,labels):
                break
            labels=new
            for j in range(k):
                members=X[labels==j]
                if len(members):
                    c=members.sum(axis=0)
                    C[j]=c/np.linalg.norm(c)
        score=float(np.sum(np.max(X@C.T,axis=1)))
        if best is None or score>best[2]:
            best=(labels.copy(),C.copy(),score)
    return best


# --- agreement metrics ---
def _comb2(x):
    return x*(x-1)/2


def contingency(a,b):
    ia={v:i for i,v in enumerate(sorted(set(a),key=str))}
    ib={v:i for i,v in enumerate(sorted(set(b),key=str))}
    m=np.zeros((len(ia),len(ib)),dtype=np.int64)
    for x,y in zip(a,b):
        m[ia[x],ib[y]]+=1
    return m


def ari(a,b):
    m=contingency(a,b)
    n=m.sum()
    s_ij=_comb2(m).sum()
    s_a=_comb2(m.sum(axis=1)).sum()
    s_b=_comb2(m.sum(axis=0)).sum()
    expected=s_a*s_b/_comb2(n) if n>1 else 0.0
    top=(s_a+s_b)/2
    if top==expected:
        return 1.0 if s_ij==top else 0.0
    return float((s_ij-expected)/(top-expected))


def nmi(a,b):
    m=contingency(a,b).astype(np.float64)
    n=m.sum()
    pa,pb=m.sum(axis=1)/n,m.sum(axis=0)/n
    nz=m>0
    mi=float(np.sum(m[nz]/n*np.log((m[nz]/n)/np.outer(pa,pb)[nz])))
    h=lambda p:-float(np.sum(p[p>0]*np.log(p[p>0])))
    denom=h(pa)+h(pb)
    return 2*mi/denom if denom>0 else 1.0


def purity(clusters,labels):
    m=contingency(clusters,labels)
    return float(m.max(axis=1).sum()/m.sum())


def company_clusters(symbols,labels):
    '''Each company's most frequent cluster; ties go to the lowest cluster id.'''
    by=Counter(zip(symbols,labels))
    out={}
    for (s,c),n in sorted(by.items(),key=lambda x:(x[0][0],-x[1],x[0][1])):
        out.setdefault(s,c)
    return out


def shuffled_aris(company_cluster,company_sector,n=N_SHUFFLES,seed=SEED):
    syms=sorted(company_sector)
    clus=[company_cluster[s] for s in syms]
    sect=np.array([company_sector[s] for s in syms],dtype=object)
    rng=np.random.default_rng(seed)
    return [ari(clus,list(rng.permutation(sect))) for _ in range(n)]


# --- theme words ---
def theme_words(texts,labels,k,top=5,min_docs=5,symbols=None,min_companies=3):
    '''Most distinctive words per cluster; a word must also span min_companies companies (Amendment 1).'''
    from eval_retrieval import tr_lower
    doc_words=[set(WORD_RE.findall(tr_lower(t))) for t in texts]
    overall=Counter(w for ws in doc_words for w in ws)
    n=len(texts)
    out={}
    for c in range(k):
        idx=[i for i,l in enumerate(labels) if l==c]
        if not idx:
            out[c]=[]
            continue
        inside=Counter(w for i in idx for w in doc_words[i])
        spread={}
        if symbols is not None:
            for i in idx:
                for w in doc_words[i]:
                    spread.setdefault(w,set()).add(symbols[i])
        ok=lambda w:inside[w]>=min_docs and (symbols is None or len(spread[w])>=min_companies)
        scored=[((inside[w]/len(idx))/(overall[w]/n),w) for w in inside if ok(w)]
        out[c]=[w for _,w in sorted(scored,key=lambda x:(-x[0],x[1]))[:top]]
    return out


# --- data steps ---
def load_texts():
    from build_docs import DB_PATH, load_rows
    from normalize import normalize
    return [{'news_id':str(nid),'symbol':sym,'published_at':str(pub),'text':normalize(text or '')}
            for nid,url,sym,pub,upd,corr,head,text in load_rows(DB_PATH)]


def vectors_for(docs):
    key=hashlib.sha1('\n'.join(d['news_id']+d['text'] for d in docs).encode('utf-8')).hexdigest()
    if os.path.exists(VECTORS_PATH):
        cached=np.load(VECTORS_PATH)
        if str(cached['key'])==key:
            return cached['vectors']
    from rag_index import embed_docs
    v=embed_docs([d['text'] for d in docs])
    np.savez(VECTORS_PATH,vectors=v,key=key)
    return v


def build(k):
    docs=load_texts()
    X=vectors_for(docs)
    labels,_,score=spherical_kmeans(X,k)
    themes=theme_words([d['text'] for d in docs],labels,k,symbols=[d['symbol'] for d in docs])
    out={'k':k,'seed':SEED,'n_docs':len(docs),'score':score,'themes':{str(c):w for c,w in themes.items()},
         'assign':[{'news_id':d['news_id'],'symbol':d['symbol'],'published_at':d['published_at'],'cluster':int(l)}
                   for d,l in zip(docs,labels)]}
    with open(OUT_PATH,'w',encoding='utf-8') as f:
        json.dump(out,f,ensure_ascii=False)
    sizes=Counter(int(l) for l in labels)
    companies={c:len({d['symbol'] for d,l in zip(docs,labels) if l==c}) for c in range(k)}
    print(f'docs={len(docs)} k={k} -> {OUT_PATH} (theme words there, not printed)')
    for c in range(k):
        print(f'cluster {c:2}: {sizes[c]:4} docs, {companies[c]:3} companies')
    print(f'doc-level ARI vs company {ari([d["symbol"] for d in docs],list(labels)):.3f}')


def load_sectors():
    import duckdb
    from build_docs import DB_PATH
    con=duckdb.connect(DB_PATH,read_only=True)
    try:
        return dict(con.execute(f'SELECT symbol,sector FROM {SECTOR_TABLE} WHERE sector IS NOT NULL').fetchall())
    finally:
        con.close()


def evaluate():
    with open(OUT_PATH,encoding='utf-8') as f:
        out=json.load(f)
    sectors=load_sectors()
    rows=[a for a in out['assign'] if a['symbol'] in sectors]
    syms=[a['symbol'] for a in rows]
    labels=[a['cluster'] for a in rows]
    n_sectors=len({sectors[s] for s in set(syms)})
    if out['k']!=n_sectors:
        raise SystemExit(f'clusters.json has k={out["k"]}, rule needs k={n_sectors} (sectors among companies): rebuild with --build --k {n_sectors}')
    cc=company_clusters(syms,labels)
    cs={s:sectors[s] for s in cc}
    primary=ari([cc[s] for s in sorted(cc)],[cs[s] for s in sorted(cc)])
    null=sorted(shuffled_aris(cc,cs))
    p99=null[int(0.99*len(null))-1]
    sect=[sectors[s] for s in syms]
    print(f'docs={len(rows)} of {out["n_docs"]} with sector, companies={len(cc)}, sectors={n_sectors}, k={out["k"]}')
    print(f'PRIMARY company-level ARI vs sector {primary:.3f}; shuffled p99 {p99:.3f}, max {null[-1]:.3f}')
    print('decision: clusters reflect sector' if primary>p99 else 'decision: clusters not aligned with sector')
    print(f'doc-level: ARI {ari(labels,sect):.3f}, NMI {nmi(labels,sect):.3f}, purity {purity(labels,sect):.3f}; '
          f'ARI vs company {ari(labels,syms):.3f}')


def week(day):
    with open(OUT_PATH,encoding='utf-8') as f:
        out=json.load(f)
    d=date.fromisoformat(day)
    start=d-timedelta(days=d.weekday())
    end=start+timedelta(days=7)
    rows=[a for a in out['assign'] if str(start)<=a['published_at'][:10]<str(end)]
    print(f'week {start}..{end-timedelta(days=1)}: {len(rows)} disclosures')
    for c,n in Counter(a['cluster'] for a in rows).most_common():
        print(f'cluster {c}: {n}')


def _self_test():
    rng=np.random.default_rng(0)
    centers=np.eye(3)
    X=np.vstack([c+0.05*rng.standard_normal((20,3)) for c in centers])
    X=X/np.linalg.norm(X,axis=1,keepdims=True)
    labels,_,_=spherical_kmeans(X,3,seed=1,n_init=3)
    truth=[0]*20+[1]*20+[2]*20
    assert ari(labels,truth)==1.0                       # separable groups are found
    assert abs(ari([0,0,1,1],[0,0,1,1])-1)<1e-12 and abs(ari([0,0,1,1],['a','a','b','b'])-1)<1e-12
    assert ari([0,1,0,1],[0,0,1,1])<0                   # anti-aligned is below chance
    assert abs(nmi([0,0,1,1],[1,1,0,0])-1)<1e-12 and nmi([0,0,0,0],[0,1,0,1])<1e-12
    assert purity([0,0,1,1],['a','b','b','b'])==0.75
    assert company_clusters(['A','A','A','B'],[2,1,1,0])=={'A':1,'B':0}
    assert company_clusters(['A','A'],[3,1])=={'A':1}   # tie -> lowest id
    null=shuffled_aris({s:i%2 for i,s in enumerate('abcdefgh')},{s:i%2 for i,s in enumerate('abcdefgh')},n=50)
    assert len(null)==50 and max(null)<=1.0
    texts=['savunma sistemleri ihracat']*6+['enerji santrali kurulum']*6
    th=theme_words(texts,[0]*6+[1]*6,2,top=2)
    assert set(th[0])<={'savunma','sistemleri','ihracat'} and set(th[1])<={'enerji','santrali','kurulum'}
    assert len(th[0])==2 and theme_words(texts,[0]*12,2)[1]==[]  # an empty cluster gets no words, no crash
    # Amendment 1: a word used by only one company (e.g. its name) is not a theme word
    t2=['acmeholding savunma']*3+['savunma radar']*3+['enerji santrali']*6
    syms=['ACME']*3+['B','C','D']+['E','F','G','H','I','J']
    th2=theme_words(t2,[0]*6+[1]*6,2,top=5,min_docs=2,symbols=syms)
    assert 'acmeholding' not in th2[0] and 'savunma' in th2[0]
    assert 'acmeholding' in theme_words(t2,[0]*6+[1]*6,2,top=5,min_docs=2)[0]  # without the company rule it would be kept
    print('self-test ok: 15 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--build',action='store_true')
    ap.add_argument('--k',type=int)
    ap.add_argument('--evaluate',action='store_true')
    ap.add_argument('--week')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.build:
        if not args.k:
            ap.error('--build needs --k')
        build(args.k)
    elif args.evaluate:
        evaluate()
    elif args.week:
        week(args.week)
    else:
        ap.error('give --build --k K, --evaluate, --week DATE or --self-test')


if __name__=='__main__':
    main()
