# Embedding Visualization Page

## Context

The app currently compares 4 search methods side by side via search results. This adds a `/viz` page that shows *why* results differ: a 2D UMAP projection of all 352K product embeddings for each method, rendered as interactive deck.gl scatter plots in a synchronized 2x2 grid. Users can pan/zoom any panel and all panels follow, hover for product titles, and search to highlight top-K results across panels.

## Approach

**Dimensionality reduction**: UMAP (cosine metric, `random_state=42`). Precomputed via a new `--stage umap` pipeline command and cached as NPZ files under `data/umap/`. UMAP on 352K x 768 takes ~5-10 min per method; run sequentially (5 methods total).

**Frontend**: deck.gl `ScatterplotLayer` with `OrthographicView` (pure 2D, no map tiles). Loaded via CDN. 352K points per panel, synchronized viewports.

**Data transfer**: Binary `Float32Array` over HTTP (2.8MB per method, ~14MB total). Products metadata as JSON (sent once).

**Layout**: 2x2 grid for the 4 dense methods (Similarity, Retrieval, TT Similarity, TT Retrieval). BM25 is omitted from the default grid because its sparse vectors live in a fundamentally different space (vocab-sized dimensions vs 768d), making its UMAP layout not directly comparable. Can be added later as an optional 5th panel.

## Files to create

### `src/tt_model/umap_coords.py`
UMAP precomputation module:
- `compute_umap(embeddings: np.ndarray, n_neighbors=15, min_dist=0.1, metric="cosine", random_state=42) -> np.ndarray` — returns (N, 2) float32
- `precompute_all(sim_product_embs, ret_product_embs, tt_sim_params, tt_ret_params, product_ids)` — runs UMAP for all 4 methods, saves to `data/umap/{method}.npz` with keys `ids`, `x`, `y`
- `load_coords(method: str) -> tuple[list[str], np.ndarray, np.ndarray]` — loads cached (ids, x, y)
- For TT variants: load base embeddings, apply `apply_tower(params, embs, "doc")` from `train.py`, then UMAP
- Normalize UMAP output to [-1, 1] range for consistent viewport across panels

### `src/tt_model/templates/viz.html`
New template following existing conventions (inline CSS, vanilla JS):
- Same header/nav style as `search.html` (blue #1a73e8, with link back to `/`)
- Search bar for query-based highlighting
- 2x2 CSS grid of deck.gl canvases, each labeled (Similarity, Retrieval, TT Similarity, TT Retrieval)
- deck.gl setup:
  - `OrthographicView` per panel
  - `ScatterplotLayer` with binary attribute data (`getPosition` from Float32Array)
  - Shared `onViewStateChange` callback to sync all 4 panels
  - `pickable: true` with `onHover` for tooltip (product title)
  - Point colors: default blue (#1a73e8, alpha 150), highlighted results in red (#ea4335)
- Search flow: POST `/viz/search` → get result IDs per method → update `getFillColor` accessor → dim non-highlighted points to gray (#dadce0, alpha 40)
- Binary coordinate loading:
  ```
  fetch('/viz/coords/similarity') → ArrayBuffer
  → first 4 bytes: uint32 count N
  → next N*4 bytes: float32[] x
  → next N*4 bytes: float32[] y
  → interleave into Float32Array(N*2) for deck.gl positions
  ```
- Load all 4 methods in parallel on page load, show spinner per panel

## Files to modify

### `pyproject.toml`
Add `"umap-learn>=0.5"` to dependencies.

### `src/tt_model/config.py`
Add:
- `UMAP_DIR = DATA_DIR / "umap"`
- `UMAP_METHODS = ["similarity", "retrieval", "tt_similarity", "tt_retrieval"]`

### `src/tt_model/pipeline.py`
Add `--stage umap` that:
1. Loads product embeddings from GCS (requires `--embedding sim_products=... --embedding products=...`)
2. Loads TT checkpoints (`--reuse-checkpoints`)
3. Applies TT projections to get 4 embedding sets
4. Runs UMAP sequentially on each, saves to `data/umap/`

### `src/tt_model/app.py`
Add at startup (optional, wrapped in try/except so search still works without UMAP data):
- Load UMAP coords for each available method into `_ctx`

Add 4 new endpoints:

| Endpoint | Method | Returns |
|----------|--------|---------|
| `GET /viz` | HTML | Jinja2 template with list of available methods |
| `GET /viz/coords/{method}` | Binary | uint32 count + float32[] x + float32[] y |
| `GET /viz/products` | JSON | `{"ids": [...], "titles": [...]}` aligned to coordinate arrays |
| `POST /viz/search` | JSON | `{"results": {"similarity": [pid, ...], ...}}` — reuses existing `_vs2_search` and `_bm25_search` logic |

Add `GZipMiddleware` for binary response compression (~14MB → ~5MB).

### `src/tt_model/templates/search.html`
Add a nav link to `/viz` in the header (small "Embedding Map" link).

## Sequencing

1. `pyproject.toml` + `config.py` — add dependency and constants
2. `umap_coords.py` — new module, test independently
3. `pipeline.py` — add `--stage umap`, run precomputation
4. `app.py` — add endpoints, load UMAP at startup
5. `viz.html` — build the frontend, test in browser
6. `search.html` — add nav link

## Verification

1. Run `uv sync` to install `umap-learn`
2. Run `uv run python -m tt_model.pipeline --stage umap --embedding sim_products=<blob>.npz --embedding products=<blob>.npz --reuse-checkpoints` — confirm 4 NPZ files created in `data/umap/`
3. Run `uv run uvicorn tt_model.app:app --port 8080` — confirm `/viz` loads
4. Open browser to `http://localhost:8080/viz`:
   - 4 panels render with 352K dots each
   - Pan/zoom one panel, all follow
   - Hover shows product title tooltip
   - Enter a search query, results highlight in red across all panels
   - Navigate to `/` from viz page, confirm search page still works
