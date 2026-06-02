import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from flax import serialization
from starlette.middleware.gzip import GZipMiddleware

from tt_model.bm25 import BM25Index
from tt_model.config import (
    COLLECTION_BM25,
    COLLECTION_BASELINE,
    COLLECTION_SIMILARITY,
    COLLECTION_TWOTOWER,
    EMBEDDING_DIM,
    UMAP_METHODS,
)
from tt_model.data import LABEL_SCORES, load_esci, query_id_for_text
from tt_model.embed import _embed_one
from tt_model.evaluate import compute_mrr, compute_ndcg, compute_recall
from tt_model.model import TwoTowerModel
from tt_model.train import apply_tower, latest_checkpoint_path
from tt_model.cluster_labels import load_cluster_labels
from tt_model.umap_coords import load_coords
from tt_model.vs2 import VS2Manager

SCORE_LABELS = {v: k for k, v in LABEL_SCORES.items()}
TOP_K = 50

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates"
)

_ctx = {}


@app.on_event("startup")
def startup():
    print("Loading startup data...")

    products, _, _, test_queries, test_qrels = load_esci()

    model = TwoTowerModel()
    dummy = np.ones((1, EMBEDDING_DIM), dtype=np.float32)
    init_params = model.init(
        __import__("jax").random.PRNGKey(0), dummy, dummy
    )
    with open(latest_checkpoint_path("similarity"), "rb") as f:
        tt_params = serialization.from_bytes(init_params, f.read())

    _ctx["products"] = products
    _ctx["product_ids"] = list(products.keys())
    _ctx["tt_params"] = tt_params
    _ctx["test_queries"] = test_queries
    _ctx["test_qrels"] = test_qrels
    _ctx["test_query_list"] = list(test_queries.values())
    _ctx["vs2"] = VS2Manager()
    _ctx["bm25"] = BM25Index(_ctx["product_ids"], list(products.values()))

    print(f"  Loaded {len(products)} products, "
          f"{len(test_queries)} test queries, VS2 client ready")

    _ctx["umap_methods"] = []
    for method in UMAP_METHODS:
        try:
            ids, x, y = load_coords(method)
            _ctx[f"umap_{method}_ids"] = ids
            _ctx[f"umap_{method}_x"] = x
            _ctx[f"umap_{method}_y"] = y
            _ctx["umap_methods"].append(method)
        except FileNotFoundError:
            pass
    if _ctx["umap_methods"]:
        print(f"  UMAP coords loaded: {', '.join(_ctx['umap_methods'])}")
    else:
        print("  No UMAP coords found (run --stage umap to generate)")

    for method in _ctx.get("umap_methods", []):
        try:
            _ctx[f"clusters_{method}"] = load_cluster_labels(method)
        except FileNotFoundError:
            _ctx[f"clusters_{method}"] = []


def _vs2_search(
    collection_id: str, query_vector: list[float],
) -> list[dict]:
    vs2 = _ctx["vs2"]
    response = vs2.search(
        collection_id, query_vector, top_k=TOP_K,
    )
    results = []
    for r in response:
        pid = r.data_object.name.split("/")[-1]
        title = ""
        if r.data_object.data and "passage_text" in r.data_object.data:
            title = r.data_object.data["passage_text"]
        if not title:
            title = _ctx["products"].get(pid, "")
        item = {"id": pid, "title": title, "score": float(r.distance)}
        results.append(item)
    return results


def _single_query_metrics(qid: str, scored: dict[str, float]) -> dict:
    qrels = _ctx["test_qrels"]
    if qid not in qrels:
        return {}
    qr = {qid: qrels[qid]}
    res = {qid: scored}
    return {
        "RR@10": compute_mrr(qr, res, 10),
        "NDCG@10": compute_ndcg(qr, res, 10),
        "Recall@10": compute_recall(qr, res, 10),
    }


def _bm25_search(query: str) -> list[dict]:
    query_weights = _ctx["bm25"].query_term_weights(query)
    response = _ctx["vs2"].search_sparse(
        COLLECTION_BM25,
        list(query_weights.keys()),
        list(query_weights.values()),
        top_k=TOP_K,
    )
    results = []
    for r in response:
        pid = r.data_object.name.split("/")[-1]
        title = ""
        if r.data_object.data and "passage_text" in r.data_object.data:
            title = r.data_object.data["passage_text"]
        if not title:
            title = _ctx["products"].get(pid, "")
        results.append({"id": pid, "title": title, "score": float(r.distance)})
    return results


@app.get("/next_query")
def next_query():
    return {"query": random.choice(_ctx["test_query_list"])}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    default_query = random.choice(_ctx["test_query_list"])
    return templates.TemplateResponse(
        request, "search.html",
        {
            "default_query": default_query,
            "methods": _ctx.get("umap_methods", []),
            "n_products": len(_ctx["products"]),
        },
    )


@app.post("/search")
def search(request_body: dict):
    query = request_body["query"]
    qid = query_id_for_text(query)
    qrels = _ctx["test_qrels"].get(qid, {})

    try:
        with ThreadPoolExecutor(max_workers=2) as emb_pool:
            f_sim_emb = emb_pool.submit(
                _embed_one, query, "SEMANTIC_SIMILARITY"
            )
            f_ret_emb = emb_pool.submit(
                _embed_one, f"task: search result | query: {query}"
            )
        sim_emb = np.array(f_sim_emb.result(), dtype=np.float32)
        ret_emb = np.array(f_ret_emb.result(), dtype=np.float32)
        tt_emb = apply_tower(
            _ctx["tt_params"], sim_emb.reshape(1, -1), "query"
        ).squeeze()

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_bm25 = executor.submit(_bm25_search, query)
            f_sim = executor.submit(
                _vs2_search, COLLECTION_SIMILARITY, sim_emb.tolist(),
            )
            f_ret = executor.submit(
                _vs2_search, COLLECTION_BASELINE, ret_emb.tolist(),
            )
            f_tt = executor.submit(
                _vs2_search, COLLECTION_TWOTOWER, tt_emb.tolist(),
            )

        def format_results(hits: list[dict]):
            scored = {h["id"]: h["score"] for h in hits}
            items = []
            for rank, h in enumerate(hits, 1):
                pid = h["id"]
                rel = qrels.get(pid)
                label = SCORE_LABELS.get(rel) if rel is not None else None
                items.append({
                    "rank": rank,
                    "product_id": pid,
                    "title": h["title"],
                    "score": round(h["score"], 4),
                    "relevance": label,
                    "relevance_score": rel,
                })
            return items, scored

        bm25_hits = f_bm25.result()
        sim_hits = f_sim.result()
        ret_hits = f_ret.result()
        tt_hits = f_tt.result()

        bm25_items, bm25_scored = format_results(bm25_hits)
        sim_items, sim_scored = format_results(sim_hits)
        ret_items, ret_scored = format_results(ret_hits)
        tt_items, tt_scored = format_results(tt_hits)

    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e)},
        )

    is_test_query = qid in _ctx["test_qrels"]

    return {
        "query": query,
        "is_test_query": is_test_query,
        "dataset": f"Amazon ESCI — {len(_ctx['products']):,} products, "
                   f"{len(_ctx['test_queries']):,} test queries",
        "columns": [
            {
                "label": "BM25",
                "description": "VS2 sparse title-only baseline",
                "results": bm25_items,
                "metrics": _single_query_metrics(qid, bm25_scored) if is_test_query else {},
            },
            {
                "label": "Similarity",
                "description": "SEMANTIC_SIMILARITY task type",
                "results": sim_items,
                "metrics": _single_query_metrics(qid, sim_scored) if is_test_query else {},
            },
            {
                "label": "Two-Tower",
                "description": "Learned projection on similarity embeddings",
                "results": tt_items,
                "metrics": _single_query_metrics(qid, tt_scored) if is_test_query else {},
            },
            {
                "label": "Retrieval",
                "description": "Search query task type",
                "results": ret_items,
                "metrics": _single_query_metrics(qid, ret_scored) if is_test_query else {},
            },
        ],
    }


@app.get("/viz/coords/{method}")
def viz_coords(method: str):
    key = f"umap_{method}_x"
    if key not in _ctx:
        return JSONResponse(status_code=404, content={"error": f"No UMAP data for {method}"})
    x = _ctx[f"umap_{method}_x"]
    y = _ctx[f"umap_{method}_y"]
    n = np.uint32(len(x))
    buf = n.tobytes() + x.tobytes() + y.tobytes()
    return Response(content=buf, media_type="application/octet-stream")


@app.get("/viz/products")
def viz_products():
    ids = _ctx["product_ids"]
    titles = [_ctx["products"][pid] for pid in ids]
    return {"ids": ids, "titles": titles}


@app.get("/viz/clusters/{method}")
def viz_clusters(method: str):
    key = f"clusters_{method}"
    if key not in _ctx:
        return JSONResponse(status_code=404, content={"error": f"No cluster data for {method}"})
    return _ctx[key]


@app.post("/viz/search")
def viz_search(request_body: dict):
    query = request_body["query"]
    qid = query_id_for_text(query)
    qrels = _ctx["test_qrels"].get(qid, {})
    is_test_query = qid in _ctx["test_qrels"]

    try:
        with ThreadPoolExecutor(max_workers=2) as emb_pool:
            f_sim_emb = emb_pool.submit(_embed_one, query, "SEMANTIC_SIMILARITY")
            f_ret_emb = emb_pool.submit(
                _embed_one, f"task: search result | query: {query}"
            )
        sim_emb = np.array(f_sim_emb.result(), dtype=np.float32)
        ret_emb = np.array(f_ret_emb.result(), dtype=np.float32)
        tt_emb = apply_tower(
            _ctx["tt_params"], sim_emb.reshape(1, -1), "query"
        ).squeeze()

        with ThreadPoolExecutor(max_workers=3) as executor:
            f_sim = executor.submit(
                _vs2_search, COLLECTION_SIMILARITY, sim_emb.tolist(),
            )
            f_ret = executor.submit(
                _vs2_search, COLLECTION_BASELINE, ret_emb.tolist(),
            )
            f_tt = executor.submit(
                _vs2_search, COLLECTION_TWOTOWER, tt_emb.tolist(),
            )

        sim_ids = [r["id"] for r in f_sim.result()]
        ret_ids = [r["id"] for r in f_ret.result()]
        tt_sim_ids = [r["id"] for r in f_tt.result()]
        results = {
            "similarity": sim_ids,
            "retrieval": ret_ids,
            "tt_similarity": tt_sim_ids,
            "tt_retrieval": ret_ids,
        }

        relevance = {}
        if is_test_query:
            for method_key, id_list in results.items():
                relevance[method_key] = {
                    pid: SCORE_LABELS.get(qrels.get(pid))
                    for pid in id_list
                }
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

    return {
        "query": query,
        "results": results,
        "is_test_query": is_test_query,
        "relevance": relevance,
    }
