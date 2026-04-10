# `app/report_generator.py` — Technical Documentation

---

## 1. Module Overview

`report_generator.py` implements a **Retrieval-Augmented Generation (RAG) pipeline** for producing structured, narrative reports from a corpus of textual reviews. It is the highest-level orchestration module in the application, sitting above the preprocessing, sentiment analysis, and configuration layers.

### Responsibilities

| Responsibility | Description |
|---|---|
| **Corpus construction** | Sentence-tokenizes and embeds all review text into a vector index |
| **Two-stage semantic retrieval** | For each aspect, retrieves candidate sentences via bi-encoder cosine similarity, then re-ranks with a cross-encoder for higher precision |
| **Sentiment aggregation** | Collects per-aspect sentiment labels across all reviews and computes distribution statistics |
| **LLM narrative generation** | Calls an OpenAI chat model to write grounded, evidence-backed narrative sections per aspect |
| **Report assembly** | Combines per-aspect results and an overall summary into a structured report dictionary |
| **Markdown formatting** | Serializes the report dictionary into a human-readable Markdown document |

### Position in the System

```
[Input: list[str] reviews]
        │
        ▼
  preprocessing.py          ← clean_text, get_sentences
        │
        ▼
  sentiment_analyzer.py     ← analyze / async_analyze_batch, embeddings, OpenAI clients
        │
        ▼
  report_generator.py       ← RAG pipeline, LLM narration, report assembly  ◄── THIS MODULE
        │
        ▼
  [Output: report dict / Markdown string]
```

The module exposes both **synchronous** (`generate_report`) and **asynchronous** (`async_generate_report`) entry points to accommodate different runtime environments — a blocking script versus a FastAPI/async web server with Server-Sent Events progress callbacks. Internal helpers are intentionally marked private (prefixed `_`) to keep the public surface minimal.

---

## 2. Key Components

### 2.1 Module-Level State

```python
_reranker_model = None
```

A module-level singleton holding the lazily loaded `CrossEncoder` instance used for re-ranking retrieved candidates. Initialized to `None` on import and populated on first use by `_get_reranker_model()`. This pattern avoids paying the model-loading cost unless retrieval is actually performed, and ensures the model is loaded only once per process.

---

### 2.2 `_get_reranker_model` *(internal)*

```python
def _get_reranker_model() -> CrossEncoder:
```

**Description:**  
Lazy-loading accessor for the cross-encoder re-ranking model. Initializes the module-level `_reranker_model` singleton from `CROSS_ENCODER_MODEL` (from config) on first call; returns the cached instance on all subsequent calls. Follows the same lazy-singleton pattern used for the sentence-transformer model in `sentiment_analyzer.py`.

**Returns:**  
`CrossEncoder` — a `sentence_transformers.CrossEncoder` instance loaded from the configured model name.

**Side Effects:**
- Mutates the module-level `_reranker_model` global on first call.
- Triggers model download and loading from disk on first call (potentially slow; subsequent calls are instantaneous).

---

### 2.3 `build_corpus`

```python
def build_corpus(reviews: list[str]) -> dict:
```

**Description:**  
Transforms a flat list of raw review strings into a searchable embedding corpus. Each review is first cleaned via `clean_text()`, then sentence-tokenized via `get_sentences()`. The concatenated sentence list is then encoded in a single batch call, producing a dense embedding matrix suitable for cosine-similarity search.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `reviews` | `list[str]` | Raw review texts to index |

**Returns:**  
A `dict` with three parallel-array keys:

| Key | Type | Description |
|---|---|---|
| `sentences` | `list[str]` | All sentences extracted from all reviews, in corpus order |
| `review_indices` | `list[int]` | Parallel array mapping each sentence back to its source review (0-indexed) |
| `embeddings` | `np.ndarray` | Shape `(n_sentences, embedding_dim)` — dense float32 embeddings |

**Side Effects / Dependencies:**
- Calls `clean_text()` and `get_sentences()` from `preprocessing.py` for every review.
- Calls `_get_sentence_model()` from `sentiment_analyzer.py`; triggers lazy load of the sentence-transformer on first use.
- Encodes all sentences in a single batch call — efficient but memory usage scales linearly with total sentence count across the corpus.

---

### 2.4 `_retrieve_candidates` *(internal)*

```python
def _retrieve_candidates(aspect: str, corpus: dict, k: int = 30) -> list[dict]:
```

**Description:**  
The **first stage** of the two-stage retrieval pipeline. Encodes the `aspect` string as a query embedding and computes cosine similarity against the entire corpus embedding matrix using the bi-encoder (sentence-transformer). Returns the top-`k` candidate sentences ranked by cosine similarity score.

Bi-encoder retrieval is fast (single matrix multiplication) but less accurate than a cross-encoder at determining true relevance. The larger candidate pool (`k=30` by default) compensates for this by giving the more accurate second stage enough material to work with.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `aspect` | `str` | The aspect label to query (e.g., `"acting"`, `"battery life"`) |
| `corpus` | `dict` | A corpus dict as returned by `build_corpus` |
| `k` | `int` | Maximum number of candidates to retrieve (default: `30`; automatically capped to corpus size) |

**Returns:**  
`list[dict]` — each dict contains:

| Key | Type | Description |
|---|---|---|
| `sentence` | `str` | The retrieved sentence text |
| `review_idx` | `int` | 0-indexed source review number |
| `score` | `float` | Cosine similarity score in `[-1.0, 1.0]` |

Results are sorted in descending cosine-similarity order.

**Side Effects / Dependencies:**
- Calls `_get_sentence_model()` to encode the aspect query vector.
- Uses `sentence_transformers.util.cos_sim` for similarity computation.
- Uses `numpy.argsort` for ranking — O(n) in corpus sentence count.

---

### 2.5 `_rerank_candidates` *(internal)*

```python
def _rerank_candidates(aspect: str, candidates: list[dict], k: int = 10) -> list[dict]:
```

**Description:**  
The **second stage** of the two-stage retrieval pipeline. Accepts a set of candidate sentences produced by `_retrieve_candidates` and re-scores them using a cross-encoder model, which jointly encodes the aspect query and each candidate sentence together. This joint encoding provides substantially higher precision relevance scoring than the independent bi-encoder embeddings, at the cost of being too slow to run across the full corpus.

Returns the top-`k` candidates by cross-encoder score, with the `"score"` field in each result dict overwritten with the cross-encoder score.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `aspect` | `str` | The aspect label, used as the query in each `(query, sentence)` cross-encoder pair |
| `candidates` | `list[dict]` | Candidate sentence dicts from `_retrieve_candidates`; each must have a `"sentence"` key |
| `k` | `int` | Number of top results to return after re-ranking (default: `10`) |

**Returns:**  
`list[dict]` — same shape as input dicts, but with `"score"` overwritten with the cross-encoder relevance score (`float`). Sorted by descending cross-encoder score. Returns an empty list immediately if `candidates` is empty.

**Side Effects / Dependencies:**
- Calls `_get_reranker_model()` — triggers lazy load of `CrossEncoder` on first invocation.
- Calls `model.predict()` on all candidate pairs in a single batch call.
- Defensively handles the case where `model.predict()` returns a `np.ndarray` by converting to a plain Python list before sorting.
- Input dicts are shallow-copied (`dict(c)`) before mutation to avoid modifying the caller's data.

---

### 2.6 `retrieve_for_aspect`

```python
def retrieve_for_aspect(
    aspect: str,
    corpus: dict,
    k: int = 10,
    k_retrieve: int = 30,
) -> list[dict]:
```

**Description:**  
The **public retrieval interface**. Orchestrates the full two-stage retrieval pipeline for a single aspect: first calls `_retrieve_candidates` to gather `k_retrieve` bi-encoder candidates from the corpus, then calls `_rerank_candidates` to re-score and return the top-`k` results by cross-encoder relevance.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `aspect` | `str` | The aspect label to retrieve sentences for |
| `corpus` | `dict` | A corpus dict as returned by `build_corpus` |
| `k` | `int` | Final number of results to return after re-ranking (default: `10`) |
| `k_retrieve` | `int` | Number of bi-encoder candidates to fetch before re-ranking (default: `30`; must be `≥ k`) |

**Returns:**  
`list[dict]` — top-`k` sentence dicts sorted by descending cross-encoder relevance score. Each dict contains `sentence` (`str`), `review_idx` (`int`), and `score` (`float`, cross-encoder score).

**Side Effects / Dependencies:**
- Delegates entirely to `_retrieve_candidates` and `_rerank_candidates`.
- Triggers lazy loading of both the sentence-transformer model and the cross-encoder model on first use.

---

### 2.7 `_compute_distribution` *(internal)*

```python
def _compute_distribution(aspect_results: list[dict]) -> dict:
```

**Description:**  
Aggregates sentiment labels for a single aspect across all reviews into raw counts and percentage breakdowns. Any label not in `{"positive", "negative", "not_mentioned"}` is bucketed into `"not_mentioned"`. Division-by-zero is guarded with a `total = sum or 1` pattern, making the function safe for empty input.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `aspect_results` | `list[dict]` | Records from sentiment analysis output, each expected to carry a `"sentiment"` key with a string value |

**Returns:**  
`dict` with the following structure:

```python
{
    "positive":      {"count": int, "pct": float},  # percentage rounded to 1 decimal
    "negative":      {"count": int, "pct": float},
    "not_mentioned": {"count": int, "pct": float},
}
```

All three keys are always present, even if their count is zero.

---

### 2.8 `generate_aspect_section`

```python
def generate_aspect_section(
    aspect: str,
    retrieved: list[dict],
    distribution: dict,
) -> str:
```

**Description:**  
Synchronously calls the OpenAI Chat Completions API to produce a 2–4 sentence narrative paragraph about a single aspect. The prompt is grounded with the retrieved sentence evidence (including 1-indexed review numbers and relevance scores) and the computed sentiment distribution statistics. The model is explicitly instructed not to fabricate details beyond the provided quotes and to begin directly with findings.

**Prompt structure (embedded in implementation):**
- Declares the aspect under discussion.
- Presents the positive / negative / not-mentioned percentage breakdown.
- Lists all retrieved sentences with `(review #N, relevance X.XX)` attribution.
- Instructs a 2–4 sentence grounded summary, no preamble.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `aspect` | `str` | The aspect being described; embedded verbatim in the prompt |
| `retrieved` | `list[dict]` | Ranked sentence dicts from `retrieve_for_aspect`, each with `review_idx` and `score` keys |
| `distribution` | `dict` | Sentiment distribution dict from `_compute_distribution` |

**Returns:**  
`str` — LLM-generated narrative text, stripped of leading and trailing whitespace.

**Side Effects / Dependencies:**
- Calls `_get_openai_client()` — synchronous OpenAI client singleton from `sentiment_analyzer.py`.
- Makes a **blocking** HTTP request to the OpenAI API; latency is network-dependent.
- Uses `OPENAI_MODEL` and `OPENAI_MAX_TOKENS` from config; temperature is fixed at `0.3` (low randomness for factual consistency).

---

### 2.9 `generate_report`

```python
def generate_report(
    reviews: list[str],
    aspects: list[str] | None = None,
    method: str = "LLM (OpenAI)",
    domain: str = "product",
) -> dict:
```

**Description:**  
The synchronous, end-to-end report generation entry point. Executes a four-step sequential pipeline:

1. **Sentiment analysis** — calls `analyze()` from `sentiment_analyzer.py` on each review serially, collecting per-aspect sentiment labels for every review.
2. **Corpus building** — encodes all review sentences into a vector corpus via `build_corpus()`.
3. **Per-aspect processing** — for each aspect: collects sentiment labels across all reviews, computes distribution statistics, retrieves the top-10 most relevant sentences via the two-stage pipeline, and generates an LLM narrative section.
4. **Overall summary** — constructs a cross-aspect sentiment breakdown and calls OpenAI to produce a 2–3 sentence executive summary.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `reviews` | `list[str]` | Raw review texts to analyze |
| `aspects` | `list[str] \| None` | Aspects to analyze; defaults to `DEFAULT_ASPECTS` from config if `None` or empty |
| `method` | `str` | Sentiment analysis method passed through to `analyze()` (default: `"LLM (OpenAI)"`) |
| `domain` | `str` | Domain label for LLM context passed through to `analyze()` (e.g., `"restaurant"`, `"software"`); default: `"product"` |

**Returns:**  
`dict` with the following structure:

```python
{
    "n_reviews": int,                    # number of input reviews
    "aspects": [
        {
            "name": str,                 # aspect label
            "distribution": {
                "positive":      {"count": int, "pct": float},
                "negative":      {"count": int, "pct": float},
                "not_mentioned": {"count": int, "pct": float},
            },
            "narrative": str,            # LLM-generated 2-4 sentence paragraph
            "top_quotes": [
                {
                    "sentence": str,
                    "review": int,       # 1-indexed review number
                },
                # up to 5 entries (top 5 of the retrieved 10)
            ],
        },
        # one dict per aspect
    ],
    "overall_summary": str,             # LLM-generated 2-3 sentence cross-aspect summary
}
```

**Side Effects / Dependencies:**
- Makes `len(reviews) + len(aspects) + 1` OpenAI API calls in total, all blocking and serial. For large corpora or many aspects this can be slow.
- Encodes the full corpus once; encoding time scales linearly with total sentence count.
- Triggers lazy loading of both the sentence-transformer model and the cross-encoder model.
- `method` controls the sentiment analysis backend (e.g., local model vs. LLM).
- `domain` provides LLM context for more accurate aspect-level sentiment classification.

---

### 2.10 `async_generate_aspect_section`

```python
async def async_generate_aspect_section(
    aspect: str,
    retrieved: list[dict],
    distribution: dict,
) -> str:
```

**Description:**  
Async counterpart to `generate_aspect_section`. Functionally identical in terms of prompt construction, model parameters, and output format — but uses the async OpenAI client obtained from `_get_async_openai_client
