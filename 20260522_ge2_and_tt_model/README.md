# Two-Tower Retrieval Model with Gemini Embedding 2

A lightweight two-tower model that learns task-specific projections on top of frozen Gemini Embedding 2 embeddings, improving search quality for retrieval tasks. Benchmarked on **Amazon ESCI** (product search, 4-grade relevance) and **MS MARCO** (passage ranking, binary relevance) with Vector Search 2.0 deployment and a FastAPI search demo UI that supports both datasets via a runtime switcher.

## Architecture

```
Gemini Embedding 2 (768d, frozen)
         │
    ┌────┴────────────┐
    │                 │
Query Tower       Doc Tower       ← JAX/Flax MLPs (768 → 512 → 768)
    │                 │                with residual connections
  q_proj            d_proj         ← L2-normalized 768d vectors
    │                 │
    └──► dot product ◄┘            ← trained with multi-positive contrastive loss
```

Each tower is a shallow MLP with a residual connection:

```
input (768d) ──┬── Dense(512) → ReLU → Dense(768) ──┬── L2 normalize → output (768d)
               │                                     │
               └─────────── residual add ────────────┘
```

The residual connection is critical: without it, the bottleneck (768→512→768) loses information and the model degrades below the baseline. With it, the MLP learns a small correction that specializes the general-purpose embeddings for the target retrieval task.

## Embedding Strategies

Four embedding approaches are compared, all using `gemini-embedding-2`. The repo also includes a title-only BM25 lexical baseline for offline comparison:

| Approach | Query Format | Document Format | Two-Tower |
|----------|-------------|-----------------|-----------|
| Similarity | Raw text (SEMANTIC_SIMILARITY task type) | Raw text | No |
| Retrieval | `task: search result \| query: {text}` | `title: none \| text: {text}` | No |
| TT Similarity | Similarity embedding → learned projection | Similarity embedding → learned projection | Yes |
| TT Retrieval | Retrieval embedding → learned projection | Retrieval embedding → learned projection | Yes |

Both two-tower variants train with a multi-positive contrastive loss, so multiple relevant products for the same query can all be treated as positives within a batch. The key difference is the frozen input space: `TT Similarity` starts from similarity embeddings, while `TT Retrieval` starts from retrieval-style embeddings with search-task prefixes.

## Datasets

The codebase supports multiple datasets through a `DatasetConfig` abstraction. Each dataset defines its own relevance grades, colors, document/query templates, collection names, and domain-specific settings. The `--dataset` flag selects which dataset to use in the pipeline.

### Amazon ESCI

[Amazon ESCI](https://huggingface.co/datasets/smangrul/amazon_esci) — a large-scale product search dataset with graded relevance labels:

| Label | Relevance | Score |
|-------|-----------|-------|
| E (Exact) | Product is an exact match for the query | 3 |
| S (Substitute) | Product is a reasonable substitute | 2 |
| C (Complement) | Product is complementary (not a match) | 1 |
| I (Irrelevant) | Product is irrelevant | 0 |

Only E and S labels are treated as positive pairs for training and evaluation. C complements and I irrelevant items are excluded from the positive set.

| Split | Queries | Products | Pairs |
|-------|---------|----------|-------|
| Train | 17,754 | 351,961 | 279,641 |
| Test | 3,134 | 351,961 | 49,806 |

### MS MARCO (passage ranking)

[BeIR/msmarco](https://huggingface.co/datasets/BeIR/msmarco) — a standard web passage ranking benchmark with binary relevance:

| Label | Relevance | Score |
|-------|-----------|-------|
| R (Relevant) | Passage answers the query | 1 |
| N (Not relevant) | Passage does not answer the query | 0 |

The loader takes a configurable subset of the 8.84M passage corpus (default 500K), prioritizing passages that appear in the qrels so that the subset retains maximum query coverage. Queries are filtered to those with at least one relevant passage in the subset.

| Split | Queries | Passages | Pairs |
|-------|---------|----------|-------|
| Train | 31,342 | 500,000 | 32,959 |
| Test | 5,000 | 500,000 | 5,236 |

## Training

- **Base embeddings**: Gemini Embedding 2, 768 dimensions
- **Variants**: towers trained separately on similarity embeddings and retrieval embeddings
- **Loss**: Bidirectional multi-positive contrastive loss with in-batch negatives
- **Optimizer**: Adam, learning rate 3e-4
- **Train/validation split**: 90/10 by query within the train split
- **Epoch budget**: Up to 30 epochs with early stopping
- **Checkpoint selection**: Best validation `MRR@10` checkpoint, patience 4, `min_delta=0.001`
- **Temperature**: 0.05
- **ESCI train pairs**: 251,353 aligned query-product positives (28,288 validation)
- **MS MARCO train pairs**: 29,644 aligned query-passage positives (3,315 validation)

On CPU, the two-tower training and validation loop usually takes tens of minutes once embeddings are already cached. The much longer first full run is dominated by embedding generation and upload, not by model fitting itself.

## Results

### Amazon ESCI (352K products, 3,134 test queries)

| Metric | BM25 | Similarity (baseline) | Retrieval | TT Similarity | TT Retrieval |
|--------|------|------------|-----------|---------------|--------------|
| MRR@10 | 0.5738 (−7.7%) | 0.6219 | 0.7372 (+18.5%) | 0.7161 (+15.1%) | **0.7442** (+19.7%) |
| NDCG@10 | 0.3299 (−19.5%) | 0.4098 | 0.5175 (+26.3%) | 0.4895 (+19.4%) | **0.5182** (+26.4%) |
| Recall@10 | 0.2085 (−22.9%) | 0.2704 | 0.3406 (+26.0%) | 0.3246 (+20.0%) | **0.3429** (+26.8%) |
| Recall@100 | 0.4702 (−24.6%) | 0.6232 | 0.7492 (+20.2%) | 0.7376 (+18.4%) | **0.7576** (+21.6%) |

BM25 here is a lightweight lexical baseline over raw product titles only. Even that simple sparse baseline is competitive enough to be worth keeping in the benchmark, but all embedding-based methods outperform it by a clear margin. `TT Retrieval` remains the strongest overall offline result in this repo and slightly outperforms the frozen retrieval baseline on all four metrics.

### MS MARCO (500K passages, 5,000 test queries)

| Metric | BM25 | Similarity (baseline) | Retrieval | TT Similarity | TT Retrieval |
|--------|------|------------|-----------|---------------|--------------|
| MRR@10 | 0.2566 (−39.8%) | 0.4265 | 0.4578 (+7.3%) | 0.4352 (+2.0%) | **0.4645** (+8.9%) |
| NDCG@10 | 0.3182 (−37.9%) | 0.5121 | 0.5430 (+6.0%) | 0.5227 (+2.1%) | **0.5500** (+7.4%) |
| Recall@10 | 0.5267 (−33.6%) | 0.7926 | 0.8217 (+3.7%) | 0.8106 (+2.3%) | **0.8303** (+4.8%) |
| Recall@100 | 0.7855 (−20.0%) | 0.9815 | 0.9852 (+0.4%) | 0.9837 (+0.2%) | **0.9873** (+0.6%) |

The same overall pattern holds across both datasets: Retrieval embeddings outperform Similarity, and two-tower learned projections improve over frozen baselines. `TT Retrieval` is the strongest method on both datasets, with clear gains over the frozen retrieval baseline across all metrics. BM25 is notably weaker on MS MARCO than ESCI — passage text is longer and more varied than product titles, making lexical matching less effective. The embedding-based methods achieve near-perfect Recall@100 (>0.98), indicating the 500K-passage subset retains excellent coverage of the query-relevant passages.

### Vector Search 2.0 deployment

The full pipeline deploys 5 collections per dataset to Vector Search 2.0 for online serving. Collection names are prefixed by dataset (`tt-demo-*` for ESCI, `tt-msmarco-*` for MS MARCO):

**ESCI collections:**

| Collection | Embeddings | Description |
|------------|-----------|-------------|
| `tt-demo-bm25-v1` | BM25 sparse | Title-only sparse lexical baseline |
| `tt-demo-sim-v4` | Similarity | SEMANTIC_SIMILARITY task type |
| `tt-demo-baseline-v4` | Retrieval | Search-task prefixed embeddings |
| `tt-demo-twotower-sim-v4` | TT Similarity | Learned projections on similarity embeddings |
| `tt-demo-twotower-ret-v4` | TT Retrieval | Learned projections on retrieval embeddings |

**MS MARCO collections:**

| Collection | Embeddings | Description |
|------------|-----------|-------------|
| `tt-msmarco-bm25-v1` | BM25 sparse | Passage text sparse lexical baseline |
| `tt-msmarco-sim-v1` | Similarity | SEMANTIC_SIMILARITY task type |
| `tt-msmarco-baseline-v1` | Retrieval | Search-task prefixed embeddings |
| `tt-msmarco-twotower-sim-v1` | TT Similarity | Learned projections on similarity embeddings |
| `tt-msmarco-twotower-ret-v1` | TT Retrieval | Learned projections on retrieval embeddings |

With `--deploy-vs2`, the pipeline also evaluates hybrid search (vector + text) with the `semantic-ranker-fast@latest` reranker.
The web app has two tabs sharing a single query bar and a **dataset switcher** dropdown. The app loads all available datasets at startup (ESCI and/or MS MARCO, skipping any whose VS2 collections aren't deployed). Switching datasets updates the query pool, relevance grades, grade colors, and all visualizations dynamically — ESCI shows 4-grade E/S/C/I bars while MS MARCO shows 2-grade R/N bars.

The **Results** tab compares 4 systems side by side: BM25 sparse, Similarity, Two-Tower (learned projection on similarity embeddings), and Retrieval. Each column shows a top-10 relevance grade stacked bar, per-query metrics (RR@10, NDCG@10, Recall@10), and rank diff annotations showing how each result moved relative to the BM25 baseline. The **Embedding Map** tab displays dual side-by-side maps (defaulting to Similarity vs Retrieval) for visual comparison of how each embedding space clusters search results (see below). Each map panel shows a relevance grade bar and metrics for the current query's top-10 results. A search fires both tabs in parallel, so switching between them shows results immediately without re-querying. The BM25 column uses the VS2 sparse collection rather than a local in-memory ranker.
In practice, BM25 sparse index creation can continue past the initial `op.result()` wait window even after sparse object upload finishes. If the deploy path times out while waiting on index creation, rerun-safe ingestion still leaves the collection in place, and the most reliable readiness check is a live sparse query. The current BM25 collection has been verified queryable with a search such as `wireless mouse`.

### Embedding Map visualization

The "Embedding Map" tab displays two side-by-side deck.gl scatter plots (defaulting to Similarity on the left, Retrieval on the right), each projecting all 352K product embeddings into 2D via UMAP. Each map has its own method selector dropdown to switch between the four dense embedding spaces (Similarity, Retrieval, TT Similarity, TT Retrieval). On each query, both maps auto-zoom to their respective top-10 result clusters, label each result with its rank, and place a green query marker at the cluster centroid. The viz tab loads lazily — coordinates and cluster data are fetched only when the tab is first activated.

Each map panel shows a **relevance grade bar** for the current query's top-10 results — a stacked bar with E (Exact), S (Substitute), C (Complement), and I (Irrelevant) segment counts from the human-annotated qrels. Below the bar, per-query metrics (RR@10, NDCG@10, Recall@10) are displayed. Scatter dots are colored by relevance grade using a blue-shade palette matching the Results tab: dark blue for Exact, lighter blue for Substitute, and gray for Irrelevant or unknown. For non-test queries (those without qrels annotations), a "No relevance data" message is shown instead.

This dual-map visualization reveals how each embedding method organizes products:

- **Similarity** embeddings cluster by broad product *category* — electronics, books, clothing form distinct regions. Top-10 results tend to include more irrelevant items because semantically related but non-relevant products (mouse pads for a "wireless mouse" query) sit nearby.
- **Retrieval** embeddings organize around *search intent* rather than category. The search-task prefix (`task: search result | query:`) trains the space to group products by what queries they answer, producing more relevant top-10 results than Similarity.
- **TT Similarity** applies a learned correction to the Similarity space. The residual MLP pulls exact matches (E-label) closer together and pushes complements (C-label) apart, surfacing more E and S results in the top-10 compared to the frozen Similarity baseline.
- **TT Retrieval** refines the already-strong Retrieval space. Because the base embeddings are already well-organized for search, the two-tower correction is smaller — the UMAP looks structurally similar to Retrieval with subtle refinements.

The key pattern: progressively more E and S grades in the top-10 from Similarity → Retrieval → TT variants correlate directly with the offline metrics (MRR, NDCG, Recall). Queries where Similarity and Retrieval disagree on results are especially informative — the side-by-side maps show different products highlighted in different regions, revealing how the two task types encode different notions of relevance.

Cluster labels are overlaid on the scatter plot and change with zoom level. At the default zoom, coarse HDBSCAN clusters (~30–45 per method) show broad category names like "Iphone Case", "Sterling Silver", "Non Gmo". Zooming in past the threshold switches to fine-grained clusters (~450–540 per method) with more specific labels like "Usb Cable", "Birthday Party", "Yoga Pants". Labels are extracted from the most frequent meaningful terms in each cluster's product titles. When a search is active, cluster labels hide to keep the result highlight readable; clicking "Clear" brings them back.

To generate UMAP coordinates and cluster labels:

```bash
uv run python -m tt_model.pipeline --stage umap \
  --embedding sim_products=<sim_products_blob>.npz \
  --embedding products=<products_blob>.npz \
  --reuse-checkpoints
```

## Embedding Storage

Embeddings are stored in Google Cloud Storage (`gs://gcp-samples-ic0-tt-demo/`) with timestamped filenames:

```
<dataset_name>-<model_name>-<task_type>-<YYYYMMDD-HHMM>.npz
```

Example: `esci_products-gemini-embedding-2-semantic_similarity-20260523-0011.npz`

Previously computed embeddings can be loaded with the `--embeddings` flag to skip recomputation. The pipeline can also mix cached product embeddings with freshly recomputed query embeddings when older query blobs were generated with a different query-id scheme.

## Project Structure

```
2026-0522-tt-model/
├── pyproject.toml
├── src/
│   └── tt_model/
│       ├── bm25.py              # Lightweight BM25 baseline + sparse vectors
│       ├── config.py            # Hyperparameters and paths
│       ├── data.py              # Dataset loading (ESCI + MS MARCO) with DatasetConfig
│       ├── embed.py             # Gemini Embedding 2 with GCS storage
│       ├── model.py             # JAX/Flax TwoTowerModel + contrastive loss
│       ├── train.py             # Training loop with TrainState
│       ├── evaluate.py          # MRR, NDCG, Recall metrics (pure numpy)
│       ├── vs2.py               # Vector Search 2.0 + reranker integration
│       ├── pipeline.py          # End-to-end orchestrator
│       ├── umap_coords.py       # UMAP 2D projection precomputation
│       ├── cluster_labels.py    # HDBSCAN cluster labeling for viz
│       ├── app.py               # FastAPI web app
│       └── templates/
│           └── search.html      # Search demo UI with Results + Embedding Map tabs
└── data/
    ├── model_params/            # ESCI two-tower checkpoints
    ├── model_params_msmarco/    # MS MARCO two-tower checkpoints
    ├── umap/                    # ESCI UMAP coordinates + cluster labels
    └── umap_msmarco/            # MS MARCO UMAP coordinates + cluster labels
```

## Usage

```bash
# Install dependencies
uv sync

# ── ESCI (default) ──

# Quick test (1K products)
uv run python -m tt_model.pipeline --max-products 1000

# BM25 only
uv run python -m tt_model.pipeline --stage bm25

# Offline baselines (BM25 + Similarity + Retrieval)
uv run python -m tt_model.pipeline --stage baselines

# Full run (352K products, ~3 hours first time; retrains are much faster with cached embeddings)
uv run python -m tt_model.pipeline

# ── MS MARCO ──

# Quick test (10K passages)
uv run python -m tt_model.pipeline --dataset msmarco --max-passages 10000

# BM25 only
uv run python -m tt_model.pipeline --dataset msmarco --stage bm25

# Full run (500K passages)
uv run python -m tt_model.pipeline --dataset msmarco

# Reuse all six embedding blobs from GCS
uv run python -m tt_model.pipeline \
  --embeddings \
  <sim_products_blob>.npz \
  <sim_train_queries_blob>.npz \
  <sim_test_queries_blob>.npz \
  <products_blob>.npz \
  <train_queries_blob>.npz \
  <test_queries_blob>.npz

# Reuse only cached product embeddings and recompute current query embeddings
uv run python -m tt_model.pipeline \
  --embedding sim_products=<sim_products_blob>.npz \
  --embedding products=<products_blob>.npz

# Evaluate using the latest local checkpoints instead of retraining
uv run python -m tt_model.pipeline \
  --stage eval-checkpoints \
  --reuse-checkpoints \
  --embedding sim_products=<sim_products_blob>.npz \
  --embedding products=<products_blob>.npz

# Train only one tower variant
uv run python -m tt_model.pipeline --stage train-sim
uv run python -m tt_model.pipeline --stage train-ret

# With Vector Search 2.0 deployment
uv run python -m tt_model.pipeline --deploy-vs2

# Build and deploy only the BM25 sparse collection to VS2
uv run python -m tt_model.pipeline --stage bm25 --deploy-vs2-target bm25

# Deploy exactly one existing dense collection to VS2
uv run python -m tt_model.pipeline \
  --deploy-vs2-target similarity \
  --embedding sim_products=<sim_products_blob>.npz
uv run python -m tt_model.pipeline \
  --deploy-vs2-target retrieval \
  --embedding products=<products_blob>.npz

# Web app (requires the VS2 collections above, including BM25 sparse)
uv run uvicorn tt_model.app:app --port 8080
```

Embedding artifacts now write a `.metadata.json` sidecar in GCS that records dataset name, split, id scheme, task type, and text role. On reuse, the pipeline validates that metadata up front so incompatible cached query blobs fail early with a clear error instead of breaking deep in the run.

The most useful stage modes are:

- `umap`: precompute UMAP 2D coordinates and HDBSCAN cluster labels for the embedding map visualization
- `bm25`: lexical BM25 baseline only
- `baselines`: BM25 plus the frozen similarity and retrieval baselines
- `train-sim`: train and evaluate only the similarity two-tower model
- `train-ret`: train and evaluate only the retrieval two-tower model
- `eval-checkpoints`: skip retraining and evaluate from the latest local checkpoints

For targeted VS2 deploys, `--deploy-vs2-target` accepts:

- `bm25`: build the sparse BM25 document vectors and deploy only that collection
- `similarity`: deploy only the frozen similarity collection
- `retrieval`: deploy only the frozen retrieval collection
- `tt-sim`: deploy only the similarity two-tower collection
- `tt-ret`: deploy only the retrieval two-tower collection

BM25 sparse deploys are resumable. The uploader retries `429 ResourceExhausted` responses with exponential backoff, skips already-created batches on rerun, and stores local resume state under `data/vs2_resume/`. That makes `--stage bm25 --deploy-vs2-target bm25` safe to rerun if VS2 throttles mid-ingest.

### Requirements

- Python 3.11+
- Google Cloud project with Vertex AI API enabled
- `GOOGLE_CLOUD_PROJECT` environment variable set
- For `--deploy-vs2`: Vector Search API and Discovery Engine API enabled

## Dependencies

- `google-genai` — Gemini Embedding 2 API
- `google-cloud-storage` — Embedding storage on GCS
- `google-cloud-vectorsearch` — Vector Search 2.0
- `jax[cpu]`, `flax`, `optax` — Two-tower model training
- `fastapi`, `uvicorn`, `jinja2` — Web app
- `datasets` — Amazon ESCI and MS MARCO dataset loading
- `umap-learn` — UMAP dimensionality reduction for embedding visualization
- `hdbscan` — Hierarchical clustering for zoom-level cluster labels
- `numpy`, `tqdm` — Utilities

## TODO (MS MARCO)

- [x] Run full MS MARCO pipeline: embeddings, training, evaluation (`uv run python -m tt_model.pipeline --dataset msmarco`)
- [x] Add MS MARCO offline results table to this README
- [ ] Deploy MS MARCO VS2 collections (`--deploy-vs2` with `--dataset msmarco`)
- [x] Precompute MS MARCO UMAP coordinates and cluster labels (`--stage umap --dataset msmarco`)
- [ ] Test web app dataset switcher with both datasets loaded simultaneously
