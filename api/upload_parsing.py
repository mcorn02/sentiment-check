"""
Turn an uploaded file into a list of review strings.

Supported formats (by file extension):
    .csv            comma-separated, with a header row
    .tsv            tab-separated, with a header row
    .xlsx           Excel workbook (first sheet, header row)
    .json           array of strings, array of objects, or an object
                    wrapping one of those (e.g. {"reviews": [...]})
    .jsonl/.ndjson  one JSON object (or string) per line
    .txt            reviews separated by blank lines; if there are no
                    blank lines, one review per line

For tabular formats the review column is auto-detected (see
`detect_review_column`) unless the caller passes `review_column`.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import PurePath

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".tsv", ".xlsx", ".json", ".jsonl", ".ndjson", ".txt")

# Column names that usually hold review text, in priority order.
_REVIEW_COLUMN_CANDIDATES = [
    "review", "review_text", "reviewtext", "review_body", "text", "comment",
    "comments", "body", "content", "feedback", "message", "description",
]


class UploadError(ValueError):
    """Raised when an upload can't be turned into reviews. Message is user-facing."""


def parse_upload(filename: str, contents: bytes, review_column: str | None = None) -> list[str]:
    """Parse an uploaded file into a list of non-empty review strings."""
    ext = PurePath(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UploadError(
            f"Unsupported file type '{ext or '(none)'}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if not contents.strip():
        raise UploadError("Uploaded file is empty.")

    if ext == ".txt":
        reviews = _parse_text(_decode(contents))
    elif ext in (".json", ".jsonl", ".ndjson"):
        reviews = _parse_json(_decode(contents), ext, review_column)
    else:
        df = _read_table(contents, ext)
        reviews = _reviews_from_frame(df, review_column)

    reviews = [r.strip() for r in reviews if isinstance(r, str) and r.strip()]
    if not reviews:
        raise UploadError("No review text found in the uploaded file.")
    return reviews


# ── Format readers ────────────────────────────────────────────────────────────

def _decode(contents: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return contents.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UploadError("Could not decode file as text.")


def _read_table(contents: bytes, ext: str) -> pd.DataFrame:
    try:
        if ext == ".xlsx":
            return pd.read_excel(io.BytesIO(contents))
        sep = "\t" if ext == ".tsv" else ","
        try:
            return pd.read_csv(io.BytesIO(contents), sep=sep, encoding="utf-8-sig", on_bad_lines="skip")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(contents), sep=sep, encoding="latin-1", on_bad_lines="skip")
    except UploadError:
        raise
    except Exception as e:
        raise UploadError(f"Could not read {ext} file: {e}") from e


def _parse_text(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    if re.search(r"\n\s*\n", text):
        return re.split(r"\n\s*\n", text)
    return text.split("\n")


def _parse_json(text: str, ext: str, review_column: str | None) -> list[str]:
    try:
        if ext in (".jsonl", ".ndjson"):
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            data = json.loads(text)
    except json.JSONDecodeError as e:
        raise UploadError(f"Invalid JSON: {e}") from e

    # Unwrap {"reviews": [...]}-style containers: use the named key if given,
    # otherwise the first list-valued key.
    if isinstance(data, dict):
        if review_column and isinstance(data.get(review_column), list):
            data = data[review_column]
            review_column = None
        else:
            lists = [v for v in data.values() if isinstance(v, list)]
            if not lists:
                raise UploadError("JSON object has no list of reviews in it.")
            data = lists[0]

    if not isinstance(data, list) or not data:
        raise UploadError("JSON must contain a non-empty list of reviews.")

    if all(isinstance(x, str) for x in data):
        return data

    records = [x for x in data if isinstance(x, dict)]
    if not records:
        raise UploadError("JSON list must contain strings or objects.")
    return _reviews_from_frame(pd.json_normalize(records), review_column)


# ── Column detection ─────────────────────────────────────────────────────────

def _reviews_from_frame(df: pd.DataFrame, review_column: str | None) -> list[str]:
    if df.empty:
        raise UploadError("Uploaded file has no rows.")
    col = detect_review_column(df, review_column)
    return df[col].dropna().astype(str).tolist()


def detect_review_column(df: pd.DataFrame, hint: str | None = None) -> str:
    """
    Pick the column holding review text.

    Order: explicit hint (case-insensitive) → known column names → the text
    column with the longest average value (reviews are long; names, dates,
    and IDs are short).
    """
    lower_map = {str(c).lower(): c for c in df.columns}

    if hint:
        if hint in df.columns:
            return hint
        if hint.lower() in lower_map:
            return lower_map[hint.lower()]
        raise UploadError(
            f"Column '{hint}' not found. Available columns: {list(map(str, df.columns))}"
        )

    for name in _REVIEW_COLUMN_CANDIDATES:
        if name in lower_map:
            return lower_map[name]

    text_cols = [
        c for c in df.columns
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])
    ]
    if text_cols:
        return max(text_cols, key=lambda c: df[c].dropna().astype(str).str.len().mean() or 0)

    raise UploadError(
        f"Could not detect a review text column. Available columns: {list(map(str, df.columns))}. "
        "Enter the column name in 'Review column'."
    )
