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
    EMBEDDING_DIM,
    UMAP_METHODS,
    collection_names,
    model_params_dir,
    umap_dir,
)
from tt_model.data import (
    ESCI_CONFIG,
    MSMARCO_CONFIG,
    DatasetConfig,
    load_dataset_by_config,
    query_id_for_text,
)
from tt_model.embed import _embed_one
from tt_model.evaluate import compute_mrr, compute_ndcg, compute_recall
from tt_model.model import TwoTowerModel
from tt_model.train import apply_tower, latest_checkpoint_path
from tt_model.cluster_labels import load_cluster_labels
from tt_model.umap_coords import load_coords
from tt_model.vs2 import VS2Manager

TOP_K = 50

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
templates = Jinja2Templates(
    directory=Path(__file__).parent / "templates"
)

_datasets: dict[str, dict] = {}
_shared: dict = {}


def _load_tt_params(ds_name: str):
    model = TwoTowerModel()
    dummy = np.ones((1, EMBEDDING_DIM), dtype=np.float32)
    init_params = model.init(
        __import__("jax").random.PRNGKey(0), dummy, dummy
    )
    pdir = model_params_dir(ds_name)
    with open(latest_checkpoint_path("similarity", params_dir=pdir), "rb") as f:
        return serialization.from_bytes(init_params, f.read())


@app.on_event("startup")
def startup():
    print("Loading startup data...")
    _shared["vs2"] = VS2Manager()

    for ds_name, config in [("esci", ESCI_CONFIG), ("msmarco", MSMARCO_CONFIG)]:
        try:
            docs, _, _, test_queries, test_qrels = load_dataset_by_config(config)
            tt_params = _load_tt_params(ds_name)
            colls = collection_names(ds_name)
            score_labels = config.score_to_label

            ctx = {
                "config": config,
                "products": docs,
                "product_ids": list(docs.keys()),
                "tt_params": tt_params,
                "test_queries": test_queries,
                "test_qrels": test_qrels,
                "test_query_list": list(test_queries.values()),
                "bm25": BM25Index(list(docs.keys()), list(docs.values())),
                "collections": colls,
                "score_labels": score_labels,
                "umap_methods": [],
            }

            udir = umap_dir(ds_name)
            for method in UMAP_METHODS:
                try:
                    ids, x, y = load_coords(method, umap_dir=udir)
                    ctx[f"umap_{method}_ids"] = ids
                    ctx[f"umap_{method}_x"] = x
                    ctx[f"umap_{method}_y"] = y
                    ctx["umap_methods"].append(method)
                except FileNotFoundError:
                    pass

            for method in ctx["umap_methods"]:
                try:
                    ctx[f"clusters_{method}"] = load_cluster_labels(method, umap_dir=udir)
                except FileNotFoundError:
                    ctx[f"clusters_{method}"] = []

            _datasets[ds_name] = ctx
            print(f"  Loaded {ds_name}: {len(docs):,} {config.doc_noun}, "
                  f"{len(test_queries):,} test queries")
        except Exception as e:
            print(f"  Skipping {ds_name}: {e}")

    if not _datasets:
        raise RuntimeError("No datasets loaded successfully")

    print(f"  Datasets ready: {', '.join(_datasets)}")


def _get_ctx(ds_name: str | None = None) -> tuple[str, dict]:
    if ds_name and ds_name in _datasets:
        return ds_name, _datasets[ds_name]
    default = "esci" if "esci" in _datasets else next(iter(_datasets))
    return default, _datasets[default]


def _vs2_search(
    ctx: dict, collection_id: str, query_vector: list[float],
) -> list[dict]:
    vs2 = _shared["vs2"]
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
            title = ctx["products"].get(pid, "")
        results.append({"id": pid, "title": title, "score": float(r.distance)})
    return results


def _single_query_metrics(ctx: dict, qid: str, scored: dict[str, float]) -> dict:
    qrels = ctx["test_qrels"]
    if qid not in qrels:
        return {}
    qr = {qid: qrels[qid]}
    res = {qid: scored}
    return {
        "RR@10": compute_mrr(qr, res, 10),
        "NDCG@10": compute_ndcg(qr, res, 10),
        "Recall@10": compute_recall(qr, res, 10),
    }


def _bm25_search(ctx: dict, query: str) -> list[dict]:
    query_weights = ctx["bm25"].query_term_weights(query)
    response = _shared["vs2"].search_sparse(
        ctx["collections"]["bm25"],
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
            title = ctx["products"].get(pid, "")
        results.append({"id": pid, "title": title, "score": float(r.distance)})
    return results


@app.get("/datasets")
def list_datasets():
    return {
        "datasets": [
            {
                "name": name,
                "display_name": ctx["config"].display_name,
                "n_docs": len(ctx["products"]),
                "n_test_queries": len(ctx["test_queries"]),
                "doc_noun": ctx["config"].doc_noun,
                "grade_order": ctx["config"].grade_order,
                "grade_colors": ctx["config"].grade_colors,
                "grade_names": ctx["config"].grade_names,
            }
            for name, ctx in _datasets.items()
        ],
        "default": "esci" if "esci" in _datasets else next(iter(_datasets)),
    }


@app.get("/next_query")
def next_query(dataset: str | None = None):
    _, ctx = _get_ctx(dataset)
    return {"query": random.choice(ctx["test_query_list"])}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    ds_name, ctx = _get_ctx()
    default_query = random.choice(ctx["test_query_list"])
    return templates.TemplateResponse(
        request, "search.html",
        {
            "default_query": default_query,
            "methods": ctx.get("umap_methods", []),
            "n_products": len(ctx["products"]),
            "datasets_info": list_datasets(),
            "default_dataset": ds_name,
        },
    )


@app.post("/search")
def search(request_body: dict):
    ds_name, ctx = _get_ctx(request_body.get("dataset"))
    config = ctx["config"]
    colls = ctx["collections"]
    score_labels = ctx["score_labels"]

    query = request_body["query"]
    qid = query_id_for_text(query)
    qrels = ctx["test_qrels"].get(qid, {})

    try:
        with ThreadPoolExecutor(max_workers=2) as emb_pool:
            f_sim_emb = emb_pool.submit(
                _embed_one, query, "SEMANTIC_SIMILARITY"
            )
            f_ret_emb = emb_pool.submit(
                _embed_one, config.query_template.format(t=query)
            )
        sim_emb = np.array(f_sim_emb.result(), dtype=np.float32)
        ret_emb = np.array(f_ret_emb.result(), dtype=np.float32)
        tt_emb = apply_tower(
            ctx["tt_params"], sim_emb.reshape(1, -1), "query"
        ).squeeze()

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_bm25 = executor.submit(_bm25_search, ctx, query)
            f_sim = executor.submit(
                _vs2_search, ctx, colls["similarity"], sim_emb.tolist(),
            )
            f_ret = executor.submit(
                _vs2_search, ctx, colls["baseline"], ret_emb.tolist(),
            )
            f_tt = executor.submit(
                _vs2_search, ctx, colls["twotower"], tt_emb.tolist(),
            )

        def format_results(hits: list[dict]):
            scored = {h["id"]: h["score"] for h in hits}
            items = []
            for rank, h in enumerate(hits, 1):
                pid = h["id"]
                rel = qrels.get(pid)
                label = score_labels.get(rel) if rel is not None else None
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

    is_test_query = qid in ctx["test_qrels"]

    return {
        "query": query,
        "is_test_query": is_test_query,
        "dataset": f"{config.display_name} — {len(ctx['products']):,} {config.doc_noun}, "
                   f"{len(ctx['test_queries']):,} test queries",
        "grade_config": {
            "order": config.grade_order,
            "colors": config.grade_colors,
            "names": config.grade_names,
        },
        "columns": [
            {
                "label": "BM25",
                "description": "VS2 sparse baseline",
                "results": bm25_items,
                "metrics": _single_query_metrics(ctx, qid, bm25_scored) if is_test_query else {},
            },
            {
                "label": "Similarity",
                "description": "SEMANTIC_SIMILARITY task type",
                "results": sim_items,
                "metrics": _single_query_metrics(ctx, qid, sim_scored) if is_test_query else {},
            },
            {
                "label": "Two-Tower",
                "description": "Learned projection on similarity embeddings",
                "results": tt_items,
                "metrics": _single_query_metrics(ctx, qid, tt_scored) if is_test_query else {},
            },
            {
                "label": "Retrieval",
                "description": "Search query task type",
                "results": ret_items,
                "metrics": _single_query_metrics(ctx, qid, ret_scored) if is_test_query else {},
            },
        ],
    }


@app.get("/viz/coords/{method}")
def viz_coords(method: str, dataset: str | None = None):
    _, ctx = _get_ctx(dataset)
    key = f"umap_{method}_x"
    if key not in ctx:
        return JSONResponse(status_code=404, content={"error": f"No UMAP data for {method}"})
    x = ctx[f"umap_{method}_x"]
    y = ctx[f"umap_{method}_y"]
    n = np.uint32(len(x))
    buf = n.tobytes() + x.tobytes() + y.tobytes()
    return Response(content=buf, media_type="application/octet-stream")


@app.get("/viz/products")
def viz_products(dataset: str | None = None):
    _, ctx = _get_ctx(dataset)
    ids = ctx["product_ids"]
    titles = [ctx["products"][pid] for pid in ids]
    return {"ids": ids, "titles": titles}


@app.get("/viz/clusters/{method}")
def viz_clusters(method: str, dataset: str | None = None):
    _, ctx = _get_ctx(dataset)
    key = f"clusters_{method}"
    if key not in ctx:
        return JSONResponse(status_code=404, content={"error": f"No cluster data for {method}"})
    return ctx[key]


@app.post("/viz/search")
def viz_search(request_body: dict):
    ds_name, ctx = _get_ctx(request_body.get("dataset"))
    config = ctx["config"]
    colls = ctx["collections"]
    score_labels = ctx["score_labels"]

    query = request_body["query"]
    qid = query_id_for_text(query)
    qrels = ctx["test_qrels"].get(qid, {})
    is_test_query = qid in ctx["test_qrels"]

    try:
        with ThreadPoolExecutor(max_workers=2) as emb_pool:
            f_sim_emb = emb_pool.submit(_embed_one, query, "SEMANTIC_SIMILARITY")
            f_ret_emb = emb_pool.submit(
                _embed_one, config.query_template.format(t=query)
            )
        sim_emb = np.array(f_sim_emb.result(), dtype=np.float32)
        ret_emb = np.array(f_ret_emb.result(), dtype=np.float32)
        tt_emb = apply_tower(
            ctx["tt_params"], sim_emb.reshape(1, -1), "query"
        ).squeeze()

        with ThreadPoolExecutor(max_workers=3) as executor:
            f_sim = executor.submit(
                _vs2_search, ctx, colls["similarity"], sim_emb.tolist(),
            )
            f_ret = executor.submit(
                _vs2_search, ctx, colls["baseline"], ret_emb.tolist(),
            )
            f_tt = executor.submit(
                _vs2_search, ctx, colls["twotower"], tt_emb.tolist(),
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
                    pid: score_labels.get(qrels.get(pid))
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
