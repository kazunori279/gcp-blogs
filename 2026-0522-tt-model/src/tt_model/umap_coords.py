from __future__ import annotations

import numpy as np
from tqdm import tqdm

from tt_model.config import UMAP_DIR, UMAP_METHODS
from tt_model.train import apply_tower


def compute_umap(
    embeddings: np.ndarray,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "cosine",
    random_state: int = 42,
) -> np.ndarray:
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=random_state,
        verbose=True,
    )
    coords = reducer.fit_transform(embeddings)
    return coords.astype(np.float32)


def _normalize_coords(coords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y = coords[:, 0], coords[:, 1]
    x_min, x_max = x.min(), x.max()
    y_min, y_max = y.min(), y.max()
    x_range = x_max - x_min or 1.0
    y_range = y_max - y_min or 1.0
    x_norm = 2.0 * (x - x_min) / x_range - 1.0
    y_norm = 2.0 * (y - y_min) / y_range - 1.0
    return x_norm.astype(np.float32), y_norm.astype(np.float32)


def precompute_all(
    sim_product_embs: np.ndarray,
    ret_product_embs: np.ndarray,
    tt_sim_params,
    tt_ret_params,
    product_ids: list[str],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    UMAP_DIR.mkdir(parents=True, exist_ok=True)

    embedding_sets = {
        "similarity": sim_product_embs,
        "retrieval": ret_product_embs,
        "tt_similarity": apply_tower(tt_sim_params, sim_product_embs, "doc"),
        "tt_retrieval": apply_tower(tt_ret_params, ret_product_embs, "doc"),
    }

    results = {}
    for method in UMAP_METHODS:
        print(f"\n--- UMAP: {method} ({len(product_ids):,} products) ---")
        embs = embedding_sets[method]
        coords = compute_umap(embs)
        x, y = _normalize_coords(coords)

        out_path = UMAP_DIR / f"{method}.npz"
        np.savez_compressed(out_path, ids=np.array(product_ids), x=x, y=y)
        print(f"  Saved to {out_path}")
        results[method] = (x, y)

    return results


def load_coords(method: str) -> tuple[list[str], np.ndarray, np.ndarray]:
    path = UMAP_DIR / f"{method}.npz"
    data = np.load(path, allow_pickle=True)
    ids = data["ids"].tolist()
    return ids, data["x"], data["y"]
