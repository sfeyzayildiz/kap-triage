# Clustering of disclosures: method and evaluation rule (written before measurement)

Date: 2026-11-09. Committed before any cluster is compared with sector labels. The sector labels (`v4/meta/symbols.gz`, approved by Matriks) are pulled around 12 Nov; nothing here has seen them.

## Why
The instructor's "one step further": interpret the daily flow by theme and route it to the right desk (defense, energy, banking ...).

## Design decision (fixed)
- **Routing to sector desks uses Matriks sector labels directly** (a lookup in code), not clusters. A label that exists should not be guessed.
- **Clusters are for themes**: "what kinds of deals came in this week", across companies and sectors.
- The evaluation asks one question: do the embeddings group companies of the same sector together, beyond chance? This tells whether the themes are meaningful, not whether routing works.

## Method (fixed now, not tuned afterwards)
- **Input:** every disclosure's normalized text **without the header** (`normalize(aciklama)`, no symbol, date or headline), embedded with `ytu-ce-cosmos/turkish-e5-large` (no prefix, same as documents in the index). The header is left out because the symbol in it would pull one company's disclosures together for a reason that has nothing to do with the theme.
- **Algorithm:** spherical k-means (unit vectors, assignment by cosine, centroids re-normalized), k-means++ initialisation, 10 restarts, 100 iterations, seed 20261109; the restart with the highest total cosine to the centroids is kept.
- **k:** the number of distinct sectors among the companies that have disclosures (read from the sector labels). Before the labels arrive, a provisional build uses k=12 for development only; it is not evaluated.
- **Theme names:** for each cluster, the 5 words (Turkish lowercase, length ≥ 4) with the highest ratio of in-cluster to overall document frequency, among words in at least 5 of the cluster's documents. Written to `data/`, never printed (they come from disclosure text).

## Amendment 1 (2026-11-09, after Feyza looked at the provisional k=12 themes; sector labels not yet pulled)
- Her reading: mixed. 3 clusters look like real themes, 3 broad clusters are generic boilerplate, and some narrow clusters are named after company names (template effect).
- Change, naming only: a theme word must also appear in documents of **at least 3 different companies** in that cluster. Company names drop out of theme names. The clustering itself (input, algorithm, k, seed) is unchanged.
- Not changed: boilerplate clusters stay; they are reported as a limit (the embedding partly groups by writing pattern, not by topic).

## Evaluation (one run, after the sector pull)
- **Primary (company level):** each company is assigned its most frequent cluster (ties: lowest cluster id). Adjusted Rand Index between that company cluster and the company's sector, over companies with a sector label.
- **Chance baseline:** the same ARI with the sector labels shuffled across companies, 1000 times, seed 20261109.
- **Decision:** "clusters reflect sector" if the primary ARI is above the 99th percentile of the shuffled ARIs. Otherwise the themes are reported as not aligned with sector, and the panel shows sector (from labels) and theme (from clusters) side by side without claiming one explains the other.
- **Also reported (not part of the decision):** document-level ARI, NMI and purity vs. sector; document-level ARI vs. company (how much clusters are just companies); cluster sizes; number of companies per cluster.

## Honest limit
About 150 companies and maybe 10-20 sectors: the company-level ARI will be noisy. Sector is a coarse label (a defense company's software contract is "defense"), so a low ARI does not mean the themes are useless.
