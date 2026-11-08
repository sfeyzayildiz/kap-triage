'''Evaluate one embedding model on the RAG questions (rule: docs/rag_model_choice.md).

Prefixes follow each model card: instructions on queries only, none on documents.
Vectors are cached under data/. Per-question results go to data/retrieval_<model>.jsonl.
Stdout shows only counts and metrics.

Usage:
  python scripts/eval_retrieval.py --self-test
  python scripts/eval_retrieval.py --model bge-m3 --timing 20
  python scripts/eval_retrieval.py --model bge-m3
  python scripts/eval_retrieval.py --model ytu-ce-cosmos/turkish-e5-large --set c   (held-out, once)
'''
import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import time

import numpy as np

DOCS_PATH='data/rag_docs.jsonl'
# question sets: path, expected total, expected answerable, output suffix.
# 'dev' picked the model (Set B questions); 'c' is the held-out set, measured once (docs/set_c_plan.md).
QUESTION_SETS={
    'dev':{'path':'data/rag_questions.jsonl','total':66,'answerable':59,'suffix':''},
    'c':{'path':'data/rag_questions_c.jsonl','total':53,'answerable':48,'suffix':'_set_c'},
    # 'd': hand-written by Feyza for the BM25 decision (docs/bm25_hybrid_rule.md, Amendment 1); each method once
    'd':{'path':'data/rag_questions_d.jsonl','total':20,'answerable':20,'suffix':'_set_d'},
}
ONCE_SETS={'c','d'}
EXPECTED_QUESTIONS=QUESTION_SETS['dev']['total']
BATCH_SIZE=16
TOP_K=10
OLLAMA_TIMEOUT=300

QWEN_TASK='Given a web search query, retrieve relevant passages that answer the query'
E5_TASK='Given a Turkish search query, retrieve relevant passages written in Turkish that best answer the query'

MODELS={
    'bge-m3':{'backend':'ollama','tokenizer':'BAAI/bge-m3','max_tokens':8192,
              'query':'{q}'},
    'qwen3-embedding:0.6b':{'backend':'ollama','tokenizer':'Qwen/Qwen3-Embedding-0.6B','max_tokens':8192,
                            'query':'Instruct: '+QWEN_TASK+'\nQuery:{q}'},
    'ytu-ce-cosmos/turkish-e5-large':{'backend':'st','tokenizer':'ytu-ce-cosmos/turkish-e5-large','max_tokens':512,
                                      'query':'Instruct: '+E5_TASK+'\nQuery: {q}'},
}


def slug(model):
    return re.sub(r'[/:]','_',model)


def load_jsonl(path):
    with open(path,encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def embed_ollama(name,cfg,texts,on_batch):
    import ollama
    client=ollama.Client(timeout=OLLAMA_TIMEOUT)
    out=[]
    for i in range(0,len(texts),BATCH_SIZE):
        # truncate=False: an over-long text fails instead of being cut silently
        resp=client.embed(model=name,input=texts[i:i+BATCH_SIZE],truncate=False,options={'num_ctx':cfg['max_tokens']})
        out.extend(resp.embeddings)
        on_batch(len(out),len(texts))
    return np.array(out,dtype=np.float32)


def embed_st(name,cfg,texts,on_batch):
    import torch
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer(name,device='mps' if torch.backends.mps.is_available() else 'cpu')
    model.max_seq_length=cfg['max_tokens']
    out=[]
    for i in range(0,len(texts),BATCH_SIZE):
        out.append(model.encode(texts[i:i+BATCH_SIZE],batch_size=BATCH_SIZE,convert_to_numpy=True,show_progress_bar=False))
        on_batch(min(i+BATCH_SIZE,len(texts)),len(texts))
    return np.vstack(out).astype(np.float32)


def embed(name,texts,on_batch=lambda done,total:None):
    cfg=MODELS[name]
    fn=embed_ollama if cfg['backend']=='ollama' else embed_st
    return unit(fn(name,cfg,texts,on_batch))


def unit(matrix):
    norms=np.linalg.norm(matrix,axis=1,keepdims=True)
    if (norms==0).any():
        raise ValueError('zero vector from the model')
    return matrix/norms


def doc_vectors(name,docs):
    '''Embed all docs once; the cache is reused only for identical texts.'''
    path=f'data/emb_{slug(name)}.npz'
    key=hashlib.sha1('\n'.join(d['news_id']+d['text'] for d in docs).encode('utf-8')).hexdigest()
    if os.path.exists(path):
        cached=np.load(path)
        if str(cached['key'])==key:
            print(f'doc vectors: cache hit ({cached["vectors"].shape[0]})')
            return cached['vectors']
    def progress(done,total):
        if done%160==0 or done==total:
            print(f'  embedded {done}/{total}',flush=True)
    vectors=embed(name,[d['text'] for d in docs],progress)
    np.savez(path,vectors=vectors,key=key)
    return vectors


def count_truncated(name,docs):
    from transformers import AutoTokenizer
    cfg=MODELS[name]
    tok=AutoTokenizer.from_pretrained(cfg['tokenizer'])
    lengths=[len(ids) for ids in tok([d['text'] for d in docs],add_special_tokens=True)['input_ids']]
    return sum(1 for n in lengths if n>cfg['max_tokens'])


def rank_docs(vectors,query_vector):
    scores=vectors@query_vector
    order=np.argsort(-scores,kind='stable')
    return order,scores


# --- lexical side (rules in docs/bm25_hybrid_rule.md; parameters fixed there) ---
BM25_K1=1.5
BM25_B=0.75
STEM_LEN=5
RRF_K=60
APOSTROPHE_RE=re.compile(r"['’`][^\s]*")
TOKEN_RE=re.compile(r'[0-9a-z]+')
# after Turkish lowercasing, fold to ASCII so 'irak' / 'Irak' and 'sirket' / 'şirket' match
ASCII_FOLD=str.maketrans('çğıöşüâîû','cgiosuaiu')


def tr_lower(text):
    return text.replace('I','ı').replace('İ','i').lower()


def tokenize(text):
    '''Turkish lowercase, ASCII fold, drop the suffix after an apostrophe, 5-char prefixes of tokens >= 2 chars.'''
    text=APOSTROPHE_RE.sub(' ',tr_lower(text).translate(ASCII_FOLD))
    return [t[:STEM_LEN] for t in TOKEN_RE.findall(text) if len(t)>=2]


class BM25:
    '''Okapi BM25 over pre-tokenized documents (inverted index, pure Python + numpy).'''

    def __init__(self,doc_tokens,k1=BM25_K1,b=BM25_B):
        self.k1,self.b,self.n=k1,b,len(doc_tokens)
        self.lengths=np.array([len(t) for t in doc_tokens],dtype=np.float64)
        self.avgdl=self.lengths.mean() if self.n else 0.0
        self.postings={}
        for i,tokens in enumerate(doc_tokens):
            counts={}
            for t in tokens:
                counts[t]=counts.get(t,0)+1
            for t,c in counts.items():
                self.postings.setdefault(t,[]).append((i,c))
        self.idf={t:float(np.log(1+(self.n-len(p)+0.5)/(len(p)+0.5))) for t,p in self.postings.items()}

    def scores(self,query_tokens):
        out=np.zeros(self.n,dtype=np.float64)
        for t in set(query_tokens):
            for i,tf in self.postings.get(t,()):
                norm=tf+self.k1*(1-self.b+self.b*self.lengths[i]/self.avgdl)
                out[i]+=self.idf[t]*tf*(self.k1+1)/norm
        return out


def rrf_order(embed_order,lex_order,k=RRF_K):
    '''Reciprocal rank fusion of two full rankings; ties keep the embedding order.'''
    n=len(embed_order)
    rank_e=np.empty(n,dtype=np.int64)
    rank_e[embed_order]=np.arange(1,n+1)
    rank_l=np.empty(n,dtype=np.int64)
    rank_l[lex_order]=np.arange(1,n+1)
    fused=1.0/(k+rank_e)+1.0/(k+rank_l)
    return np.lexsort((rank_e,-fused))


def summarize(rows):
    '''rows have answerable, rank, same_company_top1, top1_sim. rank is None beyond TOP_K.'''
    answerable=[r for r in rows if r['answerable']]
    negatives=[r['top1_sim'] for r in rows if not r['answerable']]
    hit1=sum(1 for r in answerable if r['rank']==1)
    hit5=sum(1 for r in answerable if r['rank'] is not None and r['rank']<=5)
    out={
        'answerable':len(answerable),'hit1':hit1,'hit5':hit5,
        'recall1':hit1/len(answerable),'recall5':hit5/len(answerable),
        'wrong_same_company':sum(1 for r in answerable if r['rank']!=1 and r['same_company_top1']),
        'negatives':len(negatives),
    }
    if negatives:
        out.update(neg_min=min(negatives),neg_median=statistics.median(negatives),neg_max=max(negatives))
    return out


def by_kind(rows):
    '''hit@1 and hit@5 per question kind (Set D: named / paraphrased), answerable only.'''
    out={}
    for r in rows:
        if not r['answerable'] or not r.get('kind'):
            continue
        k=out.setdefault(r['kind'],[0,0,0])
        k[0]+=1
        k[1]+=r['rank']==1
        k[2]+=r['rank'] is not None and r['rank']<=5
    return out


def _self_test():
    assert slug('ytu-ce-cosmos/turkish-e5-large')=='ytu-ce-cosmos_turkish-e5-large'
    assert slug('qwen3-embedding:0.6b')=='qwen3-embedding_0.6b'
    assert MODELS['bge-m3']['query'].format(q='x')=='x'
    assert MODELS['qwen3-embedding:0.6b']['query'].format(q='x').endswith('\nQuery:x')
    assert MODELS['ytu-ce-cosmos/turkish-e5-large']['query'].format(q='x').endswith('\nQuery: x')
    assert MODELS['bge-m3']['query'].format(q='{a}')=='{a}'
    vectors=unit(np.array([[1,0],[0,1],[1,1]],dtype=np.float32))
    order,scores=rank_docs(vectors,unit(np.array([[1,0.1]],dtype=np.float32))[0])
    assert list(order)==[0,2,1] and scores[0]>scores[2]>scores[1]
    rows=[
        {'answerable':True,'rank':1,'same_company_top1':True,'top1_sim':0.9},
        {'answerable':True,'rank':3,'same_company_top1':True,'top1_sim':0.8},
        {'answerable':True,'rank':None,'same_company_top1':False,'top1_sim':0.7},
        {'answerable':False,'rank':None,'same_company_top1':False,'top1_sim':0.4},
        {'answerable':False,'rank':None,'same_company_top1':False,'top1_sim':0.6},
    ]
    out=summarize(rows)
    assert (out['hit1'],out['hit5'],out['wrong_same_company'])==(1,2,1)
    assert out['neg_min']==0.4 and out['neg_max']==0.6
    # dev output path unchanged (old results stay valid); held-out set writes its own file
    assert QUESTION_SETS['dev']['suffix']=='' and QUESTION_SETS['c']['suffix']=='_set_c'
    assert (QUESTION_SETS['c']['total'],QUESTION_SETS['c']['answerable'])==(53,48)
    # tokenizer: Turkish case, apostrophe suffix, 5-char prefix, short tokens dropped
    assert tokenize("Irak'taki projeler")==['irak','proje']
    assert tokenize("irak'ta")==tokenize("Irak'ta")==['irak']
    assert tokenize('İSTANBUL ve ışık')==['istan','ve','isik']
    assert tokenize('sirket')==tokenize('Şirket')==['sirke']
    assert tokenize("ASELS | 2026-10-01 | Yeni İş İlişkisi")==['asels','2026','10','01','yeni','is','ilisk']
    assert tokenize('a 1 x')==[]
    # BM25: a doc with the rare query word wins; a word in every doc adds almost nothing
    bm=BM25([tokenize('irak enerji santrali'),tokenize('umman enerji santrali'),tokenize('enerji santrali bakım')])
    s=bm.scores(tokenize("Irak'ta enerji"))
    assert int(np.argmax(s))==0 and s[1]>0 and s[0]>s[1]
    assert bm.scores(tokenize('yok'))[0]==0
    # RRF, k=60, worked by hand: doc1 is 2nd in both lists and wins over doc0 (1st and 5th)
    # scores: d1 2/62=.03226, d3 1/64+1/61=.03202, d0 1/61+1/65=.03178, d2 2/63=.03175, d4 1/65+1/64=.03101
    fused=rrf_order(np.array([0,1,2,3,4]),np.array([3,1,2,4,0]))
    assert list(fused)==[1,3,0,2,4]
    # identical rankings stay identical
    assert list(rrf_order(np.array([2,0,1]),np.array([2,0,1])))==[2,0,1]
    # Set D: no negatives must not crash; per-kind counts
    s=summarize([{'answerable':True,'rank':1,'same_company_top1':True,'top1_sim':0.9}])
    assert s['negatives']==0 and 'neg_min' not in s
    k=by_kind([{'answerable':True,'rank':1,'kind':'named'},{'answerable':True,'rank':7,'kind':'named'},
               {'answerable':True,'rank':3,'kind':'paraphrased'},{'answerable':False,'rank':None,'kind':'named'}])
    assert k=={'named':[2,1,1],'paraphrased':[1,0,1]}
    assert QUESTION_SETS['d']['total']==20 and ONCE_SETS=={'c','d'}
    print('self-test ok: 25 checks')


def timing(name,docs,count):
    '''Speed only: no questions, no scores, no cache.'''
    texts=[d['text'] for d in docs[:count]]
    start=time.time()
    embed(name,texts)
    elapsed=time.time()-start
    per_text=elapsed/len(texts)
    print(f'{name}: {len(texts)} docs in {elapsed:.1f}s, {per_text:.2f}s/doc, projected {per_text*(len(docs)+EXPECTED_QUESTIONS)/60:.1f} min')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=sorted(MODELS))
    parser.add_argument('--timing',type=int,metavar='N')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--set',choices=sorted(QUESTION_SETS),default='dev')
    parser.add_argument('--method',choices=['embed','bm25','hybrid'],default='embed',
                        help='embed = current system; bm25 / hybrid per docs/bm25_hybrid_rule.md')
    args=parser.parse_args()
    if args.self_test:
        _self_test()
        return
    if not args.model:
        parser.error('--model is required')

    docs=load_jsonl(DOCS_PATH)
    if args.timing:
        timing(args.model,docs,args.timing)
        return

    qset=QUESTION_SETS[args.set]
    questions=load_jsonl(qset['path'])
    answerable=sum(1 for q in questions if q['answerable'])
    if len(questions)!=qset['total'] or answerable!=qset['answerable']:
        raise SystemExit(f'question set changed: {len(questions)} total, {answerable} answerable')
    by_id={d['news_id']:d for d in docs}
    missing=[str(q['news_id']) for q in questions if q['answerable'] and str(q['news_id']) not in by_id]
    if missing:
        raise SystemExit(f'gold ids missing from docs: {missing}')

    if args.set=='c' and args.method!='embed':
        raise SystemExit('Set C questions were measured once with embed; they are not reused (docs/bm25_hybrid_rule.md)')
    method_tag='' if args.method=='embed' else f'_{args.method}'
    out_path=f'data/retrieval_{slug(args.model)}{method_tag}{qset["suffix"]}.jsonl'
    if args.set in ONCE_SETS and os.path.exists(out_path):
        raise SystemExit(f'{out_path} exists: the held-out set is measured once')

    commit=subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip()
    start=time.time()
    truncated=count_truncated(args.model,docs)
    vectors=doc_vectors(args.model,docs)
    query_vectors=embed(args.model,[MODELS[args.model]['query'].format(q=q['question']) for q in questions])
    bm25=BM25([tokenize(d['text']) for d in docs]) if args.method!='embed' else None

    rows=[]
    for q,query_vector in zip(questions,query_vectors):
        order,scores=rank_docs(vectors,query_vector)
        if bm25 is not None:
            lex_order=np.argsort(-bm25.scores(tokenize(q['question'])),kind='stable')
            order=lex_order if args.method=='bm25' else rrf_order(order,lex_order)
        top=[docs[i]['news_id'] for i in order[:TOP_K]]
        gold=str(q['news_id'])
        rank=top.index(gold)+1 if q['answerable'] and gold in top else None
        same=q['answerable'] and docs[order[0]]['symbol']==by_id[gold]['symbol']
        # top1_sim stays the embedding cosine of whichever doc is ranked first
        rows.append({'news_id':gold,'answerable':q['answerable'],'rank':rank,'same_company_top1':bool(same),
                     'top1_sim':float(scores[order[0]]),'top_ids':top,'model':args.model,
                     'method':args.method,'kind':q.get('kind'),'git_commit':commit})
    with open(out_path,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r)+'\n')

    s=summarize(rows)
    print(f'set={args.set} method={args.method} model={args.model} commit={commit} docs={len(docs)} questions={len(questions)} seconds={time.time()-start:.0f}')
    print(f'recall@1 {s["hit1"]}/{s["answerable"]} = {s["recall1"]:.3f}')
    print(f'recall@5 {s["hit5"]}/{s["answerable"]} = {s["recall5"]:.3f}')
    print(f'wrong_same_company {s["wrong_same_company"]}')
    print(f'truncated_docs {truncated}')
    if s['negatives']:
        print(f'negative top-1 similarity min={s["neg_min"]:.3f} median={s["neg_median"]:.3f} max={s["neg_max"]:.3f}')
    else:
        print('negatives 0')
    for kind,(n,h1,h5) in sorted(by_kind(rows).items()):
        print(f'kind={kind} n={n} recall@1 {h1}/{n} recall@5 {h5}/{n}')


if __name__=='__main__':
    main()
