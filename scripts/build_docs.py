'''Build one RAG document per disclosure: a short header plus normalized text.

Output goes to data/rag_docs.jsonl (data/ is gitignored, never shared).
Stdout shows only counts.
'''
import json
import statistics

import duckdb

from normalize import normalize

DB_PATH='data/kap.duckdb'
OUT_PATH='data/rag_docs.jsonl'
QUESTIONS_PATH='data/rag_questions.jsonl'


def header(symbol,published_at,is_update,is_correction,headline):
    kind='Düzeltme' if is_correction else 'Güncelleme' if is_update else 'Yeni bildirim'
    return f'{symbol} | {str(published_at)[:10]} | {kind} | {normalize(headline)}'


def load_rows(db_path):
    con=duckdb.connect(db_path,read_only=True)
    try:
        return con.execute('''
            SELECT news_id,kap_url,symbol,published_at,is_update,is_correction,headline,aciklama
            FROM disclosures ORDER BY published_at
        ''').fetchall()
    finally:
        con.close()


def main():
    docs=[]
    for nid,url,sym,pub,upd,corr,head,text in load_rows(DB_PATH):
        docs.append({
            'news_id':str(nid),'kap_url':url,'symbol':sym,'published_at':str(pub),
            'is_update':bool(upd),'is_correction':bool(corr),
            'text':header(sym,pub,upd,corr,head)+'\n'+normalize(text),
        })
    with open(OUT_PATH,'w',encoding='utf-8') as f:
        for d in docs:
            f.write(json.dumps(d,ensure_ascii=False)+'\n')

    words=[len(d['text'].split()) for d in docs]
    print(f'{len(docs)} docs -> {OUT_PATH}')
    print(f'words: median={int(statistics.median(words))} max={max(words)}')

    doc_ids={d['news_id'] for d in docs}
    with open(QUESTIONS_PATH,encoding='utf-8') as f:
        qs=[json.loads(line) for line in f if line.strip()]
    answerable=[q for q in qs if q.get('answerable')]
    missing=[str(q['news_id']) for q in answerable if str(q['news_id']) not in doc_ids]
    print(f'questions: {len(qs)} ({len(answerable)} answerable), gold ids missing from docs: {missing}')


if __name__=='__main__':
    main()