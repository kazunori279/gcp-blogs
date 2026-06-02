from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from tqdm import tqdm

from tt_model.evaluate import evaluate_results

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Tokenize short ecommerce-style text with lightweight normalization."""
    return TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]

    def to_vs2(self) -> dict:
        """Return a VS2-compatible sparse vector payload."""
        return {
            "sparse": {
                "indices": self.indices,
                "values": self.values,
            }
        }


class BM25Index:
    """Lightweight BM25 index with reusable sparse document state."""

    def __init__(
        self,
        document_ids: list[str],
        document_texts: list[str],
        k1: float = 1.2,
        b: float = 0.75,
    ):
        self.document_ids = document_ids
        self.document_texts = document_texts
        self.k1 = k1
        self.b = b

        tokenized_docs = [tokenize(text) for text in document_texts]
        vocab_terms = sorted({token for doc in tokenized_docs for token in doc})
        self.token_to_id = {token: i for i, token in enumerate(vocab_terms)}
        self.id_to_token = vocab_terms

        self.doc_lengths: list[int] = [len(doc) for doc in tokenized_docs]
        self.avg_doc_length = (
            sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        )

        self.doc_term_freqs: list[dict[int, int]] = []
        self.postings: dict[int, list[tuple[int, int]]] = defaultdict(list)
        doc_freqs = [0] * len(vocab_terms)

        for doc_idx, tokens in enumerate(tokenized_docs):
            term_counts = Counter(self.token_to_id[token] for token in tokens)
            sparse_counts = dict(sorted(term_counts.items()))
            self.doc_term_freqs.append(sparse_counts)
            for token_id, tf in sparse_counts.items():
                doc_freqs[token_id] += 1
                self.postings[token_id].append((doc_idx, tf))

        n_docs = len(document_ids)
        self.idf = [
            math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5)) if df > 0 else 0.0
            for df in doc_freqs
        ]

    def _doc_norm(self, doc_idx: int) -> float:
        if self.avg_doc_length == 0:
            return 1.0
        return self.k1 * (
            1.0 - self.b + self.b * self.doc_lengths[doc_idx] / self.avg_doc_length
        )

    def query_term_weights(self, query_text: str) -> dict[int, float]:
        """Sparse query weights for future VS2-compatible sparse search work."""
        token_counts = Counter(
            self.token_to_id[token]
            for token in tokenize(query_text)
            if token in self.token_to_id
        )
        return {
            token_id: self.idf[token_id] * tf
            for token_id, tf in sorted(token_counts.items())
        }

    def document_sparse_vector(
        self, doc_idx: int, weighting: str = "bm25_doc"
    ) -> SparseVector:
        """Return a sparse document vector for future VS2 ingestion."""
        term_freqs = self.doc_term_freqs[doc_idx]
        indices = list(term_freqs.keys())

        if weighting == "count":
            values = [float(term_freqs[token_id]) for token_id in indices]
        elif weighting == "idf":
            values = [self.idf[token_id] for token_id in indices]
        elif weighting == "bm25_tf":
            norm = self._doc_norm(doc_idx)
            values = [
                ((self.k1 + 1.0) * term_freqs[token_id])
                / (term_freqs[token_id] + norm)
                for token_id in indices
            ]
        elif weighting == "bm25_doc":
            norm = self._doc_norm(doc_idx)
            values = [
                self.idf[token_id]
                * ((self.k1 + 1.0) * term_freqs[token_id])
                / (term_freqs[token_id] + norm)
                for token_id in indices
            ]
        else:
            raise ValueError(f"Unknown sparse weighting: {weighting}")

        return SparseVector(indices=indices, values=values)

    def score(self, query_text: str) -> dict[int, float]:
        """Score all matching documents for a query using exact BM25."""
        scores: dict[int, float] = defaultdict(float)
        query_counts = Counter(
            self.token_to_id[token]
            for token in tokenize(query_text)
            if token in self.token_to_id
        )

        for token_id, qtf in query_counts.items():
            idf = self.idf[token_id]
            for doc_idx, tf in self.postings[token_id]:
                norm = self._doc_norm(doc_idx)
                doc_score = idf * ((self.k1 + 1.0) * tf) / (tf + norm)
                scores[doc_idx] += qtf * doc_score

        return dict(scores)

    def search(self, query_text: str, top_k: int = 100) -> list[tuple[str, float]]:
        scores = self.score(query_text)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [(self.document_ids[doc_idx], float(score)) for doc_idx, score in ranked]


def evaluate_bm25(
    query_ids: list[str],
    query_texts: list[str],
    passage_ids: list[str],
    passage_texts: list[str],
    qrels: dict,
    top_k: int = 100,
    k1: float = 1.2,
    b: float = 0.75,
) -> tuple[dict[str, float], BM25Index]:
    """Evaluate a BM25 baseline over raw text."""
    index = BM25Index(passage_ids, passage_texts, k1=k1, b=b)
    return evaluate_bm25_index(index, query_ids, query_texts, qrels, top_k=top_k), index


def evaluate_bm25_index(
    index: BM25Index,
    query_ids: list[str],
    query_texts: list[str],
    qrels: dict,
    top_k: int = 100,
) -> dict[str, float]:
    """Evaluate an already-built BM25 index over query text."""
    results = {}
    for qid, query_text in tqdm(
        zip(query_ids, query_texts),
        total=len(query_ids),
        desc="Evaluating BM25",
    ):
        results[qid] = dict(index.search(query_text, top_k=top_k))
    return evaluate_results(qrels, results)
