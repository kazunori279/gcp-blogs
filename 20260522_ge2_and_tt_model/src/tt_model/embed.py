import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
from google import genai
from google.cloud import storage
from google.genai.types import EmbedContentConfig
from tqdm import tqdm

from tt_model.config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    GCS_BUCKET,
    MAX_RETRIES,
    MAX_WORKERS,
    PROJECT_ID,
)

_client = None
_gcs_client = None

EMBEDDING_LOCATION = "global"


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True, project=PROJECT_ID, location=EMBEDDING_LOCATION
        )
    return _client


def _get_gcs_bucket():
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client(project=PROJECT_ID)
    return _gcs_client.bucket(GCS_BUCKET)


def _embed_one(text: str, task_type: str | None = None) -> list[float]:
    """Embed a single text with retries."""
    client = _get_client()
    config = EmbedContentConfig(
        output_dimensionality=EMBEDDING_DIM,
        task_type=task_type,
    )
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=config,
            )
            return response.embeddings[0].values
        except Exception:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2**attempt)
    return []


def embed_parallel(texts: list[str], task_type: str | None = None) -> np.ndarray:
    """Embed texts using parallel single-text API calls."""
    results: list[tuple[int, list[float]]] = [None] * len(texts)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_embed_one, text, task_type): i
            for i, text in enumerate(texts)
        }
        pbar = tqdm(total=len(texts))
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
            pbar.update(1)
        pbar.close()

    return np.array(results, dtype=np.float32)


def _build_blob_name(dataset_name: str, task_type: str | None) -> str:
    task_label = task_type.lower() if task_type else "retrieval"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"{dataset_name}-{EMBEDDING_MODEL}-{task_label}-{ts}.npz"


def _metadata_blob_name(blob_name: str) -> str:
    if blob_name.endswith(".npz"):
        return f"{blob_name[:-4]}.metadata.json"
    return f"{blob_name}.metadata.json"


def compute_and_upload_embeddings(
    ids: list[str],
    texts: list[str],
    dataset_name: str,
    task_type: str | None = None,
    metadata: dict | None = None,
) -> tuple[str, np.ndarray]:
    """Compute embeddings and upload to GCS. Returns (blob_name, embeddings)."""
    print(f"  Computing {len(texts)} embeddings for {dataset_name} "
          f"({MAX_WORKERS} threads)...")
    embeddings = embed_parallel(texts, task_type=task_type)

    blob_name = _build_blob_name(dataset_name, task_type)
    buf = io.BytesIO()
    np.savez(buf, ids=np.array(ids), embeddings=embeddings)
    buf.seek(0)

    bucket = _get_gcs_bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buf, content_type="application/octet-stream")

    artifact_metadata = {
        "dataset_name": dataset_name,
        "embedding_model": EMBEDDING_MODEL,
        "task_type": task_type or "retrieval",
        "count": len(ids),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        artifact_metadata.update(metadata)
    bucket.blob(_metadata_blob_name(blob_name)).upload_from_string(
        json.dumps(artifact_metadata, indent=2, sort_keys=True),
        content_type="application/json",
    )
    print(f"  Uploaded to gs://{GCS_BUCKET}/{blob_name}")
    return blob_name, embeddings


def load_embedding_metadata(blob_name: str) -> dict | None:
    """Load optional sidecar metadata for an embedding blob."""
    bucket = _get_gcs_bucket()
    blob = bucket.blob(_metadata_blob_name(blob_name))
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())


def load_embeddings(blob_name: str) -> tuple[list[str], np.ndarray, dict | None]:
    """Download embeddings from GCS. Returns (ids, embeddings, metadata)."""
    bucket = _get_gcs_bucket()
    blob = bucket.blob(blob_name)
    buf = io.BytesIO(blob.download_as_bytes())
    data = np.load(buf, allow_pickle=True)
    ids = list(data["ids"])
    metadata = load_embedding_metadata(blob_name)
    print(f"  Loaded {len(ids)} embeddings from gs://{GCS_BUCKET}/{blob_name}")
    if metadata:
        print(
            "  Metadata: "
            f"split={metadata.get('split', 'unknown')} "
            f"id_scheme={metadata.get('id_scheme', 'unknown')}"
        )
    return ids, data["embeddings"], metadata


def list_embeddings(prefix: str = "") -> list[str]:
    """List available embedding files in GCS."""
    bucket = _get_gcs_bucket()
    blobs = bucket.list_blobs(prefix=prefix)
    return sorted(b.name for b in blobs if b.name.endswith(".npz"))
