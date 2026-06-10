import hashlib
from dataclasses import dataclass, field

import numpy as np
from datasets import load_dataset


LABEL_SCORES = {"E": 3, "S": 2, "C": 1, "I": 0}
POSITIVE_LABELS = {"E", "S"}


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    display_name: str
    label_scores: dict[str, int]
    positive_labels: frozenset[str]
    score_to_label: dict[int, str]
    grade_order: list[str]
    grade_colors: dict[str, str]
    grade_names: dict[str, str]
    doc_template: str
    query_template: str
    embedding_prefix: str
    collection_prefix: str
    doc_noun: str
    cluster_context: str
    stopwords_extra: frozenset[str] = field(default_factory=frozenset)


ESCI_CONFIG = DatasetConfig(
    name="esci",
    display_name="Amazon ESCI",
    label_scores={"E": 3, "S": 2, "C": 1, "I": 0},
    positive_labels=frozenset({"E", "S"}),
    score_to_label={3: "E", 2: "S", 1: "C", 0: "I"},
    grade_order=["E", "S", "C", "I"],
    grade_colors={"E": "#1a73e8", "S": "#4d9cf6", "C": "#a8c7fa", "I": "#e8eaed"},
    grade_names={
        "E": "Exact match", "S": "Substitute",
        "C": "Complement", "I": "Irrelevant",
    },
    doc_template="title: none | text: {t}",
    query_template="task: search result | query: {t}",
    embedding_prefix="esci",
    collection_prefix="tt-demo",
    doc_noun="products",
    cluster_context="product titles from a cluster of similar products",
    stopwords_extra=frozenset(
        "pack free size inch black white blue red green pink color "
        "large small medium extra compatible fits fit use used great best high "
        "quality made make premium pro plus super ultra mini max style design "
        "type model version edition series part without love life day kids men "
        "women girl boy gift home office".split()
    ),
)

MSMARCO_CONFIG = DatasetConfig(
    name="msmarco",
    display_name="MS MARCO",
    label_scores={"R": 1, "N": 0},
    positive_labels=frozenset({"R"}),
    score_to_label={1: "R", 0: "N"},
    grade_order=["R", "N"],
    grade_colors={"R": "#1a73e8", "N": "#e8eaed"},
    grade_names={"R": "Relevant", "N": "Not relevant"},
    doc_template="passage: {t}",
    query_template="task: search result | query: {t}",
    embedding_prefix="msmarco",
    collection_prefix="tt-msmarco",
    doc_noun="passages",
    cluster_context="web passage excerpts from a cluster of similar passages",
    stopwords_extra=frozenset(
        "www http https com org net html page site website click "
        "read more learn article post blog news update".split()
    ),
)

_DATASET_CONFIGS = {"esci": ESCI_CONFIG, "msmarco": MSMARCO_CONFIG}


def get_dataset_config(name: str) -> DatasetConfig:
    if name not in _DATASET_CONFIGS:
        raise ValueError(
            f"Unknown dataset: {name!r}. Choose from: {list(_DATASET_CONFIGS)}"
        )
    return _DATASET_CONFIGS[name]


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


def load_msmarco(max_passages: int | None = 500_000):
    """Load MS MARCO passage ranking dataset from BeIR format.

    Uses BeIR/msmarco for corpus+queries and BeIR/msmarco-qrels for
    relevance judgments. Binary relevance: 1=relevant, 0=not relevant.
    Train/test split comes from the dataset itself (train vs validation).

    Returns same 5-tuple shape as load_esci:
        passages, train_queries, train_qrels, test_queries, test_qrels
    """
    print("Loading MS MARCO passage ranking dataset...")

    # Load corpus
    print("Loading corpus...")
    corpus_ds = load_dataset(
        "BeIR/msmarco", "corpus", split="corpus",
        verification_mode="no_checks",
    )

    # Load qrels to figure out which passages are actually referenced
    print("Loading relevance judgments...")
    train_qrels_ds = load_dataset(
        "BeIR/msmarco-qrels", split="train",
        verification_mode="no_checks",
    )
    test_qrels_ds = load_dataset(
        "BeIR/msmarco-qrels", split="validation",
        verification_mode="no_checks",
    )

    # Collect passage IDs referenced in qrels so we prioritize those
    referenced_pids = set()
    for row in train_qrels_ds:
        if row["score"] > 0:
            referenced_pids.add(str(row["corpus-id"]))
    for row in test_qrels_ds:
        if row["score"] > 0:
            referenced_pids.add(str(row["corpus-id"]))
    print(f"  Passages referenced in qrels: {len(referenced_pids)}")

    # Build passage catalog: prioritize referenced passages, then fill up
    print("Building passage catalog...")
    passages = {}
    deferred = {}
    for row in corpus_ds:
        pid = str(row["_id"])
        text = (row.get("text") or "").strip()
        if not text:
            continue
        if pid in referenced_pids:
            passages[pid] = text
        else:
            if max_passages is None or len(passages) + len(deferred) < max_passages:
                deferred[pid] = text
        if max_passages and len(passages) + len(deferred) >= max_passages:
            break

    # Merge referenced + deferred up to limit
    if max_passages:
        remaining = max_passages - len(passages)
        if remaining > 0:
            for pid, text in list(deferred.items())[:remaining]:
                passages[pid] = text
    else:
        passages.update(deferred)

    passage_set = set(passages.keys())
    print(f"  Passages: {len(passages)}")

    # Load queries
    print("Loading queries...")
    queries_ds = load_dataset(
        "BeIR/msmarco", "queries", split="queries",
        verification_mode="no_checks",
    )
    all_query_texts = {}
    for row in queries_ds:
        qid = str(row["_id"])
        text = (row.get("text") or "").strip()
        if text:
            all_query_texts[qid] = text

    # Build qrels from train and test splits, filtering to our passage subset
    def _build_qrels(qrels_ds, label="split"):
        queries = {}
        qrels = {}
        for row in qrels_ds:
            score = row["score"]
            if score <= 0:
                continue
            qid = str(row["query-id"])
            pid = str(row["corpus-id"])
            if pid not in passage_set:
                continue
            if qid not in all_query_texts:
                continue
            queries[qid] = all_query_texts[qid]
            qrels.setdefault(qid, {})[pid] = score
        pairs = sum(len(v) for v in qrels.values())
        print(f"  {label}: {len(queries)} queries ({pairs} pairs)")
        return queries, qrels

    train_queries, train_qrels = _build_qrels(train_qrels_ds, "Train")
    test_queries, test_qrels = _build_qrels(test_qrels_ds, "Test")

    return passages, train_queries, train_qrels, test_queries, test_qrels


def load_dataset_by_config(
    config: DatasetConfig,
    max_docs: int | None = None,
):
    if config.name == "esci":
        return load_esci(max_products=max_docs)
    elif config.name == "msmarco":
        return load_msmarco(max_passages=max_docs)
    raise ValueError(f"Unknown dataset: {config.name}")
