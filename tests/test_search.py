"""Search (kap_triage/assistant/search.py): text normalization, then the index with a fake embedding: incremental update, filters and rerank order. No model is loaded."""

import numpy as np

from kap_triage.assistant.search import fix_split, is_heavy, normalize
from kap_triage.assistant.search import merge, rerank_hits, search, sha1, similar_earlier, unit


# --- Normalization --------------------------------------------------------------


def test_normalize():
    cases = [
        (fix_split('aras ı nda'), 'arasında'),
        (fix_split('s ö zle ş me imzal'), 'sözleşme imzal'),
        (fix_split('anm ış t ı r. Ara ç lar ı m ı z ı'), 'anmıştır. Araçlarımızı'),
        (fix_split('22 ara ç 12 metre'), '22 araç 12 metre'),
        # known limitation: real word boundaries next to a Turkish letter are lost
        (fix_split('29 adet ş arj'), '29 adetşarj'),
        (normalize('numaralı İ STANBUL\xa0Bölge'), 'numaralı İSTANBUL Bölge'),
        (normalize('üç adet şarj'), 'üç adet şarj'),
        (normalize('1.000.000 ? tutarında'), '1.000.000 ₺ tutarında'),
        (normalize('?500 bin'), '₺500 bin'),
        (normalize('Neden? Çünkü'), 'Neden? Çünkü'),
        (normalize('  a\xa0\xa0 b  '), 'a b'),
        (normalize(None), ''),
        (is_heavy('s ö zle ş me ara ç lar ı m ı z'), True),
        (is_heavy('numaralı İ STANBUL'), False),
    ]
    failed = [(i, got, want) for i, (got, want) in enumerate(cases) if got != want]
    assert not failed, failed  # (case number, got, want)


# --- Index ----------------------------------------------------------------------


def fake_embed(texts):
    return unit(np.array([[len(t), t.count('a') + 1, 1.0] for t in texts], dtype=np.float32))


def test_incremental_update():
    docs = [
        {'news_id': str(i), 'kap_url': f'u{i}', 'symbol': s, 'published_at': p, 'text': t, 'sha1': sha1(t)}
        for i, (s, p, t) in enumerate(
            [
                ('AAA', '2026-01-01 09:00:00', 'aaaa'),
                ('AAA', '2026-02-01 09:00:00', 'aaab'),
                ('BBB', '2026-02-15 09:00:00', 'aaaa'),
                ('AAA', '2026-03-01 09:00:00', 'aaaa x'),
            ]
        )
    ]
    index, n = merge(None, docs, fake_embed)
    assert n == 4 and index['vectors'].shape == (4, 3)
    index2, n = merge(index, docs, fake_embed)  # nothing changed -> nothing embedded
    assert n == 0 and np.allclose(index2['vectors'], index['vectors'])
    changed = docs[:3] + [{**docs[3], 'text': 'b', 'sha1': sha1('b')}]
    assert merge(index, changed, fake_embed)[1] == 1  # only the changed text is embedded
    # similar earlier: same company, only before this one
    sim = similar_earlier(index, '3')
    assert {h['news_id'] for h in sim} == {'0', '1'} and all(h['symbol'] == 'AAA' for h in sim)
    assert sim[0]['score'] >= sim[1]['score']
    assert similar_earlier(index, '0') == [] and similar_earlier(index, '99') == []
    hits = search(index, index['vectors'][0], exclude='0', k=2)
    assert len(hits) == 2 and '0' not in [h['news_id'] for h in hits]


def test_rerank_order():
    # score decides, ties keep the embedding order, hits without text go last
    h = [{'news_id': 'a'}, {'news_id': 'b'}, {'news_id': 'c'}, {'news_id': 'd'}]
    out = rerank_hits('q', h, {'a': 'x', 'b': 'yy', 'c': 'zz'}, lambda pairs: [len(t) for _, t in pairs])
    assert [x['news_id'] for x in out] == ['b', 'c', 'a', 'd'] and out[0]['rerank_score'] == 2.0
    assert rerank_hits('q', h, {}, lambda pairs: []) == h


def test_day_and_period_filters():
    idx = {
        'news_id': np.array(['1', '2', '3']),
        'symbol': np.array(['A', 'A', 'B']),
        'published_at': np.array(['2026-11-09 10:00:00', '2026-11-08 18:00:00', '2026-11-09 19:30:00']),
        'kap_url': np.array(['u1', 'u2', 'u3']),
        'vectors': np.eye(3, dtype=np.float32),
    }
    q = np.array([0.5, 0.9, 0.4], dtype=np.float32)
    assert [h['news_id'] for h in search(idx, q, on_day='2026-11-09')] == ['1', '3']
    assert [h['news_id'] for h in search(idx, q, symbol='A', on_day='2026-11-09')] == ['1']
    assert search(idx, q, on_day='2026-11-07') == []
    # period: both ends included
    assert [h['news_id'] for h in search(idx, q, period=('2026-11-08', '2026-11-08'))] == ['2']
    assert [h['news_id'] for h in search(idx, q, period=('2026-11-08', '2026-11-09'))] == ['2', '1', '3']
    assert search(idx, q, symbol='B', period=('2026-11-01', '2026-11-08')) == []
