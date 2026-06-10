import os
from pathlib import Path

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
EMBEDDING_MODEL = "gemini-embedding-2"
LABEL_MODEL = "gemini-2.5-flash-lite"

NUM_PASSAGES = 100_000
EMBEDDING_DIM = 768

HIDDEN_DIM = 512
OUTPUT_DIM = 768
LEARNING_RATE = 3e-4
BATCH_SIZE = 512
NUM_EPOCHS = 10
TEMPERATURE = 0.05
SEED = 42
VALIDATION_FRAC = 0.1
MAX_TRAIN_EPOCHS = 30
EARLY_STOPPING_PATIENCE = 4
EARLY_STOPPING_MIN_DELTA = 0.001

COLLECTION_SIMILARITY = "tt-demo-sim-v4"
COLLECTION_BM25 = "tt-demo-bm25-v1"
COLLECTION_BASELINE = "tt-demo-baseline-v4"
COLLECTION_TWOTOWER = "tt-demo-twotower-v4"
COLLECTION_TWOTOWER_SIMILARITY = "tt-demo-twotower-sim-v4"
COLLECTION_TWOTOWER_RETRIEVAL = "tt-demo-twotower-ret-v4"

MSMARCO_COLLECTION_SIMILARITY = "tt-msmarco-sim-v1"
MSMARCO_COLLECTION_BM25 = "tt-msmarco-bm25-v1"
MSMARCO_COLLECTION_BASELINE = "tt-msmarco-baseline-v1"
MSMARCO_COLLECTION_TWOTOWER = "tt-msmarco-twotower-v1"
MSMARCO_COLLECTION_TWOTOWER_SIMILARITY = "tt-msmarco-twotower-sim-v1"
MSMARCO_COLLECTION_TWOTOWER_RETRIEVAL = "tt-msmarco-twotower-ret-v1"

VECTOR_FIELD = "embedding"
SPARSE_VECTOR_FIELD = "sparse_embedding"

GCS_BUCKET = "gcp-samples-ic0-tt-demo"

DATA_DIR = Path("data")
MODEL_PARAMS_DIR = DATA_DIR / "model_params"
MSMARCO_MODEL_PARAMS_DIR = DATA_DIR / "model_params_msmarco"
UMAP_DIR = DATA_DIR / "umap"
MSMARCO_UMAP_DIR = DATA_DIR / "umap_msmarco"
UMAP_METHODS = ["similarity", "retrieval", "tt_similarity", "tt_retrieval"]


def collection_names(dataset: str = "esci") -> dict[str, str]:
    if dataset == "msmarco":
        return {
            "similarity": MSMARCO_COLLECTION_SIMILARITY,
            "bm25": MSMARCO_COLLECTION_BM25,
            "baseline": MSMARCO_COLLECTION_BASELINE,
            "twotower": MSMARCO_COLLECTION_TWOTOWER,
            "twotower_similarity": MSMARCO_COLLECTION_TWOTOWER_SIMILARITY,
            "twotower_retrieval": MSMARCO_COLLECTION_TWOTOWER_RETRIEVAL,
        }
    return {
        "similarity": COLLECTION_SIMILARITY,
        "bm25": COLLECTION_BM25,
        "baseline": COLLECTION_BASELINE,
        "twotower": COLLECTION_TWOTOWER,
        "twotower_similarity": COLLECTION_TWOTOWER_SIMILARITY,
        "twotower_retrieval": COLLECTION_TWOTOWER_RETRIEVAL,
    }


def model_params_dir(dataset: str = "esci") -> Path:
    return MSMARCO_MODEL_PARAMS_DIR if dataset == "msmarco" else MODEL_PARAMS_DIR


def umap_dir(dataset: str = "esci") -> Path:
    return MSMARCO_UMAP_DIR if dataset == "msmarco" else UMAP_DIR

MAX_WORKERS = 10
MAX_RETRIES = 5
SPARSE_BATCH_SIZE = 50
SPARSE_INSERT_MAX_RETRIES = 8
