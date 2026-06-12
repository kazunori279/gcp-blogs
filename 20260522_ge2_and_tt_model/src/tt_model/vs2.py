import json
import time
from pathlib import Path

import google.auth
import google.auth.transport.requests
import numpy as np
import requests
from google.api_core.exceptions import AlreadyExists, ResourceExhausted
from google.cloud import vectorsearch_v1beta
from tqdm import tqdm

from tt_model.config import (
    COLLECTION_BM25,
    COLLECTION_BASELINE,
    COLLECTION_SIMILARITY,
    COLLECTION_TWOTOWER_RETRIEVAL,
    COLLECTION_TWOTOWER_SIMILARITY,
    EMBEDDING_DIM,
    LOCATION,
    OUTPUT_DIM,
    PROJECT_ID,
    SPARSE_BATCH_SIZE,
    SPARSE_INSERT_MAX_RETRIES,
    SPARSE_VECTOR_FIELD,
    VECTOR_FIELD,
)

RERANKER_MODEL = "semantic-ranker-fast@latest"


class VS2Manager:
    def __init__(
        self, project_id: str = PROJECT_ID, location: str = LOCATION
    ):
        self.project_id = project_id
        self.location = location
        self.vs_client = vectorsearch_v1beta.VectorSearchServiceClient()
        self.data_client = vectorsearch_v1beta.DataObjectServiceClient()
        self.search_client = (
            vectorsearch_v1beta.DataObjectSearchServiceClient()
        )
        self.parent = f"projects/{project_id}/locations/{location}"
        self.resume_dir = Path("data/vs2_resume")
        self.resume_dir.mkdir(parents=True, exist_ok=True)

    def create_collection(self, collection_id: str, dim: int):
        collection = vectorsearch_v1beta.Collection(
            data_schema={
                "type": "object",
                "properties": {"passage_text": {"type": "string"}},
            },
            vector_schema={
                VECTOR_FIELD: {"dense_vector": {"dimensions": dim}}
            },
        )
        request = vectorsearch_v1beta.CreateCollectionRequest(
            parent=self.parent,
            collection_id=collection_id,
            collection=collection,
        )
        print(f"  Creating collection {collection_id}...")
        try:
            op = self.vs_client.create_collection(request=request)
            op.result()
            print(f"  Collection {collection_id} ready")
        except AlreadyExists:
            print(f"  Collection {collection_id} already exists; reusing it")

    def create_sparse_collection(
        self, collection_id: str, vector_field: str = SPARSE_VECTOR_FIELD
    ):
        collection = vectorsearch_v1beta.Collection(
            data_schema={
                "type": "object",
                "properties": {"passage_text": {"type": "string"}},
            },
            vector_schema={
                vector_field: {"sparse_vector": {}}
            },
        )
        request = vectorsearch_v1beta.CreateCollectionRequest(
            parent=self.parent,
            collection_id=collection_id,
            collection=collection,
        )
        print(f"  Creating sparse collection {collection_id}...")
        try:
            op = self.vs_client.create_collection(request=request)
            op.result()
            print(f"  Collection {collection_id} ready")
        except AlreadyExists:
            print(f"  Collection {collection_id} already exists; reusing it")

    def _resume_state_path(self, collection_id: str) -> Path:
        return self.resume_dir / f"{collection_id}.json"

    def _load_resume_state(self, collection_id: str) -> dict:
        path = self._resume_state_path(collection_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _save_resume_state(self, collection_id: str, state: dict):
        self._resume_state_path(collection_id).write_text(
            json.dumps(state, indent=2, sort_keys=True)
        )

    def _clear_resume_state(self, collection_id: str):
        path = self._resume_state_path(collection_id)
        if path.exists():
            path.unlink()

    def _batch_create_with_retry(self, request, batch_label: str):
        for attempt in range(SPARSE_INSERT_MAX_RETRIES):
            try:
                return self.data_client.batch_create_data_objects(request)
            except AlreadyExists:
                print(f"    {batch_label} already exists; skipping")
                return None
            except ResourceExhausted:
                if attempt == SPARSE_INSERT_MAX_RETRIES - 1:
                    raise
                sleep_s = min(60, 2 ** attempt)
                print(
                    f"    Resource exhausted on {batch_label}; "
                    f"retrying in {sleep_s}s ({attempt + 1}/{SPARSE_INSERT_MAX_RETRIES})"
                )
                time.sleep(sleep_s)

    def batch_insert(
        self,
        collection_id: str,
        ids: list[str],
        embeddings: np.ndarray,
        texts: list[str],
    ):
        collection_path = f"{self.parent}/collections/{collection_id}"
        print(f"  Inserting {len(ids)} objects into {collection_id}...")

        for start in tqdm(range(0, len(ids), 250)):
            end = min(start + 250, len(ids))
            batch = [
                {
                    "data_object_id": ids[i],
                    "data_object": {
                        "data": {"passage_text": texts[i][:500]},
                        "vectors": {
                            VECTOR_FIELD: {
                                "dense": {
                                    "values": embeddings[i].tolist()
                                }
                            }
                        },
                    },
                }
                for i in range(start, end)
            ]
            request = vectorsearch_v1beta.BatchCreateDataObjectsRequest(
                parent=collection_path, requests=batch
            )
            self._batch_create_with_retry(
                request, f"batch {start // 250 + 1}"
            )

    def create_index(self, collection_id: str, index_id: str = "ann-index"):
        request = vectorsearch_v1beta.CreateIndexRequest(
            parent=f"{self.parent}/collections/{collection_id}",
            index_id=index_id,
            index={
                "index_field": VECTOR_FIELD,
                "store_fields": ["passage_text"],
            },
        )
        op = self.vs_client.create_index(request)
        print(f"  Index creation started for {collection_id} (async)")
        return op

    def create_sparse_index(
        self,
        collection_id: str,
        vector_field: str = SPARSE_VECTOR_FIELD,
        index_id: str = "ann-index",
    ):
        request = vectorsearch_v1beta.CreateIndexRequest(
            parent=f"{self.parent}/collections/{collection_id}",
            index_id=index_id,
            index={
                "index_field": vector_field,
                "store_fields": ["passage_text"],
            },
        )
        op = self.vs_client.create_index(request)
        print(f"  Sparse index creation started for {collection_id} (async)")
        return op

    def search(
        self, collection_id: str, query_vector: list[float], top_k: int = 100,
        return_vectors: bool = False,
    ):
        output_fields = vectorsearch_v1beta.OutputFields(
            data_fields=["passage_text"],
        )
        if return_vectors:
            output_fields.vector_fields = [VECTOR_FIELD]
        request = vectorsearch_v1beta.SearchDataObjectsRequest(
            parent=f"{self.parent}/collections/{collection_id}",
            vector_search=vectorsearch_v1beta.VectorSearch(
                search_field=VECTOR_FIELD,
                vector={"values": query_vector},
                top_k=top_k,
                output_fields=output_fields,
            ),
        )
        return self.search_client.search_data_objects(request)

    def batch_insert_sparse(
        self,
        collection_id: str,
        ids: list[str],
        sparse_vectors: list[dict],
        texts: list[str],
        vector_field: str = SPARSE_VECTOR_FIELD,
        batch_size: int = SPARSE_BATCH_SIZE,
    ):
        collection_path = f"{self.parent}/collections/{collection_id}"
        print(f"  Inserting {len(ids)} sparse objects into {collection_id}...")
        resume_state = self._load_resume_state(collection_id)
        resume_next_start = int(resume_state.get("next_start", 0))
        if resume_next_start:
            print(f"  Resuming sparse insert from offset {resume_next_start}")

        batch_starts = range(resume_next_start, len(ids), batch_size)
        for start in tqdm(batch_starts, total=max(0, (len(ids) - resume_next_start + batch_size - 1) // batch_size)):
            end = min(start + batch_size, len(ids))
            batch = [
                {
                    "data_object_id": ids[i],
                    "data_object": {
                        "data": {"passage_text": texts[i][:500]},
                        "vectors": {
                            vector_field: {
                                "sparse": {
                                    "indices": sparse_vectors[i]["indices"],
                                    "values": sparse_vectors[i]["values"],
                                }
                            }
                        },
                    },
                }
                for i in range(start, end)
            ]
            request = vectorsearch_v1beta.BatchCreateDataObjectsRequest(
                parent=collection_path, requests=batch
            )
            self._batch_create_with_retry(
                request,
                batch_label=f"{collection_id}[{start}:{end}]",
            )
            self._save_resume_state(
                collection_id,
                {
                    "collection_id": collection_id,
                    "next_start": end,
                    "total": len(ids),
                    "batch_size": batch_size,
                },
            )
        self._clear_resume_state(collection_id)

    def search_sparse(
        self,
        collection_id: str,
        sparse_indices: list[int],
        sparse_values: list[float],
        top_k: int = 100,
        vector_field: str = SPARSE_VECTOR_FIELD,
    ):
        if not sparse_indices:
            return []
        request = vectorsearch_v1beta.SearchDataObjectsRequest(
            parent=f"{self.parent}/collections/{collection_id}",
            vector_search=vectorsearch_v1beta.VectorSearch(
                search_field=vector_field,
                sparse_vector={
                    "indices": sparse_indices,
                    "values": sparse_values,
                },
                top_k=top_k,
                output_fields=vectorsearch_v1beta.OutputFields(
                    data_fields=["passage_text"]
                ),
            ),
        )
        return self.search_client.search_data_objects(request)

    def search_with_reranker(
        self,
        collection_id: str,
        query_text: str,
        query_vector: list[float],
        top_k: int = 100,
        rerank_top_n: int = 200,
    ) -> list[dict]:
        """Batch search with vector + text search, fused by RRF + vertex reranker.

        Uses the REST API since vertex_ranker is not yet in the Python SDK.
        """
        creds, _ = google.auth.default()
        creds.refresh(google.auth.transport.requests.Request())

        url = (
            f"https://{self.location}-vectorsearch.googleapis.com/v1beta/"
            f"{self.parent}/collections/{collection_id}"
            f"/dataObjects:batchSearch"
        )

        body = {
            "searches": [
                {
                    "vectorSearch": {
                        "searchField": VECTOR_FIELD,
                        "vector": {"values": query_vector},
                        "topK": rerank_top_n,
                    }
                },
                {
                    "textSearch": {
                        "searchText": query_text,
                        "dataFieldNames": ["passage_text"],
                        "topK": rerank_top_n,
                    }
                },
            ],
            "combine": {
                "topK": top_k,
                "ranker": {
                    "rrf": {"weights": [1.0, 1.0]},
                    "vertexRanker": {
                        "model": RERANKER_MODEL,
                        "topN": rerank_top_n,
                        "textRecordSpec": {
                            "query": query_text,
                            "titleTemplate": "{passage_text}",
                            "contentTemplate": "{passage_text}",
                        },
                    },
                },
            },
        }

        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for search_resp in data.get("results", []):
            for sr in search_resp.get("results", []):
                obj_name = sr.get("dataObject", {}).get("name", "")
                pid = obj_name.split("/")[-1]
                score = sr.get("score", 0.0)
                results.append({"id": pid, "score": score})
        return results

    def cleanup(self, collection_id: str, index_id: str = "ann-index"):
        print(f"  Cleaning up {collection_id}...")
        try:
            request = vectorsearch_v1beta.DeleteIndexRequest(
                name=f"{self.parent}/collections/{collection_id}/indexes/{index_id}",
            )
            op = self.vs_client.delete_index(request)
            op.result()
        except Exception:
            pass

        try:
            request = vectorsearch_v1beta.DeleteCollectionRequest(
                name=f"{self.parent}/collections/{collection_id}",
            )
            op = self.vs_client.delete_collection(request)
            op.result()
        except Exception:
            pass
        print(f"  {collection_id} cleaned up")


def deploy_and_evaluate(
    vs2: VS2Manager,
    passage_ids: list[str],
    passage_texts: list[str],
    bm25_index,
    sim_embs: np.ndarray,
    baseline_embs: np.ndarray,
    tt_similarity_embs: np.ndarray,
    tt_retrieval_embs: np.ndarray,
    query_ids: list[str],
    query_texts: list[str],
    sim_query_embs: np.ndarray,
    baseline_query_embs: np.ndarray,
    tt_similarity_query_embs: np.ndarray,
    tt_retrieval_query_embs: np.ndarray,
    qrels: dict,
    collections: dict[str, str] | None = None,
):
    """Deploy all collections to VS2 and run evaluation."""
    from tt_model.evaluate import (
        compute_mrr,
        compute_ndcg,
        compute_recall,
        print_metrics,
    )

    c = collections or {
        "bm25": COLLECTION_BM25,
        "similarity": COLLECTION_SIMILARITY,
        "baseline": COLLECTION_BASELINE,
        "twotower_similarity": COLLECTION_TWOTOWER_SIMILARITY,
        "twotower_retrieval": COLLECTION_TWOTOWER_RETRIEVAL,
    }

    # Create collections
    vs2.create_sparse_collection(c["bm25"])
    vs2.create_collection(c["similarity"], EMBEDDING_DIM)
    vs2.create_collection(c["baseline"], EMBEDDING_DIM)
    vs2.create_collection(c["twotower_similarity"], OUTPUT_DIM)
    vs2.create_collection(c["twotower_retrieval"], OUTPUT_DIM)

    # Insert data
    sparse_vectors = [
        bm25_index.document_sparse_vector(i, weighting="bm25_tf").to_vs2()["sparse"]
        for i in range(len(passage_ids))
    ]
    vs2.batch_insert_sparse(c["bm25"], passage_ids, sparse_vectors, passage_texts)
    vs2.batch_insert(c["similarity"], passage_ids, sim_embs, passage_texts)
    vs2.batch_insert(c["baseline"], passage_ids, baseline_embs, passage_texts)
    vs2.batch_insert(
        c["twotower_similarity"], passage_ids, tt_similarity_embs, passage_texts
    )
    vs2.batch_insert(
        c["twotower_retrieval"], passage_ids, tt_retrieval_embs, passage_texts
    )

    # Create indexes (async)
    bm25_op = vs2.create_sparse_index(c["bm25"])
    sim_op = vs2.create_index(c["similarity"])
    baseline_op = vs2.create_index(c["baseline"])
    tt_similarity_op = vs2.create_index(c["twotower_similarity"])
    tt_retrieval_op = vs2.create_index(c["twotower_retrieval"])

    print("\n  Waiting for indexes to build (this may take ~60 minutes)...", flush=True)
    index_timeout = 3600
    bm25_op.result(timeout=index_timeout)
    print("  BM25 sparse index ready", flush=True)
    sim_op.result(timeout=index_timeout)
    print("  Similarity index ready", flush=True)
    baseline_op.result(timeout=index_timeout)
    print("  Baseline index ready", flush=True)
    tt_similarity_op.result(timeout=index_timeout)
    print("  Similarity two-tower index ready", flush=True)
    tt_retrieval_op.result(timeout=index_timeout)
    print("  Retrieval two-tower index ready", flush=True)

    all_metrics = {}

    label = "VS2 BM25"
    results = {}
    print(f"\n  Searching {label}...")
    for i, qid in enumerate(tqdm(query_ids)):
        query_weights = bm25_index.query_term_weights(query_texts[i])
        response = vs2.search_sparse(
            c["bm25"],
            list(query_weights.keys()),
            list(query_weights.values()),
        )
        results[qid] = {}
        for result in response:
            pid = result.data_object.name.split("/")[-1]
            results[qid][pid] = float(result.distance)

    metrics = {
        "MRR@10": compute_mrr(qrels, results, 10),
        "NDCG@10": compute_ndcg(qrels, results, 10),
        "Recall@10": compute_recall(qrels, results, 10),
        "Recall@100": compute_recall(qrels, results, 100),
    }
    all_metrics[label] = metrics
    print_metrics(label, metrics)

    # Evaluate via VS2 search across all collections
    for label, collection_id, q_embs in [
        ("VS2 Similarity", c["similarity"], sim_query_embs),
        ("VS2 Retrieval", c["baseline"], baseline_query_embs),
        (
            "VS2 TT Similarity",
            c["twotower_similarity"],
            tt_similarity_query_embs,
        ),
        (
            "VS2 TT Retrieval",
            c["twotower_retrieval"],
            tt_retrieval_query_embs,
        ),
    ]:
        results = {}
        print(f"\n  Searching {label}...")
        for i, qid in enumerate(tqdm(query_ids)):
            response = vs2.search(collection_id, q_embs[i].tolist())
            results[qid] = {}
            for result in response:
                pid = result.data_object.name.split("/")[-1]
                results[qid][pid] = float(result.distance)

        metrics = {
            "MRR@10": compute_mrr(qrels, results, 10),
            "NDCG@10": compute_ndcg(qrels, results, 10),
            "Recall@10": compute_recall(qrels, results, 10),
            "Recall@100": compute_recall(qrels, results, 100),
        }
        all_metrics[label] = metrics
        print_metrics(label, metrics)

    # Evaluate with reranker on baseline collection
    label = "VS2 Retrieval + Reranker"
    results = {}
    print(f"\n  Searching {label}...")
    for i, qid in enumerate(tqdm(query_ids)):
        reranked = vs2.search_with_reranker(
            c["baseline"],
            query_text=query_texts[i],
            query_vector=baseline_query_embs[i].tolist(),
        )
        results[qid] = {r["id"]: r["score"] for r in reranked}

    metrics = {
        "MRR@10": compute_mrr(qrels, results, 10),
        "NDCG@10": compute_ndcg(qrels, results, 10),
        "Recall@10": compute_recall(qrels, results, 10),
        "Recall@100": compute_recall(qrels, results, 100),
    }
    all_metrics[label] = metrics
    print_metrics(label, metrics)

    # Evaluate with reranker on similarity two-tower collection
    label = "VS2 TT Similarity + Reranker"
    results = {}
    print(f"\n  Searching {label}...")
    for i, qid in enumerate(tqdm(query_ids)):
        reranked = vs2.search_with_reranker(
            c["twotower_similarity"],
            query_text=query_texts[i],
            query_vector=tt_similarity_query_embs[i].tolist(),
        )
        results[qid] = {r["id"]: r["score"] for r in reranked}

    metrics = {
        "MRR@10": compute_mrr(qrels, results, 10),
        "NDCG@10": compute_ndcg(qrels, results, 10),
        "Recall@10": compute_recall(qrels, results, 10),
        "Recall@100": compute_recall(qrels, results, 100),
    }
    all_metrics[label] = metrics
    print_metrics(label, metrics)

    # Evaluate with reranker on retrieval two-tower collection
    label = "VS2 TT Retrieval + Reranker"
    results = {}
    print(f"\n  Searching {label}...")
    for i, qid in enumerate(tqdm(query_ids)):
        reranked = vs2.search_with_reranker(
            c["twotower_retrieval"],
            query_text=query_texts[i],
            query_vector=tt_retrieval_query_embs[i].tolist(),
        )
        results[qid] = {r["id"]: r["score"] for r in reranked}

    metrics = {
        "MRR@10": compute_mrr(qrels, results, 10),
        "NDCG@10": compute_ndcg(qrels, results, 10),
        "Recall@10": compute_recall(qrels, results, 10),
        "Recall@100": compute_recall(qrels, results, 100),
    }
    all_metrics[label] = metrics
    print_metrics(label, metrics)

    # Print full comparison
    from tt_model.evaluate import print_comparison
    print_comparison(all_metrics)


def deploy_single_collection(
    vs2: VS2Manager,
    target: str,
    passage_ids: list[str],
    passage_texts: list[str],
    bm25_index=None,
    dense_embeddings: np.ndarray | None = None,
    collections: dict[str, str] | None = None,
):
    """Deploy a single collection without touching the others."""
    c = collections or {
        "bm25": COLLECTION_BM25,
        "similarity": COLLECTION_SIMILARITY,
        "baseline": COLLECTION_BASELINE,
        "twotower_similarity": COLLECTION_TWOTOWER_SIMILARITY,
        "twotower_retrieval": COLLECTION_TWOTOWER_RETRIEVAL,
    }

    if target == "bm25":
        if bm25_index is None:
            raise ValueError("bm25_index is required to deploy the BM25 sparse collection")
        coll_id = c["bm25"]
        vs2.create_sparse_collection(coll_id)
        sparse_vectors = [
            bm25_index.document_sparse_vector(i, weighting="bm25_tf").to_vs2()["sparse"]
            for i in range(len(passage_ids))
        ]
        vs2.batch_insert_sparse(coll_id, passage_ids, sparse_vectors, passage_texts)
        op = vs2.create_sparse_index(coll_id)
        print("\n  Waiting for BM25 sparse index to build...")
        op.result()
        print("  BM25 sparse index ready")
        return coll_id

    dense_targets = {
        "similarity": (c["similarity"], EMBEDDING_DIM),
        "retrieval": (c["baseline"], EMBEDDING_DIM),
        "tt-sim": (c["twotower_similarity"], OUTPUT_DIM),
        "tt-ret": (c["twotower_retrieval"], OUTPUT_DIM),
    }
    if target not in dense_targets:
        raise ValueError(f"Unknown deploy target: {target}")
    if dense_embeddings is None:
        raise ValueError(f"dense_embeddings are required to deploy target '{target}'")

    collection_id, dim = dense_targets[target]
    vs2.create_collection(collection_id, dim)
    vs2.batch_insert(collection_id, passage_ids, dense_embeddings, passage_texts)
    op = vs2.create_index(collection_id)
    print(f"\n  Waiting for {target} index to build...")
    op.result()
    print(f"  {target} index ready")
    return collection_id
