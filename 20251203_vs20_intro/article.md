# Introducing Vertex AI Vector Search 2.0: A Fully Managed Vector Database

> **TL;DR**: Vector Search 2.0 = Collections + Auto-Embeddings + Zero Infrastructure
> - Go from 0 to prototype in **under 5 minutes**
> - Same API scales from prototype to **billions of vectors**
> - `pip install google-cloud-vectorsearch` and you're ready
> - [Try the notebook now](https://github.com/GoogleCloudPlatform/generative-ai/blob/main/embeddings/vector-search-2-intro.ipynb)

---

## The Problem: Vector Search Shouldn't Require a PhD in Infrastructure

You've built an amazing RAG application. Your embeddings are working. Your LLM is generating great responses. Time to deploy to production, right?

Not so fast. With traditional vector search, you suddenly need to:
- Create and configure an index with the right parameters
- Deploy an index endpoint and manage its lifecycle
- Set up scaling policies for traffic spikes
- Coordinate batch updates through Cloud Storage
- Monitor multiple resources and their health

**You came to build AI applications, not become an infrastructure engineer.**

Vector Search 2.0 changes everything. Let me show you.

## See It Working: Your First Search in 10 Lines

Before we dive into concepts, here's a complete working example—an e-commerce product search:

```python
from google.cloud import vectorsearch_v1beta

client = vectorsearch_v1beta.VectorSearchServiceClient()
data_client = vectorsearch_v1beta.DataObjectServiceClient()
search_client = vectorsearch_v1beta.DataObjectSearchServiceClient()
parent = f"projects/{PROJECT_ID}/locations/us-central1"

# Create collection with auto-embeddings (VS2.0 generates embeddings for you!)
client.create_collection(parent=parent, collection_id="products", collection={
    "data_schema": {"properties": {"name": {"type": "string"}, "category": {"type": "string"}, "retail_price": {"type": "number"}}},
    "vector_schema": {"name_embedding": {"dense_vector": {"dimensions": 768,
        "vertex_embedding_config": {"model_id": "text-embedding-004", "text_template": "{name}"}}}}
})

# Add products - no embedding code needed!
data_client.batch_create_data_objects(parent=f"{parent}/collections/products", requests=[
    {"data_object_id": "1", "data_object": {"data": {"name": "Classic Blue Denim Jeans", "category": "Jeans", "retail_price": 59.99}}},
    {"data_object_id": "2", "data_object": {"data": {"name": "Slim Fit Dark Wash Jeans", "category": "Jeans", "retail_price": 74.99}}},
])

# Search immediately - no index deployment, no waiting
results = search_client.search_data_objects(parent=f"{parent}/collections/products",
    semantic_search={"search_text": "blue denim jeans", "search_field": "name_embedding", "top_k": 5})
```

That's it. No index creation. No endpoint deployment. No embedding pipeline. **It just works.**

## Before & After: What Changed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VECTOR SEARCH 1.0                                   │
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Generate │───▶│ Upload   │───▶│ Create   │───▶│ Deploy   │              │
│  │Embeddings│    │ to GCS   │    │  Index   │    │ Endpoint │              │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘              │
│       │                               │               │                     │
│       │         ┌──────────┐          │     ┌────────────────┐             │
│       └────────▶│ Manage   │◀─────────┴────▶│Configure Scale │             │
│                 │ Updates  │                │ & Monitoring   │             │
│                 └──────────┘                └────────────────┘             │
│                                                                             │
│  Time to first query: 30-60 minutes        Resources to manage: 4+         │
└─────────────────────────────────────────────────────────────────────────────┘

                                    ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                         VECTOR SEARCH 2.0                                   │
│                                                                             │
│         ┌──────────────┐              ┌──────────────┐                     │
│         │   Create     │─────────────▶│    Search    │                     │
│         │  Collection  │              │              │                     │
│         └──────────────┘              └──────────────┘                     │
│                │                                                            │
│                ▼                                                            │
│    (Auto-embeddings, auto-scaling, auto-indexing - all handled)            │
│                                                                             │
│  Time to first query: < 5 minutes          Resources to manage: 1          │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Aspect | Vector Search 1.0 | Vector Search 2.0 |
|--------|-------------------|-------------------|
| Time to first query | 30-60 min | < 5 min |
| Embedding pipeline | You build it | Auto-embeddings |
| Index management | Manual create/deploy | Automatic |
| Scaling | Configure policies | Auto-scaling |
| Updates | Batch via GCS | Real-time CRUD |
| Resources to manage | 4+ (index, endpoint, GCS, etc.) | 1 (collection) |

## Architecture: It's Just a Collection

```
                    ┌─────────────────────────────────────────┐
                    │            COLLECTION                    │
                    │  ┌─────────────────────────────────────┐│
                    │  │         Data Schema                 ││
                    │  │  (name, category, retail_price...)  ││
                    │  └─────────────────────────────────────┘│
                    │  ┌─────────────────────────────────────┐│
     Your Data ────▶│  │         Data Objects                ││────▶ Search Results
                    │  │  (products, documents, content...)  ││
                    │  └─────────────────────────────────────┘│
                    │  ┌─────────────────────────────────────┐│
                    │  │      Vector Schema + Embeddings     ││
                    │  │  (auto-generated or bring your own) ││
                    │  └─────────────────────────────────────┘│
                    │  ┌─────────────────────────────────────┐│
                    │  │    Index (optional, for scale)      ││
                    │  │  (kNN → ANN when you need speed)    ││
                    │  └─────────────────────────────────────┘│
                    └─────────────────────────────────────────┘
```

**One resource. Everything included.** Your data, vectors, and index all live together.

## Choose Your Path

Different needs, different approaches. Pick what fits:

### Path 1: "I just want to prototype quickly"

Use kNN (no index needed) with auto-embeddings:

```python
# Create collection with auto-embeddings
client.create_collection(parent=parent, collection_id="products", collection={
    "vector_schema": {"name_embedding": {"dense_vector": {
        "dimensions": 768,
        "vertex_embedding_config": {"model_id": "text-embedding-004", "text_template": "{name}"}
    }}}
})

# Insert data - embeddings generated automatically
data_client.create_data_object(parent=f"{parent}/collections/products",
    data_object_id="prod-1",
    data_object={"data": {"name": "Blue Denim Jeans", "category": "Jeans"}, "vectors": {}})

# Search immediately (kNN - no index required)
results = search_client.search_data_objects(...)
```

**Time to working demo: ~2 minutes**

### Path 2: "I have my own embeddings"

Bring your own vectors:

```python
client.create_collection(parent=parent, collection_id="products", collection={
    "vector_schema": {"product_embedding": {"dense_vector": {"dimensions": 768}}}
})

# Insert with your pre-computed embeddings
data_client.batch_create_data_objects(parent=f"{parent}/collections/products", requests=[
    {"data_object_id": "prod-1", "data_object": {
        "data": {"name": "Blue Denim Jeans"},
        "vectors": {"product_embedding": {"values": your_embedding}}
    }}
])
```

### Path 3: "I need production scale"

Add an ANN index for billion-scale search:

```python
# Same collection, same data, same API - just add an index
client.create_index(
    parent=f"{parent}/collections/products",
    index_id="product-name-index",
    index={
        "index_field": "name_embedding",
        "filter_fields": ["category", "retail_price"],
        "store_fields": ["name"]
    }
)

# Search uses the same API - now backed by ANN
results = search_client.search_data_objects(...)  # Millisecond latency at billion scale
```

### Path 4: "I need hybrid search + ranking"

Combine semantic, text search, and RRF ranking:

```python
results = search_client.batch_search_data_objects(
    parent=f"{parent}/collections/products",
    searches=[
        {"semantic_search": {"search_text": "blue denim jeans", "search_field": "name_embedding", "top_k": 20}},
        {"text_search": {"search_text": "denim OR jeans", "data_field_names": ["name"], "top_k": 20}},
    ],
    combine={"ranker": {"rrf": {"weights": [1.0, 1.0]}}}  # RRF ranking
)
```

## Performance: The Numbers

| Metric | Value |
|--------|-------|
| Query latency (with ANN index) | < 10ms at 1B+ vectors |
| Time to first query (kNN, no index) | Immediate |
| Index build time | Minutes, not hours |
| Max vectors per collection | Billions |
| Concurrent queries | Auto-scales |

VS2.0 is powered by the same ScaNN infrastructure behind Google Search, YouTube, and Google Play.

## Building E-Commerce Product Search: Complete Walkthrough

Let's build something real using the [TheLook e-commerce dataset](https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce). We'll create a product search system that:

1. Stores fashion products with auto-generated embeddings
2. Finds similar products by semantic meaning
3. Filters by category and price
4. Scales to production when ready

### The Dataset

TheLook contains ~30K fashion products. For this demo, we'll use 3,000 products:

| ID | Name | Category | Price |
|----|------|----------|-------|
| 8037 | Jostar Short Sleeve Solid Stretchy Capri Pants Set | Clothing Sets | $38.99 |
| 8036 | Womens Top Stitch Jacket and Pant Set | Clothing Sets | $199.95 |
| 8035 | Ulla Popken Plus Size 3-Piece Duster and Pants Set | Clothing Sets | $159.00 |

### Step 1: Set Up

```bash
pip install google-cloud-vectorsearch tqdm
gcloud auth application-default login
gcloud services enable vectorsearch.googleapis.com aiplatform.googleapis.com
```

### Step 2: Initialize the SDK Clients

VS2.0 uses three specialized clients:

```python
from google.cloud import vectorsearch_v1beta

# VectorSearchServiceClient: Manages Collections and Indexes
vector_search_client = vectorsearch_v1beta.VectorSearchServiceClient()

# DataObjectServiceClient: Manages Data Objects (CRUD)
data_object_client = vectorsearch_v1beta.DataObjectServiceClient()

# DataObjectSearchServiceClient: Performs search and query operations
search_client = vectorsearch_v1beta.DataObjectSearchServiceClient()

PROJECT_ID = "your-project-id"
LOCATION = "us-central1"
parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
```

### Step 3: Create the Collection

```python
collection_id = "products-demo"

request = vectorsearch_v1beta.CreateCollectionRequest(
    parent=parent,
    collection_id=collection_id,
    collection={
        # Data Schema: Product attributes
        "data_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "category": {"type": "string"},
                "retail_price": {"type": "number"},
            },
        },
        # Vector Schema: Auto-embeddings from product name
        "vector_schema": {
            "name_dense_embedding": {
                "dense_vector": {
                    "dimensions": 768,
                    "vertex_embedding_config": {
                        "model_id": "text-embedding-004",
                        "text_template": "{name}",
                        "task_type": "RETRIEVAL_DOCUMENT",
                    },
                },
            },
        },
    }
)

operation = vector_search_client.create_collection(request=request)
operation.result()
print("✅ Collection created!")
```

**Key Point**: The `vertex_embedding_config` tells VS2.0 to automatically generate embeddings from the `name` field using `text-embedding-004`. No embedding code needed!

### Step 4: Add Products

```python
import json
import urllib.request

# Download TheLook dataset
dataset_url = "https://storage.googleapis.com/gcp-samples-ic0-vs20demo/thelook_dataset.jsonl"
products = []

with urllib.request.urlopen(dataset_url) as response:
    for line in response:
        product = json.loads(line.decode('utf-8'))
        products.append({
            "data_object_id": product["id"],
            "data_object": {
                "data": {
                    "id": product["id"],
                    "name": product["name"],
                    "category": product["category"],
                    "retail_price": product["retail_price"],
                },
                "vectors": {},  # Empty = auto-generate embeddings!
            }
        })
        if len(products) >= 3000:
            break

# Batch import with rate limiting (100 per batch, 2.5s delay for API quota)
import time
from tqdm import tqdm

batch_size = 100
for batch_start in tqdm(range(0, len(products), batch_size), desc="Importing"):
    batch = products[batch_start:batch_start + batch_size]

    request = vectorsearch_v1beta.BatchCreateDataObjectsRequest(
        parent=f"{parent}/collections/{collection_id}",
        requests=batch,
    )
    data_object_client.batch_create_data_objects(request)
    time.sleep(2.5)  # Stay under 3,000 RPM embedding API quota

print(f"✅ Imported {len(products)} products!")
```

### Step 5: Semantic Search

Find products by meaning, not just keywords:

```python
query = "blue denim jeans"

request = vectorsearch_v1beta.SearchDataObjectsRequest(
    parent=f"{parent}/collections/{collection_id}",
    semantic_search=vectorsearch_v1beta.SemanticSearch(
        search_text=query,
        search_field="name_dense_embedding",
        task_type="RETRIEVAL_QUERY",
        top_k=5,
        output_fields=vectorsearch_v1beta.OutputFields(
            data_fields=["name", "category", "retail_price"]
        ),
    ),
)

results = search_client.search_data_objects(request)

print(f"Results for '{query}':")
for i, result in enumerate(results, 1):
    data = result.data_object.data
    print(f"{i}. {data['name'][:60]}...")
    print(f"   {data['category']} - ${data['retail_price']:.2f}")
```

Output:
```
Results for 'blue denim jeans':
1. Levi's Classic Blue Denim Straight Leg Jeans...
   Jeans - $68.00
2. Wrangler Slim Fit Dark Wash Denim Jeans...
   Jeans - $54.99
3. Gap High Rise Skinny Jeans in Medium Indigo...
   Jeans - $79.95
```

### Step 6: Filter Products

Query by attributes like SQL WHERE clause:

```python
# Find affordable jeans (under $75)
request = vectorsearch_v1beta.QueryDataObjectsRequest(
    parent=f"{parent}/collections/{collection_id}",
    filter={
        "$and": [
            {"category": {"$eq": "Jeans"}},
            {"retail_price": {"$lt": 75}}
        ]
    },
    output_fields=vectorsearch_v1beta.OutputFields(data_fields=["*"]),
)

results = search_client.query_data_objects(request)
print("Jeans under $75:")
for p in results[:5]:
    print(f"  {p.data['name'][:50]}... - ${p.data['retail_price']:.2f}")
```

### Step 7: Hybrid Search with RRF Ranking

Combine semantic + keyword search for best results:

```python
query = "blue denim jeans"

request = vectorsearch_v1beta.BatchSearchDataObjectsRequest(
    parent=f"{parent}/collections/{collection_id}",
    searches=[
        # Semantic search: understands meaning
        vectorsearch_v1beta.Search(
            semantic_search=vectorsearch_v1beta.SemanticSearch(
                search_text=query,
                search_field="name_dense_embedding",
                task_type="RETRIEVAL_QUERY",
                top_k=20,
                output_fields=vectorsearch_v1beta.OutputFields(
                    data_fields=["name", "category", "retail_price"]
                ),
            )
        ),
        # Text search: keyword matching
        vectorsearch_v1beta.Search(
            text_search=vectorsearch_v1beta.TextSearch(
                search_text=query,
                data_field_names=["name"],
                top_k=20,
                output_fields=vectorsearch_v1beta.OutputFields(
                    data_fields=["name", "category", "retail_price"]
                ),
            )
        ),
    ],
    # Combine with Reciprocal Rank Fusion
    combine=vectorsearch_v1beta.BatchSearchDataObjectsRequest.CombineResultsOptions(
        ranker=vectorsearch_v1beta.Ranker(
            rrf=vectorsearch_v1beta.ReciprocalRankFusion(weights=[1.0, 1.0])
        )
    ),
)

results = search_client.batch_search_data_objects(request)

print(f"Hybrid search results for '{query}':")
for i, result in enumerate(results.results[0].results[:5], 1):
    data = result.data_object.data
    print(f"{i}. {data['name'][:55]}...")
    print(f"   {data['category']} | ${data['retail_price']:.2f}")
```

### Step 8: Scale to Production with ANN Index

When ready for production, add an index for billion-scale performance:

```python
request = vectorsearch_v1beta.CreateIndexRequest(
    parent=f"{parent}/collections/{collection_id}",
    index_id="product-name-index",
    index={
        "index_field": "name_dense_embedding",
        "filter_fields": ["category", "retail_price"],
        "store_fields": ["name"],
    },
)

index_operation = vector_search_client.create_index(request)
print("⏳ Creating ANN index (takes a few minutes)...")
index_operation.result()
print("✅ Index ready - now running at production scale!")
```

**The best part?** Your search code doesn't change. Same API, now backed by billion-scale ANN powered by Google's ScaNN algorithm.

### Step 9: Clean Up

**Important**: Delete resources to avoid charges!

```python
# Delete index first
vector_search_client.delete_index(
    name=f"{parent}/collections/{collection_id}/indexes/product-name-index"
)

# Then delete collection (deletes all data objects too)
vector_search_client.delete_collection(
    name=f"{parent}/collections/{collection_id}"
)
print("✅ All resources deleted!")
```

## Key Features Deep Dive

### Auto-Embeddings

No more managing embedding pipelines. Configure once, and VS2.0 handles the rest:

```python
"vertex_embedding_config": {
    "model_id": "text-embedding-004",   # Vertex AI embedding model
    "text_template": "{name}",          # Field to embed
    "task_type": "RETRIEVAL_DOCUMENT"   # Optimization hint
}
```

Supported models: `text-embedding-004`, `text-multilingual-embedding-002`, and multimodal models.

### kNN vs ANN: When to Use Each

| Scenario | Use | Why |
|----------|-----|-----|
| Development & prototyping | kNN | Instant - no index build wait |
| Small datasets (< 10K) | kNN | Fast enough without indexing |
| Production with large data | ANN | Worth the build time for speed |
| Billions of vectors | ANN | Only viable option |

### Storage Tiers

Choose the right cost/performance balance:

| Tier | Backing | Latency | Cost | Best For |
|------|---------|---------|------|----------|
| **Performance** | RAM | Lowest | Higher | Real-time apps, high QPS |
| **Storage** | SSD | Low | Lower | Large datasets, cost-sensitive |

## Migration from Vector Search 1.0

Already using Vector Search? Here's the mapping:

| Vector Search 1.0 | Vector Search 2.0 |
|-------------------|-------------------|
| `MatchingEngineIndex` | `Collection` + `Index` |
| `MatchingEngineIndexEndpoint` | Managed automatically |
| `aiplatform` SDK | `vectorsearch_v1beta` SDK |
| Batch update via GCS | Real-time CRUD |
| Manual scaling config | Auto-scaling |

## Integrations

VS2.0 works with the tools you already use:

- **ADK (Agent Development Kit)**: Build AI agents with VS2.0 as the retrieval backend
- **LangChain**: Native vector store integration
- **LlamaIndex**: Document retrieval and RAG applications
- **MCP Servers**: Connect via Model Context Protocol

## Best Practices

1. **Start with kNN, graduate to ANN**: Prototype without indexes, add them when you need scale
2. **Use auto-embeddings**: Less code, fewer bugs, automatic model updates
3. **Batch for bulk imports**: 100 items per batch, with rate limiting for embedding quotas
4. **Design filters upfront**: Declare `filter_fields` for fields you'll query frequently
5. **Match your distance metric**: Use what your embedding model was trained with
6. **Choose the right tier**: Performance for latency-critical, Storage for cost-sensitive
7. **Clean up resources**: Delete indexes and collections when done to avoid charges

## What's Next?

Vertex AI Vector Search 2.0 is now in **Public Preview**. Get started:

1. **Try the notebook**: [Vector Search 2.0 Introduction](https://github.com/GoogleCloudPlatform/generative-ai/blob/main/embeddings/vector-search-2-intro.ipynb)
2. **Read the docs**: [Vector Search 2.0 Documentation](https://cloud.google.com/vertex-ai/docs/vector-search-2/overview)
3. **Install the SDK**: `pip install google-cloud-vectorsearch`
4. **Join the community**: Share feedback and get help

Vector databases don't have to be complicated. With VS2.0, you can focus on what matters—building great AI applications.

---

## Resources

- [Vector Search 2.0 Documentation](https://cloud.google.com/vertex-ai/docs/vector-search-2/overview)
- [Python SDK Documentation](https://cloud.google.com/python/docs/reference/google-cloud-vectorsearch/latest)
- [Introduction Notebook](https://github.com/GoogleCloudPlatform/generative-ai/blob/main/embeddings/vector-search-2-intro.ipynb)
- [TheLook Dataset](https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce)
- [Google Cloud Console](https://console.cloud.google.com/vertex-ai/vector-search)
- [Pricing](https://cloud.google.com/vertex-ai/pricing)
