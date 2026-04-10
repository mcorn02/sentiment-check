"""
Shared CSV parsing utilities for batch and report endpoints.
"""
import io

import pandas as pd


def detect_review_column(df: pd.DataFrame, hint: str | None = None) -> str:
    """Return the column name containing review text."""
    if hint and hint in df.columns:
        return hint
    # Common column name candidates in priority order
    candidates = ["review", "text", "comment", "body", "content", "description", "feedback"]
    for c in candidates:
        if c in df.columns:
            return c
        if c in [col.lower() for col in df.columns]:
            return next(col for col in df.columns if col.lower() == c)
    # Fall back to the first string column
    for col in df.columns:
        if df[col].dtype == object:
            return col
    raise ValueError(
        f"Could not detect a review text column. Available columns: {list(df.columns)}. "
        "Pass 'review_column' to specify one."
    )


def parse_csv_bytes(contents: bytes) -> pd.DataFrame:
    """Parse CSV bytes with encoding fallback. Returns a DataFrame."""
    try:
        return pd.read_csv(io.BytesIO(contents), encoding="utf-8", on_bad_lines="skip")
    except Exception:
        return pd.read_csv(io.BytesIO(contents), encoding="latin-1", on_bad_lines="skip")
