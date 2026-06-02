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
VECTOR_FIELD = "embedding"
SPARSE_VECTOR_FIELD = "sparse_embedding"

GCS_BUCKET = "gcp-samples-ic0-tt-demo"

DATA_DIR = Path("data")
MODEL_PARAMS_DIR = DATA_DIR / "model_params"
UMAP_DIR = DATA_DIR / "umap"
UMAP_METHODS = ["similarity", "retrieval", "tt_similarity", "tt_retrieval"]

MAX_WORKERS = 10
MAX_RETRIES = 5
SPARSE_BATCH_SIZE = 50
SPARSE_INSERT_MAX_RETRIES = 8
