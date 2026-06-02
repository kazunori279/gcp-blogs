# Beyond Similarity Search: How Two-Tower Models and Gemini Embedding 2 Improve Product Search Quality

When you search for "wireless mouse" on a shopping site, you expect to see wireless mice — not mouse pads, keyboard-mouse combos, or articles about computer peripherals. Yet a naive embedding-based search often returns exactly those irrelevant results, because all of these items are *semantically similar* to your query. In this post, we explore why similarity search falls short for product retrieval, how two-tower models fix it, and how Gemini Embedding 2's task types give you most of that fix for free.

## The problem: queries and products are not "similar"

Most embedding-based search systems work by generating a single vector for the query and a single vector for each document, then finding documents whose vectors are closest to the query vector — a similarity search. This works well when the query and the target text are the same kind of thing: finding sentences similar to other sentences, or documents similar to other documents.

But in product search, the query and the document are fundamentally different objects. A query like "birthday present for my son" expresses an *intent* — what the user wants to accomplish. A relevant product title like "LEGO Star Wars X-Wing Starfighter" describes a *thing* — what the product is. These two texts are not semantically similar, yet one is the right answer for the other.

```
Query:    "birthday present for my son"
Product:  "LEGO Star Wars X-Wing Starfighter"
Similarity score: LOW (different topics)
Relevance: HIGH (great answer to the query)
```

This mismatch is at the heart of the problem. In embedding space, queries and products occupy different regions. A similarity search finds nearby points, but the right product for a query is often *not nearby* — it's in a completely different part of the space. What you need is a model that can learn the relationship between what a user asks for and what product actually satisfies that need.

This is not a new problem. Google Search has been tackling it since 2015, starting with deep learning ranking systems like RankBrain and neural matching. The question is: how can developers bring that same capability to their own search systems?

## The two-tower model: learning the query-product relationship

The classic solution in information retrieval is the **dual encoder** model, commonly called a **two-tower model**. Instead of one encoder for everything, you train two separate encoders — one for queries and one for documents — and train them together so that a query's vector and its relevant document's vector end up close in the shared space.

```
    "wireless mouse"              "Logitech M720 Triathlon"
          │                              │
    ┌─────┴─────┐                 ┌──────┴──────┐
    │Query Tower│                 │  Doc Tower  │
    └─────┬─────┘                 └──────┬──────┘
          │                              │
       q_proj                         d_proj
          │                              │
          └───────► dot product ◄────────┘
                    (high score = relevant)
```

During training, the model sees thousands of (query, relevant product) pairs. It learns to push query vectors and their relevant product vectors together, while pushing irrelevant products apart. After training, you encode all products once with the doc tower and store them in a vector database. At search time, you encode the query with the query tower and search for nearest neighbors — but now "nearest" means "most relevant," not "most similar."

### Building one on top of Gemini Embedding 2

In our demo, we build a lightweight two-tower model on top of frozen Gemini Embedding 2 embeddings. Rather than training an encoder from scratch, each tower is a shallow MLP with a residual connection that learns a small correction to the pre-trained 768-dimensional embeddings:

```
input (768d) ──┬── Dense(512) → ReLU → Dense(768) ──┬── L2 normalize → output (768d)
               │                                     │
               └─────────── residual add ────────────┘
```

The residual connection is critical here. Without it, the bottleneck (768 to 512 to 768) loses information and the model degrades below the baseline. With it, the MLP learns a small, task-specific adjustment — keeping the general-purpose knowledge from Gemini Embedding 2 while specializing the space for product retrieval.

```python
class Tower(nn.Module):
    hidden_dim: int = 512
    output_dim: int = 768

    @nn.compact
    def __call__(self, x):
        residual = x
        h = nn.Dense(self.hidden_dim)(x)
        h = nn.relu(h)
        h = nn.Dense(self.output_dim)(h)
        out = residual + h
        out = out / jnp.linalg.norm(out, axis=-1, keepdims=True)
        return out
```

The two towers are trained jointly with a multi-positive contrastive loss. This is important because in real product search, a query like "wireless mouse" has many valid results — not just one. The multi-positive loss treats all of them as positives simultaneously, rather than arbitrarily picking one and treating the rest as negatives.

We trained and evaluated this model on the [Amazon ESCI dataset](https://huggingface.co/datasets/smangrul/amazon_esci), a large-scale product search dataset with 352K products and over 20K queries, where each query-product pair has a human-annotated relevance grade: Exact (E), Substitute (S), Complement (C), or Irrelevant (I).

### It works — but it's not easy

The results confirm that the two-tower approach works. Training a two-tower model on similarity-type embeddings (the `TT Similarity` variant) improves MRR@10 from 0.6219 to 0.7161 — a 15% relative improvement over the frozen similarity baseline.

But building this system requires JAX/Flax experience, training data with relevance labels, a training pipeline with early stopping and validation, embedding precomputation, and deployment infrastructure. For many teams, this is a significant engineering investment. Is there a simpler way to get most of this improvement?

## Gemini Embedding 2 task types: a "quick two-tower model"

Here's where it gets interesting. [In a previous post](https://cloud.google.com/blog/products/ai-machine-learning/improve-gen-ai-search-with-vertex-ai-embeddings-and-task-types?e=48754805), we introduced Vertex AI Embeddings' task type feature. Gemini Embedding 2 takes this further with its `RETRIEVAL_QUERY` and `RETRIEVAL_DOCUMENT` task types.

When you specify a task type, the embedding model generates vectors that are optimized for that specific relationship. The model has been pre-trained using LLM distillation — essentially, a large language model was used to generate synthetic query-document pairs, and those pairs were used to train a dual encoder within the embedding model itself.

In other words, **Gemini Embedding 2 with retrieval task types is already a two-tower model** — distilled from an LLM, pre-trained on massive data, and packaged as a simple API call.

```python
from google import genai
from google.genai.types import EmbedContentConfig

client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")

# Embed a query with the retrieval-query task type
query_embedding = client.models.embed_content(
    model="gemini-embedding-2",
    contents="wireless mouse",
    config=EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
)

# Embed a product with the retrieval-document task type
product_embedding = client.models.embed_content(
    model="gemini-embedding-2",
    contents="Logitech M720 Triathlon Multi-Device Wireless Mouse",
    config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
)
```

No model training. No training data. No ML pipeline. Just specify the right task type when you generate embeddings, and the API handles the rest.

### How much of the two-tower improvement do task types capture?

We benchmarked four approaches on the Amazon ESCI dataset with 352K products and 3,134 test queries, plus a BM25 lexical baseline:

| Metric | BM25 | Similarity | Retrieval | TT Similarity | TT Retrieval |
|--------|------|------------|-----------|---------------|--------------|
| MRR@10 | 0.5738 | 0.6219 | 0.7372 | 0.7161 | **0.7442** |
| NDCG@10 | 0.3299 | 0.4098 | 0.5175 | 0.4895 | **0.5182** |
| Recall@10 | 0.2085 | 0.2704 | 0.3406 | 0.3246 | **0.3429** |
| Recall@100 | 0.4702 | 0.6232 | 0.7492 | 0.7376 | **0.7576** |

Here, `Similarity` uses `SEMANTIC_SIMILARITY` task type for both queries and products, while `Retrieval` uses task-specific prefixes that activate the retrieval behavior. `TT Similarity` and `TT Retrieval` add our custom-trained two-tower projections on top of each.

The numbers tell a striking story. Let's look at MRR@10, where the total possible improvement from baseline similarity to the best two-tower model is 0.1223 (from 0.6219 to 0.7442):

- **Just switching task types** (Similarity to Retrieval): +0.1153, which is **94% of the total improvement**
- **Training a custom two-tower model without changing task types** (Similarity to TT Similarity): +0.0942, or 77% of the total improvement

Simply switching from `SEMANTIC_SIMILARITY` to retrieval task types captures more improvement than training a custom two-tower model on the similarity embeddings. The task types alone outperform the custom-trained model.

The pattern holds across all metrics. For Recall@100, task types alone deliver 94% of the total possible improvement. You get the benefit of a pre-trained dual encoder — built by Google's research team on massive data — by changing a single API parameter.

### What the custom two-tower model adds

The custom two-tower model still has its place. When applied on top of the already-strong retrieval embeddings (`TT Retrieval`), it pushes the numbers a bit further — MRR@10 from 0.7372 to 0.7442. This is a modest but consistent improvement across all metrics. In high-stakes search applications where every fraction of a percent matters — e-commerce with millions of dollars in GMV, or medical information retrieval — that last-mile refinement can be worth the engineering investment.

But the key insight is the *diminishing returns*: the retrieval task type already closes 94% of the gap. The custom model provides the remaining 6%.

## When to use what

This gives us a clear decision framework:

**Start with task types.** For most applications, switching from `SEMANTIC_SIMILARITY` to retrieval task types (`RETRIEVAL_QUERY` for queries, `RETRIEVAL_DOCUMENT` for documents) will dramatically improve search quality with zero training effort. This is the right first move for any team building a search or RAG system.

**Train a two-tower model when the last few percent matter.** If you have domain-specific relevance data (click logs, purchase data, human ratings) and the engineering capacity to build a training pipeline, a lightweight two-tower model on top of retrieval embeddings can squeeze out additional quality. The residual architecture we demonstrated — a simple two-layer MLP with skip connections — is cheap to train and serve.

**Use the frozen retrieval baseline as your reference.** Before investing in a custom model, measure how much improvement the retrieval task type alone gives you on your own data. If it already meets your quality bar, the custom model may not be worth the operational complexity.

## Try it yourself

The complete code for this benchmark — data loading, embedding generation, two-tower training, evaluation, and a FastAPI web app with side-by-side result comparison and UMAP embedding visualizations — is available in our [demo repository](https://github.com/GoogleCloudPlatform/gcp-blogs/tree/main/20260522_ge2_and_tt_model).

```bash
# Install dependencies
uv sync

# Quick test with 1K products
uv run python -m tt_model.pipeline --max-products 1000

# Full benchmark (352K products)
uv run python -m tt_model.pipeline

# Launch the web app (requires Vector Search 2.0 collections)
uv run uvicorn tt_model.app:app --port 8080
```

The web app lets you compare BM25, Similarity, Two-Tower, and Retrieval results side by side for any query, with per-query metrics and relevance grading from the ESCI ground truth. An Embedding Map tab visualizes all 352K product embeddings in 2D via UMAP, revealing how each method organizes the product space differently.

### Resources

- [Gemini Embedding 2 documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings)
- [Embeddings task types guide](https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/task-types)
- [Vector Search 2.0 overview](https://cloud.google.com/vertex-ai/docs/vector-search/overview)
- [Previous post: Enhancing gen AI use cases with Vertex AI embeddings and task types](https://cloud.google.com/blog/products/ai-machine-learning/improve-gen-ai-search-with-vertex-ai-embeddings-and-task-types?e=48754805)
