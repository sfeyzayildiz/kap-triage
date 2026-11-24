"""Search over all disclosures: one document per disclosure, the chosen embedding model
(docs/rag_model_choice.md), a cross-encoder rerank for questions (docs/rerank_rule.md).

A document is a short header (symbol | date | kind | headline) plus normalized text. The index
(data/rag_index.npz) is updated incrementally: only new or changed texts are embedded.
Stdout shows only counts, ids and similarity scores.

Usage:
  python main.py index --build
  python main.py index --similar NEWS_ID
"""

import re
import duckdb
import argparse
import hashlib
import os
import time
from functools import lru_cache
import numpy as np

from kap_triage.settings import settings


# --- Text normalization (embedding input only; extraction reads the raw text) ---

TR = 'çğıöşüÇĞİÖŞÜ'
SPLIT_HIT = re.compile(rf'(?<=\w) [{TR}] (?=\w)')
# rows with >=6 hits had every Turkish letter split off; 1-hit rows were 'İ STANBUL'
HEAVY_MIN_HITS = 5
SPLIT_SPACE = re.compile(rf'(?<=[^\W\d_]) (?=[{TR}])|(?<=[{TR}]) (?=[^\W\d_])')
UPPER_SPLIT = re.compile(r'\b([İŞÇĞÜÖ]) (?=[A-ZÇĞİÖŞÜ]{2,})')
LIRA_AFTER = re.compile(r'(\d\s*)\?')
LIRA_BEFORE = re.compile(r'\?(\s*\d)')
MULTI_SPACE = re.compile(r'[ \t]{2,}')


def is_heavy(text):
    return len(SPLIT_HIT.findall(text)) >= HEAVY_MIN_HITS


def fix_split(text):
    """Join Turkish letters that were split off with spaces (heavy rows only)."""
    return SPLIT_SPACE.sub('', text)


def normalize(text):
    if not text:
        return ''
    text = text.replace('\xa0', ' ')
    text = UPPER_SPLIT.sub(r'\1', text)
    if is_heavy(text):
        text = fix_split(text)
    text = LIRA_AFTER.sub(r'\1₺', text)
    text = LIRA_BEFORE.sub(r'₺\1', text)
    text = MULTI_SPACE.sub(' ', text)
    return text.strip()


# --- Documents ------------------------------------------------------------------

DB_PATH = settings.path('kap.duckdb')


def header(symbol, published_at, is_update, is_correction, headline):
    kind = 'Düzeltme' if is_correction else 'Güncelleme' if is_update else 'Yeni bildirim'
    return f'{symbol} | {str(published_at)[:10]} | {kind} | {normalize(headline)}'


def load_rows(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute("""
            SELECT news_id,kap_url,symbol,published_at,is_update,is_correction,headline,aciklama
            FROM disclosures ORDER BY published_at
        """).fetchall()
    finally:
        con.close()


# --- Index, search and rerank ---------------------------------------------------

MODEL = 'ytu-ce-cosmos/turkish-e5-large'
MAX_TOKENS = 512
# the query instruction of the model card; documents get no prefix
QUERY = 'Instruct: Given a Turkish search query, retrieve relevant passages written in Turkish that best answer the query\nQuery: {q}'
RERANK_MODEL = 'BAAI/bge-reranker-v2-m3'  # docs/rerank_rule.md
INDEX_PATH = settings.path('rag_index.npz')
BATCH_SIZE = 16
META = ('news_id', 'kap_url', 'symbol', 'published_at', 'sha1')


def doc_text(sym, pub, upd, corr, head, text):
    return header(sym, pub, upd, corr, head) + '\n' + normalize(text)


def sha1(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer(MODEL, device='mps' if torch.backends.mps.is_available() else 'cpu')
    m.max_seq_length = MAX_TOKENS
    return m


def unit(matrix):
    """Rows scaled to length 1, so a dot product is the cosine similarity."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError('zero vector from the model')
    return matrix / norms


def embed_docs(texts):
    """Documents get no prefix (model card)."""
    return unit(
        model().encode(texts, batch_size=BATCH_SIZE, convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
    )


def embed_query(question):
    q = QUERY.format(q=question)
    return embed_docs([q])[0]


def load_index(path=INDEX_PATH):
    if not os.path.exists(path):
        return None
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in ('vectors',) + META}


def merge(index, docs, embed):
    """Keep vectors whose (news_id, sha1) is unchanged; embed the rest. Returns (index, n_embedded)."""
    old = {}
    if index is not None:
        old = {(n, s): i for i, (n, s) in enumerate(zip(index['news_id'], index['sha1']))}
    todo = [d for d in docs if (d['news_id'], d['sha1']) not in old]
    new_vecs = dict(zip([(d['news_id'], d['sha1']) for d in todo], embed([d['text'] for d in todo]) if todo else []))
    vectors = [
        index['vectors'][old[(d['news_id'], d['sha1'])]]
        if (d['news_id'], d['sha1']) in old
        else new_vecs[(d['news_id'], d['sha1'])]
        for d in docs
    ]
    out = {'vectors': np.array(vectors, dtype=np.float32)}
    for k in META:
        out[k] = np.array([d[k] for d in docs])
    return out, len(todo)


def update(path=INDEX_PATH):
    docs = []
    for nid, url, sym, pub, upd, corr, head, text in load_rows(DB_PATH):
        t = doc_text(sym, pub, upd, corr, head, text)
        docs.append(
            {
                'news_id': str(nid),
                'kap_url': url or '',
                'symbol': sym or '',
                'published_at': str(pub),
                'sha1': sha1(t),
                'text': t,
            }
        )
    index, n = merge(load_index(path), docs, embed_docs)
    np.savez(path, **index)
    return index, n


def search(index, query_vector, symbol=None, before=None, exclude=None, k=5, on_day=None, period=None):
    """Top k by cosine similarity, optionally only one symbol, only before a timestamp string, only one publish day,
    only inside a (start, end) period of dates, both ends included (docs/relative_periods_rule.md)."""
    mask = np.ones(len(index['news_id']), dtype=bool)
    if symbol:
        mask &= index['symbol'] == symbol
    if on_day:
        mask &= np.char.startswith(index['published_at'].astype(str), str(on_day))
    if period:
        day = index['published_at'].astype('U10')
        mask &= (day >= str(period[0])) & (day <= str(period[1]))
    if before:
        mask &= index['published_at'] < before
    if exclude:
        mask &= index['news_id'] != exclude
    scores = np.where(mask, index['vectors'] @ query_vector, -np.inf)
    order = [i for i in np.argsort(-scores, kind='stable')[:k] if np.isfinite(scores[i])]
    return [
        {
            'news_id': str(index['news_id'][i]),
            'kap_url': str(index['kap_url'][i]),
            'symbol': str(index['symbol'][i]),
            'published_at': str(index['published_at'][i]),
            'score': float(scores[i]),
        }
        for i in order
    ]


RERANK_K = 20  # docs/rerank_rule.md: adopted 2026-11-08 for question search


def doc_texts(news_ids):
    """Document text (same as the index input) for the given ids; one short read-only DB read."""
    wanted = set(news_ids)
    return {
        str(nid): doc_text(sym, pub, upd, corr, head, text)
        for nid, url, sym, pub, upd, corr, head, text in load_rows(DB_PATH)
        if str(nid) in wanted
    }


@lru_cache(maxsize=1)
def reranker():
    import torch
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANK_MODEL, max_length=512, device='mps' if torch.backends.mps.is_available() else 'cpu')


def rerank_hits(question, hits, texts, score):
    """Reorder hits by score(question, text) (stable on ties); hits without text keep their place at the end."""
    with_text = [h for h in hits if h['news_id'] in texts]
    rest = [h for h in hits if h['news_id'] not in texts]
    if not with_text:
        return hits
    s = score([(question, texts[h['news_id']]) for h in with_text])
    order = np.argsort(-np.asarray(s), kind='stable')
    return [{**with_text[i], 'rerank_score': float(s[i])} for i in order] + rest


def search_question(index, question, symbol=None, k=5, score=None, texts=None, on_day=None, period=None):
    """Question search as measured: embed the question, top RERANK_K, cross-encoder rerank, top k."""
    hits = search(index, embed_query(question), symbol=symbol, k=RERANK_K, on_day=on_day, period=period)
    texts = texts if texts is not None else doc_texts([h['news_id'] for h in hits])
    score = score or (lambda pairs: reranker().predict(pairs, show_progress_bar=False))
    return rerank_hits(question, hits, texts, score)[:k]


def similar_earlier(index, news_id, k=3):
    """The same company's earlier disclosures most similar to this one."""
    hits = np.where(index['news_id'] == str(news_id))[0]
    if not len(hits):
        return []
    i = hits[0]
    return search(index, index['vectors'][i], symbol=str(index['symbol'][i]), before=str(index['published_at'][i]), k=k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true', help='create or update data/rag_index.npz')
    ap.add_argument('--similar', help='earlier disclosures of the same company like NEWS_ID')
    args = ap.parse_args()
    if args.build:
        start = time.time()
        index, n = update()
        print(f'docs={len(index["news_id"])} embedded={n} seconds={time.time() - start:.0f} -> {INDEX_PATH}')
    if args.similar:
        index = load_index()
        for h in similar_earlier(index, args.similar):
            print(h['news_id'], h['published_at'][:10], f'{h["score"]:.3f}')
    if not (args.build or args.similar):
        ap.error('give --build, --similar')


if __name__ == '__main__':
    main()
