'''Search index over all disclosures with the chosen embedding model (docs/rag_model_choice.md).

One vector per disclosure (same document text as build_docs.py). The index is updated
incrementally: only new or changed texts are embedded. Stored in data/rag_index.npz.
Stdout shows only counts, ids and similarity scores.

Usage:
  python scripts/rag_index.py --self-test
  python scripts/rag_index.py --build
  python scripts/rag_index.py --similar NEWS_ID
'''
import argparse
import hashlib
import os
import time
from functools import lru_cache

import numpy as np

from build_docs import DB_PATH, header, load_rows
from eval_retrieval import MODELS, unit
from normalize import normalize

MODEL='ytu-ce-cosmos/turkish-e5-large'
INDEX_PATH='data/rag_index.npz'
BATCH_SIZE=16
META=('news_id','kap_url','symbol','published_at','sha1')


def doc_text(sym,pub,upd,corr,head,text):
    return header(sym,pub,upd,corr,head)+'\n'+normalize(text)


def sha1(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import SentenceTransformer
    m=SentenceTransformer(MODEL,device='mps' if torch.backends.mps.is_available() else 'cpu')
    m.max_seq_length=MODELS[MODEL]['max_tokens']
    return m


def embed_docs(texts):
    '''Documents get no prefix (model card).'''
    return unit(model().encode(texts,batch_size=BATCH_SIZE,convert_to_numpy=True,show_progress_bar=False).astype(np.float32))


def embed_query(question):
    q=MODELS[MODEL]['query'].format(q=question)
    return embed_docs([q])[0]


def load_index(path=INDEX_PATH):
    if not os.path.exists(path):
        return None
    data=np.load(path,allow_pickle=False)
    return {k:data[k] for k in ('vectors',)+META}


def merge(index,docs,embed):
    '''Keep vectors whose (news_id, sha1) is unchanged; embed the rest. Returns (index, n_embedded).'''
    old={}
    if index is not None:
        old={(n,s):i for i,(n,s) in enumerate(zip(index['news_id'],index['sha1']))}
    todo=[d for d in docs if (d['news_id'],d['sha1']) not in old]
    new_vecs=dict(zip([(d['news_id'],d['sha1']) for d in todo],embed([d['text'] for d in todo]) if todo else []))
    vectors=[index['vectors'][old[(d['news_id'],d['sha1'])]] if (d['news_id'],d['sha1']) in old else new_vecs[(d['news_id'],d['sha1'])] for d in docs]
    out={'vectors':np.array(vectors,dtype=np.float32)}
    for k in META:
        out[k]=np.array([d[k] for d in docs])
    return out,len(todo)


def update(path=INDEX_PATH):
    docs=[]
    for nid,url,sym,pub,upd,corr,head,text in load_rows(DB_PATH):
        t=doc_text(sym,pub,upd,corr,head,text)
        docs.append({'news_id':str(nid),'kap_url':url or '','symbol':sym or '','published_at':str(pub),'sha1':sha1(t),'text':t})
    index,n=merge(load_index(path),docs,embed_docs)
    np.savez(path,**index)
    return index,n


def search(index,query_vector,symbol=None,before=None,exclude=None,k=5):
    '''Top k by cosine similarity, optionally only one symbol and only before a timestamp string.'''
    mask=np.ones(len(index['news_id']),dtype=bool)
    if symbol:
        mask&=index['symbol']==symbol
    if before:
        mask&=index['published_at']<before
    if exclude:
        mask&=index['news_id']!=exclude
    scores=np.where(mask,index['vectors']@query_vector,-np.inf)
    order=[i for i in np.argsort(-scores,kind='stable')[:k] if np.isfinite(scores[i])]
    return [{'news_id':str(index['news_id'][i]),'kap_url':str(index['kap_url'][i]),'symbol':str(index['symbol'][i]),
             'published_at':str(index['published_at'][i]),'score':float(scores[i])} for i in order]


RERANK_K=20  # docs/rerank_rule.md: adopted 2026-11-08 for question search


def doc_texts(news_ids):
    '''Document text (same as the index input) for the given ids; one short read-only DB read.'''
    wanted=set(news_ids)
    return {str(nid):doc_text(sym,pub,upd,corr,head,text)
            for nid,url,sym,pub,upd,corr,head,text in load_rows(DB_PATH) if str(nid) in wanted}


@lru_cache(maxsize=1)
def reranker():
    from eval_retrieval import cross_encoder
    return cross_encoder()


def rerank_hits(question,hits,texts,score):
    '''Reorder hits by score(question, text) (stable on ties); hits without text keep their place at the end.'''
    with_text=[h for h in hits if h['news_id'] in texts]
    rest=[h for h in hits if h['news_id'] not in texts]
    if not with_text:
        return hits
    s=score([(question,texts[h['news_id']]) for h in with_text])
    order=np.argsort(-np.asarray(s),kind='stable')
    return [{**with_text[i],'rerank_score':float(s[i])} for i in order]+rest


def search_question(index,question,symbol=None,k=5,score=None,texts=None):
    '''Question search as measured: embed the question, top RERANK_K, cross-encoder rerank, top k.'''
    hits=search(index,embed_query(question),symbol=symbol,k=RERANK_K)
    texts=texts if texts is not None else doc_texts([h['news_id'] for h in hits])
    score=score or (lambda pairs:reranker().predict(pairs,show_progress_bar=False))
    return rerank_hits(question,hits,texts,score)[:k]


def similar_earlier(index,news_id,k=3):
    '''The same company's earlier disclosures most similar to this one.'''
    hits=np.where(index['news_id']==str(news_id))[0]
    if not len(hits):
        return []
    i=hits[0]
    return search(index,index['vectors'][i],symbol=str(index['symbol'][i]),before=str(index['published_at'][i]),k=k)


def _self_test():
    def fake_embed(texts):
        return unit(np.array([[len(t),t.count('a')+1,1.0] for t in texts],dtype=np.float32))
    docs=[{'news_id':str(i),'kap_url':f'u{i}','symbol':s,'published_at':p,'text':t,'sha1':sha1(t)}
          for i,(s,p,t) in enumerate([('AAA','2026-01-01 09:00:00','aaaa'),('AAA','2026-02-01 09:00:00','aaab'),
                                     ('BBB','2026-02-15 09:00:00','aaaa'),('AAA','2026-03-01 09:00:00','aaaa x')])]
    index,n=merge(None,docs,fake_embed)
    assert n==4 and index['vectors'].shape==(4,3)
    index2,n=merge(index,docs,fake_embed)
    assert n==0 and np.allclose(index2['vectors'],index['vectors'])
    changed=docs[:3]+[{**docs[3],'text':'b','sha1':sha1('b')}]
    _,n=merge(index,changed,fake_embed)
    assert n==1
    sim=similar_earlier(index,'3')
    assert {h['news_id'] for h in sim}=={'0','1'} and all(h['symbol']=='AAA' for h in sim)
    assert sim[0]['score']>=sim[1]['score']
    assert similar_earlier(index,'0')==[] and similar_earlier(index,'99')==[]
    hits=search(index,index['vectors'][0],exclude='0',k=2)
    assert len(hits)==2 and '0' not in [h['news_id'] for h in hits]
    # rerank: score decides, ties keep the embedding order, hits without text go last
    h=[{'news_id':'a'},{'news_id':'b'},{'news_id':'c'},{'news_id':'d'}]
    out=rerank_hits('q',h,{'a':'x','b':'yy','c':'zz'},lambda pairs:[len(t) for _,t in pairs])
    assert [x['news_id'] for x in out]==['b','c','a','d'] and out[0]['rerank_score']==2.0
    assert rerank_hits('q',h,{},lambda pairs:[])==h
    print('self-test ok: 10 checks')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--build',action='store_true',help='create or update data/rag_index.npz')
    ap.add_argument('--similar',help='earlier disclosures of the same company like NEWS_ID')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:
        _self_test()
        return
    if args.build:
        start=time.time()
        index,n=update()
        print(f'docs={len(index["news_id"])} embedded={n} seconds={time.time()-start:.0f} -> {INDEX_PATH}')
    if args.similar:
        index=load_index()
        for h in similar_earlier(index,args.similar):
            print(h['news_id'],h['published_at'][:10],f'{h["score"]:.3f}')
    if not (args.build or args.similar):
        ap.error('give --build, --similar or --self-test')


if __name__=='__main__':
    main()
