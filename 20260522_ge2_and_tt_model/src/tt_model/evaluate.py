import numpy as np
from tqdm import tqdm


def compute_mrr(qrels: dict, results: dict, k: int) -> float:
    """Mean Reciprocal Rank at k."""
    mrr_sum = 0.0
    n = 0
    for qid, rels in qrels.items():
        if qid not in results:
            continue
        n += 1
        ranked = sorted(results[qid].items(), key=lambda x: x[1], reverse=True)[:k]
        for rank, (pid, _) in enumerate(ranked, 1):
            if pid in rels and rels[pid] > 0:
                mrr_sum += 1.0 / rank
                break
    return mrr_sum / n if n > 0 else 0.0


def compute_ndcg(qrels: dict, results: dict, k: int) -> float:
    """Normalized Discounted Cumulative Gain at k."""
    ndcg_sum = 0.0
    n = 0
    for qid, rels in qrels.items():
        if qid not in results:
            continue
        n += 1
        ranked = sorted(results[qid].items(), key=lambda x: x[1], reverse=True)[:k]

        dcg = 0.0
        for rank, (pid, _) in enumerate(ranked, 1):
            rel = rels.get(pid, 0)
            dcg += (2**rel - 1) / np.log2(rank + 1)

        ideal_rels = sorted(rels.values(), reverse=True)[:k]
        idcg = sum(
            (2**rel - 1) / np.log2(rank + 1)
            for rank, rel in enumerate(ideal_rels, 1)
        )
        ndcg_sum += dcg / idcg if idcg > 0 else 0.0

    return ndcg_sum / n if n > 0 else 0.0


def compute_recall(qrels: dict, results: dict, k: int) -> float:
    """Recall at k."""
    recall_sum = 0.0
    n = 0
    for qid, rels in qrels.items():
        if qid not in results:
            continue
        n += 1
        relevant = {pid for pid, rel in rels.items() if rel > 0}
        ranked = sorted(results[qid].items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = {pid for pid, _ in ranked}
        recall_sum += len(relevant & retrieved) / len(relevant) if relevant else 0.0

    return recall_sum / n if n > 0 else 0.0


def evaluate_results(qrels: dict, results: dict) -> dict[str, float]:
    """Evaluate a precomputed run dictionary."""
    return {
        "MRR@10": float(compute_mrr(qrels, results, 10)),
        "NDCG@10": float(compute_ndcg(qrels, results, 10)),
        "Recall@10": float(compute_recall(qrels, results, 10)),
        "Recall@100": float(compute_recall(qrels, results, 100)),
    }


def evaluate_retrieval(
    query_ids: list[str],
    query_embeddings: np.ndarray,
    passage_ids: list[str],
    passage_embeddings: np.ndarray,
    qrels: dict,
    top_k: int = 100,
) -> dict[str, float]:
    """Evaluate retrieval using in-memory cosine similarity."""
    q_norm = query_embeddings / np.linalg.norm(
        query_embeddings, axis=1, keepdims=True
    )
    p_norm = passage_embeddings / np.linalg.norm(
        passage_embeddings, axis=1, keepdims=True
    )

    results = {}
    for i, qid in enumerate(tqdm(query_ids, desc="Evaluating")):
        scores = q_norm[i] @ p_norm.T
        top_indices = np.argsort(scores)[::-1][:top_k]
        results[qid] = {passage_ids[j]: float(scores[j]) for j in top_indices}

    return evaluate_results(qrels, results)


def print_metrics(label: str, metrics: dict):
    print(f"\n=== {label} ===")
    for name, value in metrics.items():
        print(f"  {name:<12} {value:.4f}")


def print_comparison(
    all_metrics: dict[str, dict],
    change_from_label: str | None = None,
    change_to_label: str | None = None,
):
    labels = list(all_metrics.keys())
    col_w = max(len(l) for l in labels) + 2
    col_w = max(col_w, 12)
    baseline_label = change_from_label or labels[0]
    target_label = change_to_label or labels[-1]
    change_header = f"{target_label} vs {baseline_label}"
    change_w = max(len(change_header), 9)
    total_w = 14 + col_w * len(labels) + change_w + 1
    print(f"\n{'=' * total_w}")
    print(f"  {'Metric':<12}", end="")
    for label in labels:
        print(f" {label:>{col_w}}", end="")
    print(f" {change_header:>{change_w}}")
    print(f"  {'-' * (total_w - 4)}")
    metric_names = list(all_metrics[labels[0]].keys())
    for name in metric_names:
        print(f"  {name:<12}", end="")
        for label in labels:
            print(f" {all_metrics[label][name]:>{col_w}.4f}", end="")
        b = all_metrics[baseline_label][name]
        t = all_metrics[target_label][name]
        change = (t - b) / b * 100 if b > 0 else 0
        print(f" {change:>+{change_w - 1}.1f}%")
    print(f"{'=' * total_w}")
