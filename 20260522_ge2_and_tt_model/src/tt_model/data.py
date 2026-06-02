import hashlib

import numpy as np
from datasets import load_dataset


LABEL_SCORES = {"E": 3, "S": 2, "C": 1, "I": 0}
POSITIVE_LABELS = {"E", "S"}


def query_id_for_text(query: str) -> str:
    """Build a stable query id from query text."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def load_esci(max_products: int | None = None, test_frac: float = 0.15):
    """Load Amazon ESCI dataset for product search recommendation.

    Relevance: E(xact)=3, S(ubstitute)=2, C(omplement)=1, I(rrelevant)=0.
    Uses only E and S as positive pairs. Splits by query into train/test.

    Returns:
        products: dict {product_id: text}
        train_queries: dict {query_id: text}
        train_qrels: dict {query_id: {product_id: relevance}}
        test_queries: dict {query_id: text}
        test_qrels: dict {query_id: {product_id: relevance}}
    """
    print("Loading Amazon ESCI dataset...")
    ds = load_dataset(
        "smangrul/amazon_esci", split="train",
        verification_mode="no_checks",
    )

    # First pass: collect product IDs up to the limit
    print("Building product catalog...")
    products = {}
    for row in ds:
        pid = row["product_id"]
        if pid not in products:
            title = row.get("product_title") or ""
            if title:
                products[pid] = title
        if max_products and len(products) >= max_products:
            break

    product_set = set(products.keys())
    print(f"  Products: {len(products)}")

    # Second pass: collect query-product pairs for known products
    print("Building query-product pairs...")
    query_texts = {}
    all_qrels = {}

    for row in ds:
        pid = row["product_id"]
        if pid not in product_set:
            continue
        esci_label = row["esci_label"]
        if esci_label not in POSITIVE_LABELS:
            continue
        label = LABEL_SCORES[esci_label]

        query = row["query"]
        qid = query_id_for_text(query)
        query_texts[qid] = query
        all_qrels.setdefault(qid, {})[pid] = label

    # Split queries into train/test
    rng = np.random.default_rng(42)
    all_qids = list(all_qrels.keys())
    rng.shuffle(all_qids)
    split_idx = int(len(all_qids) * (1 - test_frac))

    train_qids = set(all_qids[:split_idx])
    test_qids = set(all_qids[split_idx:])

    train_queries = {qid: query_texts[qid] for qid in train_qids}
    train_qrels = {qid: all_qrels[qid] for qid in train_qids}
    test_queries = {qid: query_texts[qid] for qid in test_qids}
    test_qrels = {qid: all_qrels[qid] for qid in test_qids}

    train_pairs = sum(len(v) for v in train_qrels.values())
    test_pairs = sum(len(v) for v in test_qrels.values())
    print(f"  Train queries: {len(train_queries)} ({train_pairs} pairs)")
    print(f"  Test queries: {len(test_queries)} ({test_pairs} pairs)")

    return products, train_queries, train_qrels, test_queries, test_qrels


def align_training_pairs(
    train_qrels: dict,
    query_ids: list[str],
    query_embs: np.ndarray,
    product_ids: list[str],
    product_embs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create aligned query-product pairs plus query-group ids for training."""
    qid_to_idx = {qid: i for i, qid in enumerate(query_ids)}
    pid_to_idx = {pid: i for i, pid in enumerate(product_ids)}

    q_indices = []
    d_indices = []
    group_ids = []
    for qid, rels in train_qrels.items():
        if qid not in qid_to_idx:
            continue
        qi = qid_to_idx[qid]
        for pid in rels:
            if pid not in pid_to_idx:
                continue
            q_indices.append(qi)
            d_indices.append(pid_to_idx[pid])
            group_ids.append(qi)

    print(f"  Aligned {len(q_indices)} training pairs")
    return (
        query_embs[q_indices],
        product_embs[d_indices],
        np.array(group_ids, dtype=np.int32),
    )


def split_train_validation_queries(
    train_queries: dict,
    train_qrels: dict,
    val_frac: float,
    seed: int = 42,
) -> tuple[dict, dict, dict, dict]:
    """Split query-level training data into train and validation subsets."""
    if not 0.0 < val_frac < 1.0:
        raise ValueError(f"val_frac must be between 0 and 1, got {val_frac}")

    qids = list(train_queries.keys())
    if len(qids) < 2:
        raise ValueError("Need at least 2 queries to create a validation split")

    rng = np.random.default_rng(seed)
    rng.shuffle(qids)
    val_size = max(1, int(round(len(qids) * val_frac)))
    val_qids = set(qids[:val_size])
    fit_qids = set(qids[val_size:])

    fit_queries = {qid: train_queries[qid] for qid in qids if qid in fit_qids}
    fit_qrels = {qid: train_qrels[qid] for qid in qids if qid in fit_qids}
    val_queries = {qid: train_queries[qid] for qid in qids if qid in val_qids}
    val_qrels = {qid: train_qrels[qid] for qid in qids if qid in val_qids}

    fit_pairs = sum(len(v) for v in fit_qrels.values())
    val_pairs = sum(len(v) for v in val_qrels.values())
    print(
        "  Validation split: "
        f"{len(fit_queries)} train queries ({fit_pairs} pairs), "
        f"{len(val_queries)} val queries ({val_pairs} pairs)"
    )

    return fit_queries, fit_qrels, val_queries, val_qrels
