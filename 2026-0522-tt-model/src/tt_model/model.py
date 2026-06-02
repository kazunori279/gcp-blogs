import jax
import jax.numpy as jnp
import optax
from flax import linen as nn

from tt_model.config import HIDDEN_DIM, OUTPUT_DIM, TEMPERATURE


class Tower(nn.Module):
    hidden_dim: int = HIDDEN_DIM
    output_dim: int = OUTPUT_DIM

    @nn.compact
    def __call__(self, x, training: bool = False):
        residual = x
        h = nn.Dense(self.hidden_dim)(x)
        h = nn.relu(h)
        h = nn.Dense(self.output_dim)(h)
        out = residual + h
        out = out / jnp.linalg.norm(out, axis=-1, keepdims=True)
        return out


class TwoTowerModel(nn.Module):
    hidden_dim: int = HIDDEN_DIM
    output_dim: int = OUTPUT_DIM

    def setup(self):
        self.query_tower = Tower(self.hidden_dim, self.output_dim)
        self.doc_tower = Tower(self.hidden_dim, self.output_dim)

    def __call__(self, query_embs, doc_embs):
        q = self.encode_query(query_embs)
        d = self.encode_doc(doc_embs)
        return q, d

    def encode_query(self, query_embs):
        return self.query_tower(query_embs)

    def encode_doc(self, doc_embs):
        return self.doc_tower(doc_embs)


def multi_positive_contrastive_loss(
    q_proj,
    d_proj,
    group_ids,
    temperature=TEMPERATURE,
):
    """Contrastive loss with same-query positives."""
    sim_matrix = q_proj @ d_proj.T / temperature
    positive_mask = group_ids[:, None] == group_ids[None, :]
    positive_mask = positive_mask.astype(sim_matrix.dtype)

    log_probs_q = jax.nn.log_softmax(sim_matrix, axis=1)
    pos_counts_q = jnp.maximum(positive_mask.sum(axis=1), 1.0)
    loss_q = -(positive_mask * log_probs_q).sum(axis=1) / pos_counts_q

    log_probs_d = jax.nn.log_softmax(sim_matrix.T, axis=1)
    pos_counts_d = jnp.maximum(positive_mask.sum(axis=0), 1.0)
    loss_d = -(positive_mask.T * log_probs_d).sum(axis=1) / pos_counts_d

    return 0.5 * (loss_q.mean() + loss_d.mean())
