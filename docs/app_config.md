# `app/config.py` — Module Documentation

---

## 1. Module Overview

**File:** `app/config.py`
**Docstring:** *Configuration management and API key loading.*

`config.py` serves as the **centralized configuration hub** for the application. It is responsible for:

- **Loading environment variables** from a `.env` file at startup (via `python-dotenv`).
- **Defining application-wide constants** for model selection and default analytical parameters.
- **Providing secure access** to sensitive credentials (e.g., the OpenAI API key) through a guarded accessor function that fails fast with a clear error message if the key is absent.

Within the system architecture, this module sits at the **foundation layer** — it has no dependencies on other internal application modules and is expected to be imported by any component that requires configuration values, model identifiers, or API credentials. Because it calls `load_dotenv()` at import time, importing this module is a side-effectful operation and should occur early in the application lifecycle.

---

## 2. Key Components

### Constants

---

#### `DEFAULT_ASPECTS`

```python
DEFAULT_ASPECTS: list[str] = [
    "quality",
    "value",
    "service",
    "features",
    "reliability",
    "usability",
]
```

**Description:**
A list of **general-purpose, domain-agnostic** aspect categories used as the default facets during sentiment and aspect-based analysis. These represent the broad dimensions of a subject that the application evaluates when no custom aspects are provided by the caller. Unlike the legacy `MOVIE_ASPECTS`, these aspects are designed to apply meaningfully across diverse product and service domains.

| Attribute | Value |
|---|---|
| Type | `list[str]` |
| Default Count | 6 aspects |
| Usage Context | General-purpose sentiment/aspect-based analysis pipelines |

**Aspects defined:**

| Aspect | Description |
|---|---|
| `quality` | Overall caliber and standard of the subject |
| `value` | Cost-to-benefit ratio and perceived worth |
| `service` | Customer support, responsiveness, and care |
| `features` | Capabilities, functionality, and feature set |
| `reliability` | Consistency, dependability, and uptime |
| `usability` | Ease of use, accessibility, and user experience |

---

#### `MOVIE_ASPECTS`

```python
MOVIE_ASPECTS: list[str] = [
    "acting_performances",
    "story_plot",
    "pacing",
    "visuals",
    "directing",
    "writing",
]
```

**Description:**
A list of **film-specific** aspect categories retained for backward compatibility with the legacy IMDB endpoint. These represent the domain-specific facets of a movie or media piece that the application can analyze. This constant is considered **legacy** — new general-purpose code should prefer `DEFAULT_ASPECTS`.

| Attribute | Value |
|---|---|
| Type | `list[str]` |
| Default Count | 6 aspects |
| Usage Context | Legacy IMDB endpoint; film/media sentiment analysis |
| Status | Legacy — superseded by `DEFAULT_ASPECTS` for new consumers |

**Aspects defined:**

| Aspect | Description |
|---|---|
| `acting_performances` | Quality and believability of performances |
| `story_plot` | Narrative structure and coherence |
| `pacing` | Rhythm and flow of the content |
| `visuals` | Cinematography, visual effects, or aesthetics |
| `directing` | Directorial choices and execution |
| `writing` | Script quality, dialogue, and storytelling craft |

> **Note:** `MOVIE_ASPECTS` is preserved for backward compatibility with the IMDB endpoint. New pipelines and endpoints should use `DEFAULT_ASPECTS` unless film-specific categorization is explicitly required.

---

#### `SENTENCE_TRANSFORMER_MODEL`

```python
SENTENCE_TRANSFORMER_MODEL: str = "all-MiniLM-L6-v2"
```

**Description:**
Identifier for the **Sentence Transformer** model used to generate dense vector embeddings for semantic similarity tasks. Centralizing this identifier ensures that upgrading or swapping the embedding model requires a change in only one location.

| Attribute | Value |
|---|---|
| Type | `str` |
| Model Source | [Hugging Face — `sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |
| Characteristics | Lightweight, fast, 384-dimensional embeddings |

---

#### `CROSS_ENCODER_MODEL`

```python
CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
```

**Description:**
Identifier for the **Cross-Encoder** model used for re-ranking or precise relevance scoring between text pairs. Unlike bi-encoders (such as `SENTENCE_TRANSFORMER_MODEL`), a cross-encoder jointly processes both input texts together, producing a single relevance score rather than independent embeddings. This makes it more accurate for ranking tasks at the cost of higher inference latency.

| Attribute | Value |
|---|---|
| Type | `str` |
| Model Source | [Hugging Face — `cross-encoder/ms-marco-MiniLM-L-6-v2`](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2) |
| Characteristics | Trained on MS MARCO passage ranking dataset; optimized for relevance scoring between query-document pairs |
| Typical Usage | Re-ranking candidate passages retrieved by a bi-encoder in a retrieval pipeline |

> **Architectural note:** In a typical two-stage retrieval system, `SENTENCE_TRANSFORMER_MODEL` (bi-encoder) performs fast approximate candidate retrieval, and `CROSS_ENCODER_MODEL` then re-ranks those candidates with higher precision. The two constants are designed to work in tandem.

---

#### `OPENAI_MODEL`

```python
OPENAI_MODEL: str = "gpt-4o-mini"
```

**Description:**
The OpenAI model identifier used for all calls to the OpenAI API. Centralizing this value ensures that switching model versions requires a change in only one location rather than across every API call site.

| Attribute | Value |
|---|---|
| Type | `str` |
| Default Model | `gpt-4o-mini` |

---

#### `OPENAI_MAX_TOKENS`

```python
OPENAI_MAX_TOKENS: int = 350
```

**Description:**
The maximum number of tokens the OpenAI model is permitted to generate in a single API response. Acts as a cost-control and latency-management guardrail, preventing runaway generation from unexpectedly large or open-ended completions.

| Attribute | Value |
|---|---|
| Type | `int` |
| Default | `350` tokens |

---

### Functions

---

#### `get_openai_api_key`

```python
def get_openai_api_key() -> str:
```

**Description:**
Retrieves the OpenAI API key from the runtime environment. Reads the `OPENAI_API_KEY` environment variable, which may have been populated either by the shell environment or by the `.env` file loaded at module import time. Implements a **fail-fast** pattern — raises immediately on absence rather than returning `None` or a sentinel value, making misconfiguration obvious at the point of access rather than producing a cryptic downstream failure.

**Parameters:**
None.

**Returns:**

| Type | Description |
|---|---|
| `str` | The OpenAI API key string if present and non-empty |

**Raises:**

| Exception | Condition |
|---|---|
| `ValueError` | Raised when `OPENAI_API_KEY` is not set or resolves to an empty/falsy string |

**Error message on failure:**
```
OpenAI API key not found. Please set OPENAI_API_KEY environment variable
or add it to a .env file in the project root.
```

**Side Effects:**
- Reads from the process environment via `os.getenv()`.
- No writes or mutations occur.

**Usage Example:**
```python
from app.config import get_openai_api_key

try:
    api_key = get_openai_api_key()
    # Use api_key to initialize OpenAI client
except ValueError as e:
    print(f"Configuration error: {e}")
```

**Design Notes:**
- The function is safe to call at module load time in dependent modules; it will only raise if the key is genuinely absent.
- The falsy check (rather than an explicit `is None` guard) also catches the edge case of `OPENAI_API_KEY` being set to an empty string, which `os.getenv()` would return as `""` rather than `None`.

---

### Module-Level Side Effects

#### `load_dotenv()` (called at import time)

```python
load_dotenv()
```

This call executes **when the module is first imported**. It searches for a `.env` file starting from the current working directory and traverses upward, loading any found key-value pairs into `os.environ`. If no `.env` file is found, the call is a no-op — it does not raise an error.

**Implication:** Any module that imports from `app.config` will trigger environment variable loading as a side effect. This is generally desirable and expected for applications using `python-dotenv`, but it should be accounted for in test environments where environment isolation is required (e.g., by patching `os.environ` or using a test-specific `.env` file).

---

## 3. What Changed

This commit removes two categories of constants that were previously part of the module's public API: **classification thresholds** and the **zero-shot classification model identifier**. The current state of the module reflects a narrowed, cleaner configuration surface focused solely on the models and parameters that remain actively in use.

### What Was Removed

#### Default Classification Thresholds

```diff
-# Default thresholds
-DEFAULT_NLI_THRESHOLD = 0.55
-DEFAULT_ZSC_THRESHOLD = 0.6
```

Two numeric threshold constants have been deleted:

| Removed Constant | Former Value | Former Purpose |
|---|---|---|
| `DEFAULT_NLI_THRESHOLD` | `0.55` | Confidence cutoff for Natural Language Inference (NLI) classification decisions |
| `DEFAULT_ZSC_THRESHOLD` | `0.60` | Confidence cutoff for Zero-Shot Classification (ZSC) decisions |

These constants governed the minimum confidence scores required for a classification result to be accepted as valid. Any pipeline component that imported and used these values will no longer find them in `app.config` after this change.

#### Zero-Shot Classification Model Identifier

```diff
-ZERO_SHOT_MODEL = "typeform/distilbert-base-uncased-mnli"
```

The identifier for the zero-shot classification model has been removed. This model — a DistilBERT variant fine-tuned on the MNLI dataset and hosted on Hugging Face — was previously used for zero-shot text classification tasks. Its removal from the configuration implies that the zero-shot classification code path has been retired, refactored, or migrated to an alternative approach that no longer requires a dedicated model constant in this module.

---

### Why the Changes Matter Functionally

**Removal of `DEFAULT_NLI_THRESHOLD` and `DEFAULT_ZSC_THRESHOLD`:**
These thresholds were decision-boundary values — removing them does not merely change a label or comment, but eliminates configuration that actively influenced classification outcomes. Any consuming code that referenced these constants to gate or filter classification results must now either define its own threshold values locally, receive them as parameters, or have been removed alongside the classification logic that depended on them. If any code paths silently fall back to `None` or `0` in the absence of these values, the behavioral impact could be significant (e.g., accepting all classification results regardless of confidence, or rejecting all of them).

**Removal of `ZERO_SHOT_MODEL`:**
The zero-shot classification model identifier being removed strongly suggests that the NLI/ZSC-based classification pipeline has been deprecated or removed from the application. Previously, the co-presence of `DEFAULT_NLI_THRESHOLD`, `DEFAULT_ZSC_THRESHOLD`, and `ZERO_SHOT_MODEL` formed a coherent configuration group for a specific classification subsystem. With all three now absent, that subsystem appears to have been fully retired from the configuration layer.

---

### Behavioral Differences From Before

| Aspect | Before | After |
|---|---|---|
| `DEFAULT_NLI_THRESHOLD` | Available as `app.config.DEFAULT_NLI_THRESHOLD` (`0.55`) | **Removed** — `AttributeError` if accessed |
| `DEFAULT_ZSC_THRESHOLD` | Available as `app.config.DEFAULT_ZSC_THRESHOLD` (`0.60`) | **Removed** — `AttributeError` if accessed |
| `ZERO_SHOT_MODEL` | Available as `app.config.ZERO_SHOT_MODEL` (`"typeform/distilbert-base-uncased-mnli"`) | **Removed** — `AttributeError` if accessed |
| NLI/ZSC classification configuration | Centrally managed in `app.config` | No longer present in the configuration layer |
| Public API surface | 8 exported names (5 constants + 2 threshold values + 1 function) | Reduced to 6 exported names (5 constants + 1 function) |

> ⚠️ **Breaking change:** Any module that imports `DEFAULT_NLI_THRESHOLD`, `DEFAULT_ZSC_THRESHOLD`, or `ZERO_SHOT_MODEL` from `app.config` will raise an `ImportError` (for direct name imports) or `AttributeError` (for attribute-style access) after this change. All consumers of these constants must be updated or removed.

---

## 4. Dependencies & Integration

### External Dependencies

| Import | Package | Purpose |
|---|---|---|
| `os` | Python standard library | Access to environment variables via `os.getenv()` |
| `load_dotenv` | `python-dotenv` | Loads `.env` file contents into `os.environ` at import time |

### Internal Dependencies

None. `app/config.py` does **not** import from any other internal application module, making it a true leaf-level dependency in the project's import graph. It is safe to import from anywhere in the codebase without risk of circular imports.

### What Depends On This Module

Any application component that requires one or more of the following should import from `app.config`:

| Consumer Type | Constants / Functions Used |
|---|---|
| Sentence embedding and semantic search modules | `SENTENCE_TRANSFORMER_MODEL` |
| Re-ranking and relevance scoring modules | `CROSS_ENCODER_MODEL` |
| LLM-based analysis modules | `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `get_openai_api_key()` |
| Default aspect consumers (general-purpose) | `DEFAULT_ASPECTS` |
| Legacy IMDB / film-analysis endpoints | `MOVIE_ASPECTS` |

> **Note for maintainers:** Consumers that previously imported `DEFAULT_NLI_THRESHOLD`, `DEFAULT_ZSC_THRESHOLD`, or `ZERO_SHOT_MODEL` must be audited and updated. These constants no longer exist in the module and their removal indicates that the NLI/ZSC classification subsystem has been retired from the configuration layer. Verify that no active code paths reference these removed names before deploying this change.

---

`FUNCTIONAL_CHANGE: YES`
