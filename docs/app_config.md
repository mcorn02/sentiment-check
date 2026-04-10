# `app/config.py` — Module Documentation

---

## 1. Module Overview

**File:** `app/config.py`
**Docstring:** *Configuration management and API key loading.*

`config.py` serves as the **centralized configuration hub** for the application. It is responsible for:

- **Loading environment variables** from a `.env` file at startup (via `python-dotenv`).
- **Defining application-wide constants** for model selection, classification thresholds, and default analytical parameters.
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

#### `DEFAULT_NLI_THRESHOLD`

```python
DEFAULT_NLI_THRESHOLD: float = 0.55
```

**Description:**
The default confidence threshold for **Natural Language Inference (NLI)**-based classification decisions. Predictions with a confidence score below this threshold may be discarded or treated as inconclusive by the consuming pipeline.

| Attribute | Value |
|---|---|
| Type | `float` |
| Range | `0.0` – `1.0` |
| Default | `0.55` |

---

#### `DEFAULT_ZSC_THRESHOLD`

```python
DEFAULT_ZSC_THRESHOLD: float = 0.6
```

**Description:**
The default confidence threshold for **Zero-Shot Classification (ZSC)** decisions. Operates similarly to `DEFAULT_NLI_THRESHOLD` but applies specifically to the zero-shot classification pipeline.

| Attribute | Value |
|---|---|
| Type | `float` |
| Range | `0.0` – `1.0` |
| Default | `0.60` |

> **Note:** `DEFAULT_ZSC_THRESHOLD` is intentionally set slightly higher than `DEFAULT_NLI_THRESHOLD`, reflecting the expectation that zero-shot predictions should meet a stricter confidence bar before being acted upon.

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

#### `ZERO_SHOT_MODEL`

```python
ZERO_SHOT_MODEL: str = "typeform/distilbert-base-uncased-mnli"
```

**Description:**
Identifier for the **zero-shot classification** model used to classify text into arbitrary label categories without task-specific training data. This model powers the ZSC pipeline governed by `DEFAULT_ZSC_THRESHOLD`.

| Attribute | Value |
|---|---|
| Type | `str` |
| Model Source | [Hugging Face — `typeform/distilbert-base-uncased-mnli`](https://huggingface.co/typeform/distilbert-base-uncased-mnli) |
| Characteristics | DistilBERT-based, trained on MNLI; efficient for zero-shot inference |

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

The current version of this module introduces two meaningful changes relative to the previously documented version: the **replacement of `DEFAULT_ASPECTS`** content with domain-agnostic categories, and the **addition of `MOVIE_ASPECTS`** as a legacy-designated constant.

### What Was Added

```diff
+# General-purpose default aspects (domain-agnostic)
 DEFAULT_ASPECTS = [
-    "acting_performances",
-    "story_plot",
-    "pacing",
-    "visuals",
-    "directing",
-    "writing",
+    "quality",
+    "value",
+    "service",
+    "features",
+    "reliability",
+    "usability",
 ]

+# Legacy movie aspects (used by IMDB endpoint)
+MOVIE_ASPECTS = [
+    "acting_performances",
+    "story_plot",
+    "pacing",
+    "visuals",
+    "directing",
+    "writing",
+]
```

### What Was Changed

**`DEFAULT_ASPECTS` — content replaced entirely.**
The six film-specific aspect strings (`acting_performances`, `story_plot`, `pacing`, `visuals`, `directing`, `writing`) have been replaced with six domain-agnostic strings (`quality`, `value`, `service`, `features`, `reliability`, `usability`). The constant name, type, and length are unchanged; only the string values differ.

**`MOVIE_ASPECTS` — new constant introduced.**
The former contents of `DEFAULT_ASPECTS` have been preserved in a new constant, `MOVIE_ASPECTS`, annotated as the legacy set used specifically by the IMDB endpoint. This ensures that any existing code targeting the IMDB endpoint is not broken by the generalization of `DEFAULT_ASPECTS`, provided it is updated to reference `MOVIE_ASPECTS` explicitly.

### Why the Change Matters Functionally

- **Broadened applicability:** The previous `DEFAULT_ASPECTS` values were inherently film-centric, limiting the usefulness of the application's default analysis path to media review contexts. The new values (`quality`, `value`, `service`, etc.) are meaningful across a wide range of product and service domains — e-commerce, SaaS, hospitality, and more — making the application's default behavior suitable for general-purpose review analysis without caller customization.
- **Backward compatibility preserved:** Rather than simply overwriting the film-specific aspects and silently breaking IMDB endpoint consumers, the original values are retained under `MOVIE_ASPECTS`. Code that explicitly targeted movie-domain analysis can be updated to import `MOVIE_ASPECTS` instead of `DEFAULT_ASPECTS` without any loss of functionality.
- **Intent made explicit via naming and comments:** The addition of inline comments (`# General-purpose default aspects (domain-agnostic)` and `# Legacy movie aspects (used by IMDB endpoint)`) makes the purpose and lifecycle status of each constant immediately clear to future maintainers without requiring them to inspect consuming code.

### Behavioral Differences From Before

| Aspect | Before | After |
|---|---|---|
| `DEFAULT_ASPECTS` values | Film-specific (`acting_performances`, etc.) | Domain-agnostic (`quality`, `value`, etc.) |
| `DEFAULT_ASPECTS` length | 6 | 6 (unchanged) |
| `MOVIE_ASPECTS` constant | Not present | Available as `app.config.MOVIE_ASPECTS` |
| IMDB endpoint aspect source | `DEFAULT_ASPECTS` (implicit) | Should be updated to use `MOVIE_ASPECTS` (explicit, legacy-designated) |
| General-purpose pipelines | Would receive film-specific aspects by default | Now receive domain-agnostic aspects by default |
| Public API surface | `DEFAULT_ASPECTS` only | Extended with `MOVIE_ASPECTS` |

> ⚠️ **Breaking change risk:** Any consumer that imported `DEFAULT_ASPECTS` and expected to receive film-specific aspect strings will now receive the domain-agnostic set instead. Code paths serving the IMDB endpoint or other film-analysis features **must be updated** to import `MOVIE_ASPECTS` in place of `DEFAULT_ASPECTS`. This is a **breaking change** for any consumer relying on the prior string content of `DEFAULT_ASPECTS`.

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
| Zero-shot classification wrappers | `ZERO_SHOT_MODEL`, `DEFAULT_ZSC_THRESHOLD` |
| NLI-based
