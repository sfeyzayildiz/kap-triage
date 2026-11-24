"""kap_triage/assistant/clusters.py: the checks of the v1 self-test in clusters.py, on made-up data (no network, no real data)."""

import numpy as np
from kap_triage.assistant.clusters import (
    ari,
    company_clusters,
    nmi,
    purity,
    shuffled_aris,
    spherical_kmeans,
    theme_words,
)


def test_clusters():
    rng = np.random.default_rng(0)
    centers = np.eye(3)
    X = np.vstack([c + 0.05 * rng.standard_normal((20, 3)) for c in centers])
    X = X / np.linalg.norm(X, axis=1, keepdims=True)
    labels, _, _ = spherical_kmeans(X, 3, seed=1, n_init=3)
    truth = [0] * 20 + [1] * 20 + [2] * 20
    assert ari(labels, truth) == 1.0  # separable groups are found
    assert abs(ari([0, 0, 1, 1], [0, 0, 1, 1]) - 1) < 1e-12 and abs(ari([0, 0, 1, 1], ['a', 'a', 'b', 'b']) - 1) < 1e-12
    assert ari([0, 1, 0, 1], [0, 0, 1, 1]) < 0  # anti-aligned is below chance
    assert abs(nmi([0, 0, 1, 1], [1, 1, 0, 0]) - 1) < 1e-12 and nmi([0, 0, 0, 0], [0, 1, 0, 1]) < 1e-12
    assert purity([0, 0, 1, 1], ['a', 'b', 'b', 'b']) == 0.75
    assert company_clusters(['A', 'A', 'A', 'B'], [2, 1, 1, 0]) == {'A': 1, 'B': 0}
    assert company_clusters(['A', 'A'], [3, 1]) == {'A': 1}  # tie -> lowest id
    null = shuffled_aris(
        {s: i % 2 for i, s in enumerate('abcdefgh')}, {s: i % 2 for i, s in enumerate('abcdefgh')}, n=50
    )
    assert len(null) == 50 and max(null) <= 1.0
    texts = ['savunma sistemleri ihracat'] * 6 + ['enerji santrali kurulum'] * 6
    th = theme_words(texts, [0] * 6 + [1] * 6, 2, top=2)
    assert set(th[0]) <= {'savunma', 'sistemleri', 'ihracat'} and set(th[1]) <= {'enerji', 'santrali', 'kurulum'}
    assert len(th[0]) == 2 and theme_words(texts, [0] * 12, 2)[1] == []  # an empty cluster gets no words, no crash
    # Amendment 1: a word used by only one company (e.g. its name) is not a theme word
    t2 = ['acmeholding savunma'] * 3 + ['savunma radar'] * 3 + ['enerji santrali'] * 6
    syms = ['ACME'] * 3 + ['B', 'C', 'D'] + ['E', 'F', 'G', 'H', 'I', 'J']
    th2 = theme_words(t2, [0] * 6 + [1] * 6, 2, top=5, min_docs=2, symbols=syms)
    assert 'acmeholding' not in th2[0] and 'savunma' in th2[0]
    assert (
        'acmeholding' in theme_words(t2, [0] * 6 + [1] * 6, 2, top=5, min_docs=2)[0]
    )  # without the company rule it would be kept
