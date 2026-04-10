# `inference/run_inference_on_gold.py` — Technical Documentation

---

## 1. Module Overview

### Purpose

`run_inference_on_gold.py` is a **batch inference script** designed to run aspect-level sentiment analysis over a gold (ground-truth) evaluation dataset. It applies an LLM-based sentiment classifier to each review in the dataset and writes predicted sentiment labels back into the source DataFrame, which is then persisted as a CSV file for downstream evaluation.

### Responsibilities

- Load a gold-standard aspect-level sentiment dataset from disk.
- Iterate over reviews grouped by `review_id`, applying LLM-based aspect sentiment inference to each.
- Map predicted sentiments back to individual aspect-level rows in the DataFrame.
- Periodically checkpoint results to disk to guard against data loss during long-running inference jobs.
- Handle inference errors gracefully, substituting an `"error"` sentinel value rather than halting execution.

### Position in the System

This script lives in the `inference/` directory and acts as a **one-off evaluation runner** — it is not part of the live application stack. It bridges the `app/` layer (specifically `sentiment_analyzer` and `config`) with offline evaluation workflows. The output file (`predictions.csv`) is intended to be consumed by evaluation or analysis scripts that compare `llm_sentiment` predictions against gold-standard labels.

```
project root/
├── app/
│   ├── sentiment_analyzer.py   ← provides llm_aspect_sentiment
│   └── config.py               ← provides DEFAULT_ASPECTS
├── data/
│   └── gold_dataset_aspect_level - gold_dataset_aspect_level.csv  ← input
├── inference/
│   └── run_inference_on_gold.py  ← this script
└── predictions.csv               ← output (written by this script)
```

---

## 2. Key Components

### Module-Level Initialization

The script performs several operations at import/execution time that are not wrapped in functions:

#### Dataset Loading

```python
df = pd.read_csv('data/gold_dataset_aspect_level - gold_dataset_aspect_level.csv')
```

- Loads the gold evaluation dataset into a Pandas DataFrame.
- **Expected columns**: `review_id`, `review`, `aspect`, and any existing label columns.
- **Side effect**: Reads from the filesystem relative to the current working directory (not relative to the script location). The script must be executed from the project root.

#### Review Grouping

```python
grouped = df.groupby('review_id')
total = len(grouped)
```

- Groups the DataFrame by `review_id` so that all aspect rows belonging to the same review are processed together in a single LLM call.
- `total` is used for progress logging.

#### Main Inference Loop

```python
for i, (review_id, group) in enumerate(grouped):
    ...
```

Iterates over each unique review. For each review:

1. Extracts the review text from the first row of the group (`group.iloc[0]['review']`).
2. Uses `DEFAULT_ASPECTS` as the set of aspects to evaluate.
3. Calls `llm_aspect_sentiment` and converts results to a dictionary.
4. Writes the predicted sentiment for each aspect back into `df` via `df.loc[idx, "llm_sentiment"]`.
5. On error, fills all aspects for that review with `"error"`.
6. Checkpoints to `predictions.csv` every 10 reviews.

**Side effects**:
- Mutates `df` in-place by adding/updating the `"llm_sentiment"` column.
- Writes `predictions.csv` to the working directory periodically and unconditionally at the end.
- Prints progress and error messages to stdout.

---

### Function: `results_to_dict`

```python
def results_to_dict(results_list: list) -> dict:
    return {r["aspect"]: r["sentiment"] for r in results_list}
```

#### Description

Converts the list-of-dicts output format returned by `llm_aspect_sentiment` into a flat dictionary keyed by aspect name. This makes it straightforward to look up a predicted sentiment for any given aspect string.

#### Parameters

| Parameter      | Type   | Description                                                                                     |
|----------------|--------|-------------------------------------------------------------------------------------------------|
| `results_list` | `list` | A list of dictionaries, each containing at minimum an `"aspect"` key and a `"sentiment"` key. |

#### Returns

| Type   | Description                                                                          |
|--------|--------------------------------------------------------------------------------------|
| `dict` | A dictionary mapping each aspect string to its predicted sentiment label (e.g., `{"food": "positive", "service": "negative"}`). |

#### Example

```python
results = [
    {"aspect": "food", "sentiment": "positive"},
    {"aspect": "service", "sentiment": "neutral"}
]
results_to_dict(results)
# → {"food": "positive", "service": "neutral"}
```

#### Notes

- Assumes each element of `results_list` has both `"aspect"` and `"sentiment"` keys; missing keys will raise a `KeyError`.
- If duplicate aspect keys exist, the last occurrence wins (standard dict comprehension behavior).
- No side effects.

---

### Constants / Imported Configuration

#### `DEFAULT_ASPECTS`

```python
from app.config import DEFAULT_ASPECTS
```

- Imported from `app.config`.
- Defines the fixed list/set of aspects that every review is evaluated against during inference.
- Used as the `aspects` argument to `llm_aspect_sentiment`.
- Not modified by this script.

---

## 3. What Changed

### Summary of the Diff

This commit **removes NLI (Natural Language Inference) model inference** from the batch evaluation pipeline, leaving only LLM-based inference active.

### Specific Changes

#### Import Removal

```diff
-from app.sentiment_analyzer import llm_aspect_sentiment, nli_aspect_sentiment
+from app.sentiment_analyzer import llm_aspect_sentiment
```

`nli_aspect_sentiment` is no longer imported. This is a clean removal — any import of this symbol from this module will now fail (though nothing else imports from this script directly).

#### NLI Inference Block Removal

```diff
-    try:
-        nli_results = results_to_dict(nli_aspect_sentiment(review_text, aspects))
-    except Exception as e:
-        print(f"Error in NLI inference for review {review_id}: {e}")
-        nli_results = {aspect: "error" for aspect in aspects}
```

The entire try/except block that invoked `nli_aspect_sentiment` and stored results in `nli_results` has been deleted. This means:

- The NLI model is **no longer invoked** during inference, removing its computational overhead (inference time, memory usage, and any associated API/model loading costs) entirely.
- Error handling specific to NLI failures is also gone.

#### Column Write Removal

```diff
-        df.loc[idx, "nli_sentiment"] = nli_results[aspect]
```

The line that wrote NLI predictions into the `"nli_sentiment"` column of `df` has been removed. As a result:

- The output `predictions.csv` **will no longer contain an `nli_sentiment` column** (unless the column already existed in the input CSV and was not overwritten).
- Downstream consumers of `predictions.csv` that relied on the `nli_sentiment` column for comparison will need to be updated.

### Functional Impact

| Aspect                   | Before                                          | After                                  |
|--------------------------|-------------------------------------------------|----------------------------------------|
| Models invoked per review | LLM + NLI                                      | LLM only                               |
| Output columns written   | `llm_sentiment`, `nli_sentiment`                | `llm_sentiment` only                   |
| Inference time per review | Higher (two model calls)                        | Lower (one model call)                 |
| `predictions.csv` schema | Includes `nli_sentiment`                        | Does not include `nli_sentiment`       |
| Error handling           | Separate try/except for LLM and NLI            | Single try/except for LLM only         |

### Why This Change Matters

This is a **functional change** to both the inference pipeline and the output artifact schema. If any evaluation scripts, notebooks, or reports depend on the `nli_sentiment` column being present in `predictions.csv`, they will break or produce incomplete results. The change likely reflects a deliberate decision to streamline the evaluation to focus exclusively on LLM-based predictions, possibly after NLI-based inference was deemed unnecessary, underperforming, or too resource-intensive for the evaluation goals.

---

## 4. Dependencies & Integration

### External Dependencies

| Library    | Usage                                                                 |
|------------|-----------------------------------------------------------------------|
| `pandas`   | DataFrame loading (`read_csv`), mutation, and persistence (`to_csv`) |
| `pathlib`  | Constructing the project root path for `sys.path` manipulation        |
| `sys`      | Inserting the project root into the Python module search path         |

### Internal Dependencies

| Module                        | Symbol Imported          | Role                                                                                   |
|-------------------------------|--------------------------|----------------------------------------------------------------------------------------|
| `app.sentiment_analyzer`      | `llm_aspect_sentiment`   | Core inference function; takes review text and a list of aspects, returns sentiment predictions as a list of dicts |
| `app.config`                  | `DEFAULT_ASPECTS`        | Provides the canonical list of aspects used for evaluation                             |

### `sys.path` Manipulation

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

This line inserts the **project root** directory at the front of `sys.path` at runtime, enabling imports from `app.*` regardless of how/where the script is invoked. This is necessary because `inference/` is a subdirectory of the project root and is not a package itself.

### What Depends on This Module

This is a **standalone script** and is not imported by any other module. It is intended to be run directly:

```bash
# From the project root:
python inference/run_inference_on_gold.py
```

### Output Artifact

| File              | Format | Description                                                                                  |
|-------------------|--------|----------------------------------------------------------------------------------------------|
| `predictions.csv` | CSV    | The input DataFrame with an added `llm_sentiment` column containing per-aspect predictions. Written to the current working directory. |

---

`FUNCTIONAL_CHANGE: YES`
