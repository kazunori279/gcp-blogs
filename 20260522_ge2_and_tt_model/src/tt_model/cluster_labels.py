from __future__ import annotations

import json
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from tqdm import tqdm

from tt_model.config import LABEL_MODEL, UMAP_DIR, UMAP_METHODS
from tt_model.embed import _get_client

STOPWORDS_BASE = frozenset(
    "a an the and or but in on at to for of with by from is are was were be "
    "been being have has had do does did will would shall should may might can "
    "could not no nor so as if then than that this these those it its i me my "
    "we our you your he she they them their him her all any each every some "
    "more most other such only also very just how what which who whom when "
    "where why out up down off over under again further once here there about "
    "above below between through during before after into too set get got new "
    "one two per".split()
)

# Default: ESCI ecommerce stopwords for backward compatibility
STOPWORDS = STOPWORDS_BASE | frozenset(
    "pack free size inch black white blue red green pink color "
    "large small medium extra compatible fits fit use used great best high "
    "quality made make premium pro plus super ultra mini max style design "
    "type model version edition series part without love life day kids men "
    "women girl boy gift home office".split()
)

COARSE_MIN_CLUSTER_SIZE = 2000
FINE_MIN_CLUSTER_SIZE = 200

MAX_SAMPLE = 50
MAX_WORKERS = 10
MAX_RETRIES = 3


def _tokenize(text: str, stopwords: frozenset[str] = STOPWORDS) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in stopwords]


def _cluster_label_heuristic(
    titles: list[str],
    n_terms: int = 2,
    stopwords: frozenset[str] = STOPWORDS,
) -> str:
    bigram_counts: Counter[tuple[str, str]] = Counter()
    unigram_counts: Counter[str] = Counter()
    for title in titles:
        tokens = _tokenize(title, stopwords)
        unigram_counts.update(set(tokens))
        for a, b in zip(tokens, tokens[1:]):
            bigram_counts[(a, b)] += 1
    best_bigram = bigram_counts.most_common(1)
    if best_bigram and best_bigram[0][1] >= len(titles) * 0.08:
        a, b = best_bigram[0][0]
        return f"{a.title()} {b.title()}"
    top = [w for w, _ in unigram_counts.most_common(n_terms)]
    return " / ".join(t.title() for t in top)


def _cluster_label_llm(
    texts: list[str],
    use_titles: bool = True,
    cluster_context: str = "product titles from a cluster of similar products",
) -> str:
    sample = random.sample(texts, min(MAX_SAMPLE, len(texts)))
    if use_titles:
        items = "\n".join(f"- {t}" for t in sample)
        prompt = (
            f"Here are sample {cluster_context}:\n\n"
            f"{items}\n\n"
            "Generate a short category label (2-4 words) that describes this group. "
            "Reply with ONLY the label, nothing else."
        )
    else:
        items = ", ".join(sample)
        prompt = (
            "Here are sub-category labels within a broader product category:\n\n"
            f"{items}\n\n"
            "Generate a short label (2-4 words) for the overarching category. "
            "Reply with ONLY the label, nothing else."
        )

    for attempt in range(MAX_RETRIES):
        try:
            client = _get_client()
            response = client.models.generate_content(
                model=LABEL_MODEL,
                contents=prompt,
            )
            label = response.text.strip().strip('"').strip("'")
            if label:
                return label
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1 * (attempt + 1))
    return _cluster_label_heuristic(texts)


def _run_hdbscan(coords_2d: np.ndarray, min_cluster_size: int) -> np.ndarray:
    import hdbscan

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=10,
        metric="euclidean",
    )
    return clusterer.fit_predict(coords_2d)


def compute_clusters_for_method(
    x: np.ndarray,
    y: np.ndarray,
    doc_texts: list[str],
    cluster_context: str = "product titles from a cluster of similar products",
    stopwords: frozenset[str] = STOPWORDS,
) -> list[dict]:
    coords = np.column_stack([x, y])

    # --- Level 1 (fine): label from document texts ---
    fine_labels_arr = _run_hdbscan(coords, FINE_MIN_CLUSTER_SIZE)
    fine_cids = sorted(set(fine_labels_arr) - {-1})

    fine_cluster_data = []
    for cid in fine_cids:
        mask = fine_labels_arr == cid
        texts_in = [doc_texts[i] for i in np.where(mask)[0]]
        fine_cluster_data.append({
            "cid": cid,
            "mask": mask,
            "cx": float(x[mask].mean()),
            "cy": float(y[mask].mean()),
            "size": int(mask.sum()),
            "titles": texts_in,
        })

    print(f"  Labeling {len(fine_cluster_data)} fine clusters with {LABEL_MODEL}...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_cluster_label_llm, c["titles"], True, cluster_context): i
            for i, c in enumerate(fine_cluster_data)
        }
        for f in tqdm(as_completed(futures), total=len(futures), desc="  Fine labels"):
            idx = futures[f]
            fine_cluster_data[idx]["label"] = f.result()

    fine_clusters = [
        {"label": c["label"], "cx": round(c["cx"], 6), "cy": round(c["cy"], 6),
         "size": c["size"], "level": 1}
        for c in fine_cluster_data
    ]

    # --- Level 0 (coarse): label from fine cluster labels ---
    coarse_labels_arr = _run_hdbscan(coords, COARSE_MIN_CLUSTER_SIZE)
    coarse_cids = sorted(set(coarse_labels_arr) - {-1})

    coarse_cluster_data = []
    for cid in coarse_cids:
        coarse_mask = coarse_labels_arr == cid
        child_labels = []
        for fc in fine_cluster_data:
            fc_cx, fc_cy = fc["cx"], fc["cy"]
            fc_idx = np.argmin((x - fc_cx) ** 2 + (y - fc_cy) ** 2)
            if coarse_mask[fc_idx]:
                child_labels.append(fc["label"])
        if not child_labels:
            child_labels = [doc_texts[i] for i in np.where(coarse_mask)[0][:MAX_SAMPLE]]
        coarse_cluster_data.append({
            "cx": float(x[coarse_mask].mean()),
            "cy": float(y[coarse_mask].mean()),
            "size": int(coarse_mask.sum()),
            "child_labels": child_labels,
        })

    print(f"  Labeling {len(coarse_cluster_data)} coarse clusters with {LABEL_MODEL}...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_cluster_label_llm, c["child_labels"], False): i
            for i, c in enumerate(coarse_cluster_data)
        }
        for f in tqdm(as_completed(futures), total=len(futures), desc="  Coarse labels"):
            idx = futures[f]
            coarse_cluster_data[idx]["label"] = f.result()

    coarse_clusters = [
        {"label": c["label"], "cx": round(c["cx"], 6), "cy": round(c["cy"], 6),
         "size": c["size"], "level": 0}
        for c in coarse_cluster_data
    ]

    return coarse_clusters + fine_clusters


def precompute_cluster_labels(
    doc_ids: list[str],
    doc_texts: list[str],
    config=None,
    output_dir=None,
):
    from pathlib import Path
    base = Path(output_dir) if output_dir else UMAP_DIR
    base.mkdir(parents=True, exist_ok=True)

    cluster_context = config.cluster_context if config else "product titles from a cluster of similar products"
    sw = STOPWORDS_BASE | config.stopwords_extra if config else STOPWORDS

    for method in UMAP_METHODS:
        path = base / f"{method}.npz"
        if not path.exists():
            print(f"  Skipping {method} — no UMAP coords")
            continue

        print(f"\n--- Cluster labels: {method} ---")
        data = np.load(path, allow_pickle=True)
        x, y = data["x"], data["y"]
        ids_in_file = data["ids"].tolist()

        text_map = dict(zip(doc_ids, doc_texts))
        texts = [text_map.get(pid, "") for pid in ids_in_file]

        clusters = compute_clusters_for_method(
            x, y, texts,
            cluster_context=cluster_context,
            stopwords=sw,
        )

        coarse = sum(1 for c in clusters if c["level"] == 0)
        fine = sum(1 for c in clusters if c["level"] == 1)
        print(f"  {coarse} coarse clusters, {fine} fine clusters")

        out_path = base / f"{method}_clusters.json"
        with open(out_path, "w") as f:
            json.dump(clusters, f)
        print(f"  Saved to {out_path}")


def load_cluster_labels(method: str, umap_dir=None) -> list[dict]:
    from pathlib import Path
    base = Path(umap_dir) if umap_dir else UMAP_DIR
    path = base / f"{method}_clusters.json"
    with open(path) as f:
        return json.load(f)
