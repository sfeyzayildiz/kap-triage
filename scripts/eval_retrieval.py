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
}
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


def summarize(rows):
    '''rows have answerable, rank, same_company_top1, top1_sim. rank is None beyond TOP_K.'''
    answerable=[r for r in rows if r['answerable']]
    negatives=[r['top1_sim'] for r in rows if not r['answerable']]
    hit1=sum(1 for r in answerable if r['rank']==1)
    hit5=sum(1 for r in answerable if r['rank'] is not None and r['rank']<=5)
    return {
        'answerable':len(answerable),'hit1':hit1,'hit5':hit5,
        'recall1':hit1/len(answerable),'recall5':hit5/len(answerable),
        'wrong_same_company':sum(1 for r in answerable if r['rank']!=1 and r['same_company_top1']),
        'neg_min':min(negatives),'neg_median':statistics.median(negatives),'neg_max':max(negatives),
    }


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
    print('self-test ok: 12 checks')


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

    commit=subprocess.run(['git','rev-parse','--short','HEAD'],capture_output=True,text=True).stdout.strip()
    start=time.time()
    truncated=count_truncated(args.model,docs)
    vectors=doc_vectors(args.model,docs)
    query_vectors=embed(args.model,[MODELS[args.model]['query'].format(q=q['question']) for q in questions])

    rows=[]
    for q,query_vector in zip(questions,query_vectors):
        order,scores=rank_docs(vectors,query_vector)
        top=[docs[i]['news_id'] for i in order[:TOP_K]]
        gold=str(q['news_id'])
        rank=top.index(gold)+1 if q['answerable'] and gold in top else None
        same=q['answerable'] and docs[order[0]]['symbol']==by_id[gold]['symbol']
        rows.append({'news_id':gold,'answerable':q['answerable'],'rank':rank,'same_company_top1':bool(same),
                     'top1_sim':float(scores[order[0]]),'top_ids':top,'model':args.model,'git_commit':commit})

    out_path=f'data/retrieval_{slug(args.model)}{qset["suffix"]}.jsonl'
    if args.set=='c' and os.path.exists(out_path):
        raise SystemExit(f'{out_path} exists: the held-out set is measured once')
    with open(out_path,'w',encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r)+'\n')

    s=summarize(rows)
    print(f'set={args.set} model={args.model} commit={commit} docs={len(docs)} questions={len(questions)} seconds={time.time()-start:.0f}')
    print(f'recall@1 {s["hit1"]}/{s["answerable"]} = {s["recall1"]:.3f}')
    print(f'recall@5 {s["hit5"]}/{s["answerable"]} = {s["recall5"]:.3f}')
    print(f'wrong_same_company {s["wrong_same_company"]}')
    print(f'truncated_docs {truncated}')
    print(f'negative top-1 similarity min={s["neg_min"]:.3f} median={s["neg_median"]:.3f} max={s["neg_max"]:.3f}')


if __name__=='__main__':
    main()
