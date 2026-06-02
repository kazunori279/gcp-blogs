from pathlib import Path
from datetime import datetime

import jax
import jax.numpy as jnp
import numpy as np
from flax import serialization
from flax.training import train_state
import optax

from tt_model.config import (
    BATCH_SIZE,
    EARLY_STOPPING_MIN_DELTA,
    EARLY_STOPPING_PATIENCE,
    EMBEDDING_DIM,
    LEARNING_RATE,
    MAX_TRAIN_EPOCHS,
    MODEL_PARAMS_DIR,
    SEED,
)
from tt_model.evaluate import evaluate_retrieval
from tt_model.model import TwoTowerModel, multi_positive_contrastive_loss


def create_train_state(rng, model):
    dummy_q = jnp.ones((1, EMBEDDING_DIM))
    dummy_d = jnp.ones((1, EMBEDDING_DIM))
    params = model.init(rng, dummy_q, dummy_d)
    tx = optax.adam(LEARNING_RATE)
    return train_state.TrainState.create(
        apply_fn=model.apply, params=params, tx=tx
    )


def checkpoint_path(model_variant: str, timestamp: str | None = None) -> Path:
    """Build a checkpoint path for a training variant."""
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    return MODEL_PARAMS_DIR / f"{model_variant}-{ts}.msgpack"


def latest_checkpoint_path(model_variant: str) -> Path:
    """Return the most recent checkpoint path for a training variant."""
    pattern = f"{model_variant}-*.msgpack"
    matches = sorted(MODEL_PARAMS_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No checkpoints found for variant '{model_variant}' in {MODEL_PARAMS_DIR}"
        )
    return matches[-1]


def load_checkpoint(model_variant: str, checkpoint: Path | None = None):
    """Load params from a specific or latest checkpoint for a model variant."""
    path = checkpoint or latest_checkpoint_path(model_variant)
    model = TwoTowerModel()
    rng = jax.random.PRNGKey(SEED)
    state = create_train_state(rng, model)
    with open(path, "rb") as f:
        params = serialization.from_bytes(state.params, f.read())
    print(f"  Loaded model params from {path}")
    return params, path


@jax.jit
def train_step(state, q_batch, d_batch, group_ids):
    def loss_fn(params):
        q_proj, d_proj = state.apply_fn(params, q_batch, d_batch)
        return multi_positive_contrastive_loss(q_proj, d_proj, group_ids)

    loss, grads = jax.value_and_grad(loss_fn)(state.params)
    state = state.apply_gradients(grads=grads)
    return state, loss


def train(
    train_query_embs: np.ndarray,
    train_doc_embs: np.ndarray,
    train_group_ids: np.ndarray,
    val_query_ids: list[str],
    val_query_embs: np.ndarray,
    val_qrels: dict,
    product_ids: list[str],
    product_embs: np.ndarray,
    num_epochs: int = MAX_TRAIN_EPOCHS,
    batch_size: int = BATCH_SIZE,
    seed: int = SEED,
    patience: int = EARLY_STOPPING_PATIENCE,
    min_delta: float = EARLY_STOPPING_MIN_DELTA,
    model_variant: str = "similarity",
    save_path: Path | None = None,
) -> tuple[train_state.TrainState, dict[str, float]]:
    """Train with validation-based early stopping and best-checkpoint selection."""
    print(f"Training two-tower model ({len(train_query_embs)} pairs, "
          f"{num_epochs} epochs, batch_size={batch_size}, variant={model_variant})")
    print(
        "  Early stopping: "
        f"monitor=MRR@10 patience={patience} min_delta={min_delta:.4f}"
    )

    model = TwoTowerModel()
    rng = jax.random.PRNGKey(seed)
    state = create_train_state(rng, model)

    rng_np = np.random.default_rng(seed)
    best_state = state
    best_metrics = None
    best_score = float("-inf")
    best_epoch = 0
    epochs_without_improvement = 0

    for epoch in range(num_epochs):
        perm = rng_np.permutation(len(train_query_embs))
        epoch_losses = []

        for i in range(0, len(perm), batch_size):
            batch_idx = perm[i : i + batch_size]
            if len(batch_idx) < 2:
                continue
            q_batch = jnp.array(train_query_embs[batch_idx])
            d_batch = jnp.array(train_doc_embs[batch_idx])
            group_batch = jnp.array(train_group_ids[batch_idx])
            state, loss = train_step(state, q_batch, d_batch, group_batch)
            epoch_losses.append(float(loss))

        avg_loss = np.mean(epoch_losses)
        val_product_embs = apply_tower(state.params, product_embs, "doc")
        val_query_proj = apply_tower(state.params, val_query_embs, "query")
        val_metrics = evaluate_retrieval(
            val_query_ids,
            val_query_proj,
            product_ids,
            val_product_embs,
            val_qrels,
        )
        val_score = val_metrics["MRR@10"]

        print(
            f"  Epoch {epoch + 1}/{num_epochs}  "
            f"loss={avg_loss:.4f}  "
            f"val_MRR@10={val_metrics['MRR@10']:.4f}  "
            f"val_NDCG@10={val_metrics['NDCG@10']:.4f}"
        )

        if val_score > best_score + min_delta:
            best_state = state
            best_metrics = val_metrics
            best_score = val_score
            best_epoch = epoch + 1
            epochs_without_improvement = 0
            print(f"    New best checkpoint at epoch {best_epoch}")
        else:
            epochs_without_improvement += 1
            print(
                "    No meaningful improvement "
                f"({epochs_without_improvement}/{patience})"
            )
            if epochs_without_improvement >= patience:
                print(f"  Early stopping at epoch {epoch + 1}")
                break

    if best_metrics is None:
        raise RuntimeError("Training finished without producing validation metrics")

    print(
        f"  Best checkpoint: epoch {best_epoch} "
        f"(val_MRR@10={best_metrics['MRR@10']:.4f})"
    )

    if save_path is None and model_variant:
        save_path = checkpoint_path(model_variant)

    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(serialization.to_bytes(best_state.params))
        print(f"  Saved model params to {save_path}")

    return best_state, best_metrics


def apply_tower(params, embeddings: np.ndarray, tower: str) -> np.ndarray:
    """Apply a single tower to embeddings in batches."""
    model = TwoTowerModel()
    results = []
    batch_size = 4096

    for i in range(0, len(embeddings), batch_size):
        batch = jnp.array(embeddings[i : i + batch_size])
        if tower == "query":
            proj = model.apply(params, batch, method=TwoTowerModel.encode_query)
        else:
            proj = model.apply(params, batch, method=TwoTowerModel.encode_doc)
        results.append(np.array(proj))

    return np.concatenate(results, axis=0)
