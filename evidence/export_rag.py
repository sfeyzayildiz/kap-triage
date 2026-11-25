"""Write evidence/rag_set_d.jsonl: the Set D search result per question, from a rerun that must equal the saved run.

Runs only in the private working repository, where the documents, the 20 Set D questions (written
by Feyza) and the saved runs of 8 Nov are. Rules: docs/rerank_rule.md, docs/bm25_hybrid_rule.md.

It runs the search again in memory, the same way eval_retrieval.py did (turkish-e5-large, top 20,
bge-reranker-v2-m3, top 10 kept), and writes nothing if one check fails:
  1. the document vectors come from the saved cache, and the cache key equals today's documents
     (no new embedding of the archive, nothing written under data/);
  2. for every question, the top 10 of the rerun equals the saved top 10, both for embedding only
     and for embedding + rerank (40 of 40 lists identical, not only the counts);
  3. the counts from the saved runs (rank 1 and top 5) equal the counts from the rerun.

Each line holds: a hash of the gold disclosure id, its rank with embedding only and with the
rerank (null = not in the top 10), and whether the first result is the right company. No question,
answer, text or company.

    cd <private repo> && HF_HUB_OFFLINE=1 PYTHONPATH=scripts .venv/bin/python <this repo>/evidence/export_rag.py
"""

import hashlib
import json
from pathlib import Path

import numpy as np

import eval_retrieval as er

MODEL = 'ytu-ce-cosmos/turkish-e5-large'
SAVED = {
    'embed': f'data/retrieval_{er.slug(MODEL)}_set_d.jsonl',
    'rerank': f'data/retrieval_{er.slug(MODEL)}_rerank_set_d.jsonl',
}
CACHE = f'data/emb_{er.slug(MODEL)}.npz'
OUT = Path(__file__).resolve().parent / 'rag_set_d.jsonl'
KEYS = {'id_hash', 'rank_embed', 'rank_rerank', 'same_company_top1'}


def cached_vectors(docs):
    """The saved document vectors, only if they were made from exactly these documents."""
    key = hashlib.sha1('\n'.join(d['news_id'] + d['text'] for d in docs).encode('utf-8')).hexdigest()
    cached = np.load(CACHE)
    if str(cached['key']) != key:
        raise SystemExit('STOP: the documents changed since the cached vectors; not rerun')
    return cached['vectors']


def counts(ranks):
    return sum(1 for r in ranks if r == 1), sum(1 for r in ranks if r is not None and r <= 5)


def main():
    docs = er.load_jsonl(er.DOCS_PATH)
    questions = er.load_jsonl(er.QUESTION_SETS['d']['path'])
    if len(questions) != 20 or not all(q['answerable'] for q in questions):
        raise SystemExit(f'STOP: {len(questions)} Set D questions, expected 20 answerable')
    saved = {name: er.load_jsonl(path) for name, path in SAVED.items()}
    for name, rows in saved.items():
        if [r['news_id'] for r in rows] != [str(q['news_id']) for q in questions]:
            raise SystemExit(f'STOP: saved {name} run does not follow the question file')
        if any('top_ids' not in r or 'rank' not in r for r in rows):
            raise SystemExit(f'STOP: saved {name} run has no top-10 lists to compare with')
    # rerank_k and docs were added to the rows on 11 Nov (depth and chunking ablations); the 8 Nov run
    # has neither, and then the depth was fixed at 20 and documents were one per disclosure (rerank_rule.md)
    rr = saved['rerank']
    if any(r.get('method') != 'rerank' for r in rr) or any(
        r.get('rerank_k', er.RERANK_K) != er.RERANK_K or r.get('docs', 'docs') != 'docs' for r in rr
    ):
        raise SystemExit('STOP: saved rerank run is not the adopted setting (top 20, one doc per disclosure)')
    print(
        f'saved rerank run: commit {sorted({r.get("git_commit") for r in rr})}, '
        f'rows without rerank_k (8 Nov format): {sum("rerank_k" not in r for r in rr)}'
    )

    vectors = cached_vectors(docs)
    by_id = {d['news_id']: d for d in docs}
    query_vectors = er.embed(MODEL, [er.MODELS[MODEL]['query'].format(q=q['question']) for q in questions])
    ce = er.cross_encoder()
    same = {'embed': 0, 'rerank': 0}
    out = []
    for q, qv, se, sr in zip(questions, query_vectors, saved['embed'], saved['rerank']):
        order, _ = er.rank_docs(vectors, qv)
        top_embed = [docs[i]['news_id'] for i in order[: er.TOP_K]]
        ce_scores = ce.predict(
            [(q['question'], docs[i]['text']) for i in order[: er.RERANK_K]], show_progress_bar=False
        )
        reranked = er.rerank_order(order, ce_scores, k=er.RERANK_K)
        top_rerank = [docs[i]['news_id'] for i in reranked[: er.TOP_K]]
        same['embed'] += top_embed == se['top_ids']
        same['rerank'] += top_rerank == sr['top_ids']
        gold = str(q['news_id'])
        out.append(
            {
                'id_hash': hashlib.sha256(gold.encode()).hexdigest()[:16],
                'rank_embed': top_embed.index(gold) + 1 if gold in top_embed else None,
                'rank_rerank': top_rerank.index(gold) + 1 if gold in top_rerank else None,
                'same_company_top1': docs[reranked[0]]['symbol'] == by_id[gold]['symbol'],
            }
        )

    mine = {'embed': counts([o['rank_embed'] for o in out]), 'rerank': counts([o['rank_rerank'] for o in out])}
    theirs = {name: counts([r['rank'] for r in rows]) for name, rows in saved.items()}
    print(
        f'questions={len(out)} docs={len(docs)} identical_top10: embed {same["embed"]}/20, rerank {same["rerank"]}/20'
    )
    for name in ('embed', 'rerank'):
        print(f'{name}: rerun @1 {mine[name][0]} @5 {mine[name][1]} | saved @1 {theirs[name][0]} @5 {theirs[name][1]}')
    ok = same == {'embed': 20, 'rerank': 20} and mine == theirs
    print('MATCH' if ok else 'MISMATCH')
    if not ok:
        raise SystemExit('STOP: not written')
    for o in out:
        if set(o) != KEYS:
            raise SystemExit('STOP: unexpected field')
    OUT.write_text(''.join(json.dumps(o, sort_keys=True) + '\n' for o in out), encoding='utf-8')
    print(f'written {len(out)} lines -> {OUT.name}')


if __name__ == '__main__':
    main()
