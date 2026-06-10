import argparse

import numpy as np

from tt_model.bm25 import BM25Index, evaluate_bm25_index
from tt_model.config import SEED, VALIDATION_FRAC, collection_names, model_params_dir
from tt_model.data import (
    DatasetConfig,
    align_training_pairs,
    get_dataset_config,
    load_dataset_by_config,
    split_train_validation_queries,
)
from tt_model.embed import compute_and_upload_embeddings, load_embeddings
from tt_model.evaluate import evaluate_retrieval, print_comparison, print_metrics
from tt_model.train import apply_tower, load_checkpoint, train

EMBEDDING_KEYS = (
    "sim_products",
    "sim_train_queries",
    "sim_test_queries",
    "products",
    "train_queries",
    "test_queries",
)


def _reorder_embeddings(
    expected_ids: list[str],
    loaded_ids: list[str],
    embeddings: np.ndarray,
) -> np.ndarray:
    """Reorder loaded embeddings to match the current dataset id order."""
    index_by_id = {str(item_id): i for i, item_id in enumerate(loaded_ids)}
    missing = [item_id for item_id in expected_ids if item_id not in index_by_id]
    if missing:
        raise ValueError(
            f"Missing {len(missing)} ids in loaded embeddings; first missing id: {missing[0]}"
        )
    return embeddings[[index_by_id[item_id] for item_id in expected_ids]]


def _expected_embedding_metadata(
    dataset_name: str,
    split: str,
    expected_ids: list[str],
    task_type: str | None,
    text_role: str,
    id_scheme: str | None = None,
) -> dict:
    if id_scheme is None:
        id_scheme = "sha256(query_text)" if "queries" in dataset_name else "product_id"
    return {
        "dataset_name": dataset_name,
        "split": split,
        "id_scheme": id_scheme,
        "count": len(expected_ids),
        "task_type": task_type or "retrieval",
        "text_role": text_role,
    }


def _validate_embedding_metadata(blob_name: str, metadata: dict | None, expected: dict):
    """Validate sidecar metadata when present; fall back to id alignment otherwise."""
    if metadata is None:
        return
    mismatches = []
    for key in ("dataset_name", "split", "id_scheme", "count", "task_type", "text_role"):
        if key in metadata and metadata[key] != expected[key]:
            mismatches.append(f"{key}={metadata[key]!r} (expected {expected[key]!r})")
    if mismatches:
        raise ValueError(
            f"Embedding metadata mismatch for {blob_name}: " + ", ".join(mismatches)
        )


def _load_or_compute_embeddings(
    blob_name: str | None,
    expected_ids: list[str],
    texts: list[str],
    dataset_name: str,
    task_type: str | None,
    text_role: str,
    split: str,
    blob_names: dict[str, str],
    blob_key: str,
    id_scheme: str | None = None,
) -> np.ndarray:
    expected_metadata = _expected_embedding_metadata(
        dataset_name=dataset_name,
        split=split,
        expected_ids=expected_ids,
        task_type=task_type,
        text_role=text_role,
        id_scheme=id_scheme,
    )
    if blob_name:
        loaded_ids, embeddings, metadata = load_embeddings(blob_name)
        _validate_embedding_metadata(blob_name, metadata, expected_metadata)
        return _reorder_embeddings(expected_ids, loaded_ids, embeddings)

    blob_names[blob_key], embeddings = compute_and_upload_embeddings(
        expected_ids,
        texts,
        dataset_name,
        task_type=task_type,
        metadata=expected_metadata,
    )
    return embeddings


def _load_dataset(config: DatasetConfig, max_docs: int | None):
    print("\n" + "=" * 60)
    print(f"Step 1: Loading {config.display_name} dataset")
    print("=" * 60)
    docs, train_queries, train_qrels, test_queries, test_qrels = (
        load_dataset_by_config(config, max_docs=max_docs)
    )

    return {
        "products": docs,
        "train_queries": train_queries,
        "train_qrels": train_qrels,
        "test_queries": test_queries,
        "test_qrels": test_qrels,
        "product_ids": list(docs.keys()),
        "product_texts": list(docs.values()),
        "train_query_ids": list(train_queries.keys()),
        "train_query_texts": list(train_queries.values()),
        "test_query_ids": list(test_queries.keys()),
        "test_query_texts": list(test_queries.values()),
    }


def _prepare_embeddings(
    dataset: dict,
    embeddings: dict[str, str] | None,
    config: DatasetConfig,
):
    print("\n" + "=" * 60)
    print("Step 2: Embeddings")
    print("=" * 60)

    blob_names = {}
    if embeddings:
        print("\n--- Reusing embeddings from GCS where available ---")

    product_ids = dataset["product_ids"]
    product_texts = dataset["product_texts"]
    train_query_ids = dataset["train_query_ids"]
    train_query_texts = dataset["train_query_texts"]
    test_query_ids = dataset["test_query_ids"]
    test_query_texts = dataset["test_query_texts"]

    prefix = config.embedding_prefix
    doc_id_scheme = "product_id" if config.name == "esci" else "passage_id"
    query_id_scheme = "sha256(query_text)" if config.name == "esci" else "query_id"

    sim_product_embs = _load_or_compute_embeddings(
        embeddings.get("sim_products") if embeddings else None,
        product_ids,
        product_texts,
        f"{prefix}_products",
        "SEMANTIC_SIMILARITY",
        "product_text",
        "products",
        blob_names,
        "sim_products",
        id_scheme=doc_id_scheme,
    )
    sim_train_query_embs = _load_or_compute_embeddings(
        embeddings.get("sim_train_queries") if embeddings else None,
        train_query_ids,
        train_query_texts,
        f"{prefix}_train_queries",
        "SEMANTIC_SIMILARITY",
        "query_text",
        "train",
        blob_names,
        "sim_train_queries",
        id_scheme=query_id_scheme,
    )
    sim_test_query_embs = _load_or_compute_embeddings(
        embeddings.get("sim_test_queries") if embeddings else None,
        test_query_ids,
        test_query_texts,
        f"{prefix}_test_queries",
        "SEMANTIC_SIMILARITY",
        "query_text",
        "test",
        blob_names,
        "sim_test_queries",
        id_scheme=query_id_scheme,
    )
    product_embs = _load_or_compute_embeddings(
        embeddings.get("products") if embeddings else None,
        product_ids,
        [config.doc_template.format(t=t) for t in product_texts],
        f"{prefix}_products",
        None,
        "product_text_prefixed",
        "products",
        blob_names,
        "products",
        id_scheme=doc_id_scheme,
    )
    train_query_embs = _load_or_compute_embeddings(
        embeddings.get("train_queries") if embeddings else None,
        train_query_ids,
        [config.query_template.format(t=t) for t in train_query_texts],
        f"{prefix}_train_queries",
        None,
        "query_text_prefixed",
        "train",
        blob_names,
        "train_queries",
        id_scheme=query_id_scheme,
    )
    test_query_embs = _load_or_compute_embeddings(
        embeddings.get("test_queries") if embeddings else None,
        test_query_ids,
        [config.query_template.format(t=t) for t in test_query_texts],
        f"{prefix}_test_queries",
        None,
        "query_text_prefixed",
        "test",
        blob_names,
        "test_queries",
        id_scheme=query_id_scheme,
    )

    if blob_names:
        header = "--- New GCS blob names generated in this run ---" if embeddings else "--- GCS blob names (use with --embedding) ---"
        print(f"\n{header}")
        for key, name in blob_names.items():
            print(f"  {key}: {name}")

    return {
        "sim_product_embs": sim_product_embs,
        "sim_train_query_embs": sim_train_query_embs,
        "sim_test_query_embs": sim_test_query_embs,
        "product_embs": product_embs,
        "train_query_embs": train_query_embs,
        "test_query_embs": test_query_embs,
    }


def _build_bm25_index(dataset: dict) -> BM25Index:
    return BM25Index(dataset["product_ids"], dataset["product_texts"])


def _run_bm25(
    dataset: dict,
    bm25_index: BM25Index | None = None,
    doc_noun: str = "products",
) -> tuple[dict[str, float], BM25Index]:
    print("\n" + "=" * 60)
    print("Step 3: BM25 baseline")
    print("=" * 60)
    bm25_index = bm25_index or _build_bm25_index(dataset)
    bm25_metrics = evaluate_bm25_index(
        bm25_index,
        dataset["test_query_ids"],
        dataset["test_query_texts"],
        dataset["test_qrels"],
    )
    print_metrics(f"BM25 (raw {doc_noun})", bm25_metrics)
    print(
        "  Sparse vocab size: "
        f"{len(bm25_index.token_to_id):,} terms across "
        f"{len(dataset['product_ids']):,} {doc_noun}"
    )
    return bm25_metrics, bm25_index


def _run_dense_baselines(dataset: dict, emb: dict) -> tuple[dict[str, float], dict[str, float]]:
    print("\n" + "=" * 60)
    print("Step 4: Similarity baseline (SEMANTIC_SIMILARITY)")
    print("=" * 60)
    sim_metrics = evaluate_retrieval(
        dataset["test_query_ids"],
        emb["sim_test_query_embs"],
        dataset["product_ids"],
        emb["sim_product_embs"],
        dataset["test_qrels"],
    )
    print_metrics("Similarity (SEMANTIC_SIMILARITY, 768d)", sim_metrics)

    print("\n" + "=" * 60)
    print("Step 5: Retrieval baseline (query/passage)")
    print("=" * 60)
    retrieval_metrics = evaluate_retrieval(
        dataset["test_query_ids"],
        emb["test_query_embs"],
        dataset["product_ids"],
        emb["product_embs"],
        dataset["test_qrels"],
    )
    print_metrics("Retrieval (query/passage, 768d)", retrieval_metrics)
    return sim_metrics, retrieval_metrics


def _training_split(dataset: dict) -> dict:
    fit_queries, fit_qrels, val_queries, val_qrels = split_train_validation_queries(
        dataset["train_queries"], dataset["train_qrels"], VALIDATION_FRAC, seed=SEED
    )
    fit_query_ids = list(fit_queries.keys())
    val_query_ids = list(val_queries.keys())
    train_qid_to_idx = {qid: i for i, qid in enumerate(dataset["train_query_ids"])}
    return {
        "fit_queries": fit_queries,
        "fit_qrels": fit_qrels,
        "val_queries": val_queries,
        "val_qrels": val_qrels,
        "fit_query_ids": fit_query_ids,
        "val_query_ids": val_query_ids,
        "train_qid_to_idx": train_qid_to_idx,
    }


def _run_two_tower_variant(
    model_variant: str,
    train_query_embs: np.ndarray,
    test_query_embs: np.ndarray,
    product_embs: np.ndarray,
    dataset: dict,
    split_data: dict,
    reuse_checkpoint: bool = False,
    params_dir=None,
):
    from pathlib import Path
    fit_query_embs = train_query_embs[
        [split_data["train_qid_to_idx"][qid] for qid in split_data["fit_query_ids"]]
    ]
    val_query_embs = train_query_embs[
        [split_data["train_qid_to_idx"][qid] for qid in split_data["val_query_ids"]]
    ]

    if reuse_checkpoint:
        params, checkpoint = load_checkpoint(model_variant, params_dir=params_dir)
        print(f"Using existing {model_variant} checkpoint: {checkpoint.name}")
        val_product_embs = apply_tower(params, product_embs, "doc")
        val_query_proj = apply_tower(params, val_query_embs, "query")
        val_metrics = evaluate_retrieval(
            split_data["val_query_ids"],
            val_query_proj,
            dataset["product_ids"],
            val_product_embs,
            split_data["val_qrels"],
        )
    else:
        train_q_aligned, train_d_aligned, train_group_ids = align_training_pairs(
            split_data["fit_qrels"], split_data["fit_query_ids"], fit_query_embs,
            dataset["product_ids"], product_embs,
        )
        from tt_model.train import checkpoint_path as _ckpt_path
        save_path = _ckpt_path(model_variant, params_dir=params_dir) if params_dir else None
        state, val_metrics = train(
            train_q_aligned,
            train_d_aligned,
            train_group_ids,
            split_data["val_query_ids"],
            val_query_embs,
            split_data["val_qrels"],
            dataset["product_ids"],
            product_embs,
            model_variant=model_variant,
            save_path=save_path,
        )
        params = state.params

    tt_product_embs = apply_tower(params, product_embs, "doc")
    tt_query_embs = apply_tower(params, test_query_embs, "query")
    tt_metrics = evaluate_retrieval(
        dataset["test_query_ids"], tt_query_embs, dataset["product_ids"], tt_product_embs, dataset["test_qrels"]
    )
    return val_metrics, tt_metrics, tt_product_embs, tt_query_embs


def run(
    max_docs: int | None = None,
    deploy_vs2: bool = False,
    deploy_vs2_target: str | None = None,
    embeddings: dict[str, str] | None = None,
    stage: str = "full",
    reuse_checkpoints: bool = False,
    dataset_name: str = "esci",
):
    config = get_dataset_config(dataset_name)
    colls = collection_names(dataset_name)
    pdir = model_params_dir(dataset_name)
    dataset = _load_dataset(config, max_docs)

    if deploy_vs2 and deploy_vs2_target:
        raise ValueError("Use either deploy_vs2 or deploy_vs2_target, not both")

    if stage == "umap":
        print("\n" + "=" * 60)
        print("UMAP: loading product embeddings")
        print("=" * 60)
        if not embeddings or "sim_products" not in embeddings or "products" not in embeddings:
            raise ValueError(
                "--stage umap requires --embedding sim_products=<blob> --embedding products=<blob>"
            )
        sim_ids, sim_product_embs, _ = load_embeddings(embeddings["sim_products"])
        sim_product_embs = _reorder_embeddings(dataset["product_ids"], sim_ids, sim_product_embs)
        ret_ids, ret_product_embs, _ = load_embeddings(embeddings["products"])
        ret_product_embs = _reorder_embeddings(dataset["product_ids"], ret_ids, ret_product_embs)

        sim_params, _ = load_checkpoint("similarity", params_dir=pdir)
        ret_params, _ = load_checkpoint("retrieval", params_dir=pdir)
        from tt_model.umap_coords import precompute_all as umap_precompute
        from tt_model.config import umap_dir as _umap_dir

        umap_precompute(
            sim_product_embs,
            ret_product_embs,
            sim_params,
            ret_params,
            dataset["product_ids"],
            umap_dir=_umap_dir(dataset_name),
        )

        print("\n" + "=" * 60)
        print("Cluster labels")
        print("=" * 60)
        from tt_model.cluster_labels import precompute_cluster_labels

        precompute_cluster_labels(
            dataset["product_ids"],
            [dataset["products"][pid] for pid in dataset["product_ids"]],
            config=config,
            output_dir=_umap_dir(dataset_name),
        )
        return

    bm25_index = None
    if stage == "bm25":
        if deploy_vs2_target == "bm25":
            bm25_index = _build_bm25_index(dataset)
            print("\n" + "=" * 60)
            print("Step 2: BM25 sparse collection build")
            print("=" * 60)
            print(
                "  Sparse vocab size: "
                f"{len(bm25_index.token_to_id):,} terms across "
                f"{len(dataset['product_ids']):,} {config.doc_noun}"
            )
        else:
            _, bm25_index = _run_bm25(dataset, doc_noun=config.doc_noun)
        if deploy_vs2_target == "bm25":
            from tt_model.vs2 import VS2Manager, deploy_single_collection

            vs2 = VS2Manager()
            deploy_single_collection(
                vs2,
                "bm25",
                dataset["product_ids"],
                dataset["product_texts"],
                bm25_index=bm25_index,
                collections=colls,
            )
        return

    needs_embeddings = stage != "bm25" or deploy_vs2_target in {
        "similarity", "retrieval", "tt-sim", "tt-ret"
    }
    emb = _prepare_embeddings(dataset, embeddings, config) if needs_embeddings else None
    bm25_index = _build_bm25_index(dataset)
    bm25_metrics, bm25_index = _run_bm25(dataset, bm25_index=bm25_index, doc_noun=config.doc_noun)

    if deploy_vs2_target == "bm25":
        from tt_model.vs2 import VS2Manager, deploy_single_collection

        vs2 = VS2Manager()
        deploy_single_collection(
            vs2,
            "bm25",
            dataset["product_ids"],
            dataset["product_texts"],
            bm25_index=bm25_index,
            collections=colls,
        )
        return

    if stage == "baselines":
        _run_dense_baselines(dataset, emb)
        if deploy_vs2_target in {"similarity", "retrieval"}:
            from tt_model.vs2 import VS2Manager, deploy_single_collection

            dense_embeddings = (
                emb["sim_product_embs"] if deploy_vs2_target == "similarity" else emb["product_embs"]
            )
            vs2 = VS2Manager()
            deploy_single_collection(
                vs2,
                deploy_vs2_target,
                dataset["product_ids"],
                dataset["product_texts"],
                dense_embeddings=dense_embeddings,
                collections=colls,
            )
        return

    sim_metrics, retrieval_metrics = _run_dense_baselines(dataset, emb)
    if deploy_vs2_target in {"similarity", "retrieval"}:
        from tt_model.vs2 import VS2Manager, deploy_single_collection

        dense_embeddings = (
            emb["sim_product_embs"] if deploy_vs2_target == "similarity" else emb["product_embs"]
        )
        vs2 = VS2Manager()
        deploy_single_collection(
            vs2,
            deploy_vs2_target,
            dataset["product_ids"],
            dataset["product_texts"],
            dense_embeddings=dense_embeddings,
            collections=colls,
        )
        return
    split_data = _training_split(dataset)

    print("\n" + "=" * 60)
    print("Step 6: Similarity two-tower")
    print("=" * 60)
    sim_val_metrics, sim_tt_metrics, sim_tt_product_embs, sim_tt_query_embs = _run_two_tower_variant(
        "similarity",
        emb["sim_train_query_embs"],
        emb["sim_test_query_embs"],
        emb["sim_product_embs"],
        dataset,
        split_data,
        reuse_checkpoint=reuse_checkpoints or stage == "eval-checkpoints",
        params_dir=pdir,
    )
    print_metrics("Similarity Two-Tower validation checkpoint", sim_val_metrics)
    print_metrics("Two-Tower on Similarity (768d)", sim_tt_metrics)
    if deploy_vs2_target == "tt-sim":
        from tt_model.vs2 import VS2Manager, deploy_single_collection

        vs2 = VS2Manager()
        deploy_single_collection(
            vs2,
            "tt-sim",
            dataset["product_ids"],
            dataset["product_texts"],
            dense_embeddings=sim_tt_product_embs,
            collections=colls,
        )
        return
    if stage == "train-sim":
        return

    print("\n" + "=" * 60)
    print("Step 7: Retrieval two-tower")
    print("=" * 60)
    ret_val_metrics, ret_tt_metrics, ret_tt_product_embs, ret_tt_query_embs = _run_two_tower_variant(
        "retrieval",
        emb["train_query_embs"],
        emb["test_query_embs"],
        emb["product_embs"],
        dataset,
        split_data,
        reuse_checkpoint=reuse_checkpoints or stage == "eval-checkpoints",
        params_dir=pdir,
    )
    print_metrics("Retrieval Two-Tower validation checkpoint", ret_val_metrics)
    print_metrics("Two-Tower on Retrieval (768d)", ret_tt_metrics)
    if deploy_vs2_target == "tt-ret":
        from tt_model.vs2 import VS2Manager, deploy_single_collection

        vs2 = VS2Manager()
        deploy_single_collection(
            vs2,
            "tt-ret",
            dataset["product_ids"],
            dataset["product_texts"],
            dense_embeddings=ret_tt_product_embs,
            collections=colls,
        )
        return
    if stage == "train-ret":
        return

    print("\n" + "=" * 60)
    print("Step 8: Comparison")
    print("=" * 60)
    print_comparison(
        {
            "BM25": bm25_metrics,
            "Similarity": sim_metrics,
            "Retrieval": retrieval_metrics,
            "TT Similarity": sim_tt_metrics,
            "TT Retrieval": ret_tt_metrics,
        },
        change_from_label="BM25",
        change_to_label="TT Retrieval",
    )

    if deploy_vs2:
        print("\n" + "=" * 60)
        print("Step 9: Vector Search 2.0 deployment")
        print("=" * 60)
        from tt_model.vs2 import VS2Manager, deploy_and_evaluate

        vs2 = VS2Manager()
        try:
            deploy_and_evaluate(
                vs2,
                dataset["product_ids"],
                dataset["product_texts"],
                bm25_index,
                emb["sim_product_embs"],
                emb["product_embs"],
                sim_tt_product_embs,
                ret_tt_product_embs,
                dataset["test_query_ids"],
                dataset["test_query_texts"],
                emb["sim_test_query_embs"],
                emb["test_query_embs"],
                sim_tt_query_embs,
                ret_tt_query_embs,
                dataset["test_qrels"],
                collections=colls,
            )
        finally:
            print("\nCleaning up VS2 resources...")
            for coll_id in colls.values():
                vs2.cleanup(coll_id)


def main():
    parser = argparse.ArgumentParser(
        description="Two-tower retrieval model benchmark"
    )
    parser.add_argument(
        "--dataset",
        choices=("esci", "msmarco"),
        default="esci",
        help="Dataset to use (default: esci)",
    )
    parser.add_argument(
        "--max-products", "--max-passages",
        type=int,
        default=None,
        dest="max_docs",
        help="Limit number of documents (default: all for ESCI, 500000 for MS MARCO)",
    )
    parser.add_argument(
        "--deploy-vs2",
        action="store_true",
        help="Deploy to Vector Search 2.0 and run online evaluation",
    )
    parser.add_argument(
        "--deploy-vs2-target",
        choices=("bm25", "similarity", "retrieval", "tt-sim", "tt-ret"),
        help="Deploy exactly one specified collection to Vector Search 2.0",
    )
    parser.add_argument(
        "--stage",
        choices=("full", "bm25", "baselines", "train-sim", "train-ret", "eval-checkpoints", "umap"),
        default="full",
        help="Run only a specific benchmark stage",
    )
    parser.add_argument(
        "--reuse-checkpoints",
        action="store_true",
        help="Reuse the latest local two-tower checkpoints instead of retraining",
    )
    parser.add_argument(
        "--embeddings",
        nargs=6,
        metavar=("SIM_PRODUCTS", "SIM_TRAIN_QUERIES", "SIM_TEST_QUERIES",
                 "PRODUCTS", "TRAIN_QUERIES", "TEST_QUERIES"),
        help="Load embeddings from GCS blob names instead of computing",
    )
    parser.add_argument(
        "--embedding",
        action="append",
        default=[],
        metavar="KEY=BLOB",
        help="Provide individual embedding blobs for partial reuse",
    )
    args = parser.parse_args()

    emb_map = None
    if args.embeddings:
        emb_map = {
            "sim_products": args.embeddings[0],
            "sim_train_queries": args.embeddings[1],
            "sim_test_queries": args.embeddings[2],
            "products": args.embeddings[3],
            "train_queries": args.embeddings[4],
            "test_queries": args.embeddings[5],
        }
    if args.embedding:
        emb_map = emb_map or {}
        for item in args.embedding:
            if "=" not in item:
                raise ValueError(f"Invalid --embedding value: {item}")
            key, value = item.split("=", 1)
            if key not in EMBEDDING_KEYS:
                raise ValueError(
                    f"Unknown embedding key '{key}'. Valid keys: {', '.join(EMBEDDING_KEYS)}"
                )
            emb_map[key] = value

    run(
        max_docs=args.max_docs,
        deploy_vs2=args.deploy_vs2,
        deploy_vs2_target=args.deploy_vs2_target,
        embeddings=emb_map,
        stage=args.stage,
        reuse_checkpoints=args.reuse_checkpoints,
        dataset_name=args.dataset,
    )
