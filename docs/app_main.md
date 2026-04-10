# `app/main.py` — Module Documentation

## 1. Module Overview

`app/main.py` serves as the **primary entry point** for the `product_reviewer` application. It orchestrates all user-facing interaction modes — both a command-line interface (CLI) and a web server — and ties together the application's core subsystems: dataset loading, sentiment analysis, and report generation.

### Responsibilities

- **CLI argument parsing**: Exposes all configurable parameters (review source, aspects, analysis method, etc.) via `argparse`.
- **Dataset ingestion**: Supports loading IMDB-style CSV datasets either from a local file path or by downloading from Kaggle via `kagglehub`.
- **Single-review analysis**: Accepts review text directly (inline string or file), runs aspect-based sentiment analysis, and prints results to stdout.
- **Batch testing**: Iterates over the first *N* reviews of a loaded dataset and prints per-review results.
- **Web server launch**: Delegates HTTP API serving to a FastAPI/Uvicorn stack when `--web` is specified.

### Position in the System

```
User (CLI / shell)
        │
        ▼
  app/main.py          ← this module
  ├── app/config.py             (DEFAULT_ASPECTS constant)
  ├── app/sentiment_analyzer.py (analyze())
  ├── app/report_generator.py   (generate_report(), format_report_markdown())
  └── api/main.py               (FastAPI app, launched via uvicorn)
```

---

## 2. Key Components

### 2.1 Module-Level Imports & Optional Dependencies

```python
import kagglehub   # optional — set to None if not installed
```

`kagglehub` is wrapped in a `try/except ImportError` block so the module remains fully functional without it; Kaggle-download features are simply unavailable if the package is absent. `uvicorn` is imported lazily inside `main()` only when `--web` is passed, avoiding a hard dependency for CLI-only users.

---

### 2.2 `load_dataset_kaggle`

```python
def load_dataset_kaggle(
    dataset_name: str = "lakshmi25npathi/imdb-dataset-of-50k-movie-reviews"
) -> pd.DataFrame | None
```

**Purpose**: Downloads a Kaggle dataset using `kagglehub` and loads the first discovered IMDB-named CSV file into a `pandas.DataFrame`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dataset_name` | `str` | `"lakshmi25npathi/imdb-dataset-of-50k-movie-reviews"` | Kaggle dataset slug in `owner/dataset-name` format. |

**Returns**: A `pd.DataFrame` on success, or `None` if:
- `kagglehub` is not installed.
- The download raises any exception.
- No CSV file whose name contains `'IMDB'` is found anywhere in the downloaded directory tree.

**Side Effects**:
- Prints progress and status messages to stdout.
- Triggers a network download to the local `kagglehub` cache directory.
- Walks the downloaded directory tree with `os.walk` to locate the target CSV.

**Dependencies**: `kagglehub`, `os`, `pandas`

---

### 2.3 `load_dataset_manual`

```python
def load_dataset_manual(file_path: str) -> pd.DataFrame | None
```

**Purpose**: Loads a local CSV file into a `pandas.DataFrame` using `latin-1` encoding.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | — | Absolute or relative path to a CSV file. |

**Returns**: A `pd.DataFrame` on success, or `None` if:
- The file does not exist at `file_path`.
- Reading the file raises any exception.

**Side Effects**:
- Prints progress or error messages to stdout.
- Reads from the local filesystem.

**Dependencies**: `os`, `pandas`

---

### 2.4 `analyze_review_cli`

```python
def analyze_review_cli(review: str, aspects: list, method: str) -> None
```

**Purpose**: Runs aspect-based sentiment analysis on a single review text and pretty-prints the structured results table to stdout.

| Parameter | Type | Description |
|-----------|------|-------------|
| `review` | `str` | The full text of the review to analyze. |
| `aspects` | `list` | List of aspect label strings to evaluate (e.g., `["acting", "plot", "visuals"]`). |
| `method` | `str` | The analysis backend to use — currently only `"LLM (OpenAI)"` is accepted. |

**Returns**: `None`

**Side Effects**:
- Prints a formatted header block, the review text, a separator line, and a tabular results DataFrame to stdout.
- Delegates to `app.sentiment_analyzer.analyze()`, which may make external API calls to OpenAI. Network latency and API availability affect execution time.

**Output format** (stdout):
```
Analyzing review using <method>...
Aspects: <aspect1>, <aspect2>, ...

Review:
<review text>

--------------------------------------------------------------------------------

Results:
<DataFrame table>
```

**Dependencies**: `app.sentiment_analyzer.analyze`

---

### 2.5 `main`

```python
def main() -> None
```

**Purpose**: Root entry point for the application. Parses all CLI arguments and dispatches to the appropriate execution mode: web server launch, batch dataset testing, single-review analysis, or help display.

**Returns**: `None`

**Raises / Exits**: Calls `sys.exit(1)` on unrecoverable errors, including:
- A `--file` path that cannot be read.
- `--test` specified without a loadable dataset.

#### Argument Reference

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--web` | flag | `False` | Launch the FastAPI/Uvicorn web server. |
| `--port` | `int` | `8000` | TCP port for the web server. |
| `--review` | `str` | `None` | Inline review text to analyze directly. |
| `--file` | `str` | `None` | Path to a plain-text file containing the review. |
| `--dataset` | `str` | `None` | Path to a local IMDB-format CSV dataset. |
| `--dataset-kaggle` | flag | `False` | Download the IMDB dataset from Kaggle via `kagglehub`. |
| `--aspects` | `str...` | `DEFAULT_ASPECTS` | One or more aspect labels to analyze (space-separated). |
| `--method` | `str` | `"LLM (OpenAI)"` | Analysis method. Currently only `"LLM (OpenAI)"` is accepted. |
| `--test` | `int` | `None` | Run analysis on the first N reviews of the loaded dataset. |

#### Execution Modes (evaluated in priority order)

1. **Web server** (`--web`): Lazily imports `uvicorn` and starts it pointing at `api.main:app` on `0.0.0.0:<port>` with `reload=True`. Control returns after server shutdown.
2. **Batch test** (`--test N`): Requires `--dataset` or `--dataset-kaggle` to produce a valid DataFrame. Iterates over the first N rows of the `'review'` column, calling `analyze_review_cli` for each. Exits after completion.
3. **Single review** — evaluated by sub-priority:
   - `--review`: Uses the inline string directly.
   - `--file`: Reads the file contents as the review text.
   - `--dataset` / `--dataset-kaggle` (without `--test`): Uses `df['review'].iloc[0]` (first row) and prints a reminder to use `--test N` for multiple reviews.
4. **No input**: Prints argparse help text plus hand-written usage examples, then returns normally.

**Side Effects**:
- Prints extensively to stdout throughout all modes.
- May call `sys.exit(1)` on fatal input errors.
- Imports `uvicorn` lazily (only when `--web` is specified).

**Dependencies**: `argparse`, `sys`, `uvicorn` (optional/lazy), `app.config.DEFAULT_ASPECTS`, `load_dataset_kaggle`, `load_dataset_manual`, `analyze_review_cli`

---

## 3. What Changed

This section documents the change introduced in the current diff relative to the previous version of the file.

### 3.1 Removed: `"Zero-shot NLI (local)"` Analysis Method

**Before**:

```python
parser.add_argument(
    "--method",
    choices=["LLM (OpenAI)", "Zero-shot NLI (local)"],
    default="LLM (OpenAI)",
    help="Analysis method to use"
)
```

**After**:

```python
parser.add_argument(
    "--method",
    choices=["LLM (OpenAI)"],
    default="LLM (OpenAI)",
    help="Analysis method to use"
)
```

#### What Was Removed

The `"Zero-shot NLI (local)"` option has been removed from the `--method` argument's `choices` list. This was one of two supported analysis backends; it presumably ran a local Natural Language Inference model (e.g., a Hugging Face zero-shot classification pipeline) without requiring any external API credentials or network access.

#### Why It Matters Functionally

This is a **breaking change** for any user or script that previously invoked the application with `--method "Zero-shot NLI (local)"`. `argparse` enforces the `choices` constraint at parse time, so passing this value will now result in an immediate error:

```
error: argument --method: invalid choice: 'Zero-shot NLI (local)'
      (choose from 'LLM (OpenAI)')
```

The application now has **only one supported analysis method**: `"LLM (OpenAI)"`. Since the default is also `"LLM (OpenAI)"`, users who did not explicitly pass `--method` are unaffected. However, users who:
- Relied on offline/local analysis without an OpenAI API key, or
- Scripted the `--method "Zero-shot NLI (local)"` flag explicitly,

will need to update their workflows. The local inference path is no longer accessible through the CLI regardless of whether the underlying `sentiment_analyzer` module still supports it internally.

#### Behavioral Differences

| Scenario | Before | After |
|----------|--------|-------|
| `--method "LLM (OpenAI)"` | Works | Works (unchanged) |
| `--method "Zero-shot NLI (local)"` | Works, uses local NLI model | **Fails with argparse error** |
| No `--method` flag | Defaults to `"LLM (OpenAI)"` | Defaults to `"LLM (OpenAI)"` (unchanged) |
| Offline usage without OpenAI key | Possible via NLI method | **No longer possible via CLI** |

---

## 4. Dependencies & Integration

### 4.1 Standard Library

| Module | Usage |
|--------|-------|
| `argparse` | Full CLI argument definition, parsing, and help generation |
| `os` | File existence checks (`os.path.exists`), directory tree traversal (`os.walk`), path joining |
| `sys` | `sys.exit(1)` on unrecoverable errors |

### 4.2 Third-Party (Required)

| Package | Usage |
|---------|-------|
| `pandas` | Loading CSV files into DataFrames, extracting review columns, displaying results via `.to_string()` |

### 4.3 Third-Party (Optional / Lazy)

| Package | Import Condition | Usage |
|---------|-----------------|-------|
| `kagglehub` | Module-level `try/except`; set to `None` if absent | Kaggle dataset download in `load_dataset_kaggle` |
| `uvicorn` | Imported inside `main()` only when `--web` is passed | ASGI server that hosts the FastAPI application |

### 4.4 Internal Imports

| Module | Symbols Imported | Role in This File |
|--------|-----------------|-------------------|
| `app.config` | `DEFAULT_ASPECTS` | Provides the default aspect list for `--aspects` argument |
| `app.sentiment_analyzer` | `analyze` | Core sentiment analysis logic called by `analyze_review_cli` |
| `app.report_generator` | `generate_report`, `format_report_markdown` | Report generation utilities; imported but not directly invoked in the current CLI/batch paths — available for future use or consumed via the web API path |

### 4.5 What Depends on This Module

| Consumer | How It Uses `main.py` |
|----------|-----------------------|
| `if __name__ == "__main__"` block | Direct script execution via `python app/main.py` |
| Package `__main__.py` (if present) | Enables `python -m app` invocation |
| Shell scripts / CI pipelines | Invoked as `python -m app.main [args]` |
| `api/main.py` | Referenced indirectly — `main.py` launches it via Uvicorn but does not import from it; the dependency is one-directional |

---

`FUNCTIONAL_CHANGE: YES`
