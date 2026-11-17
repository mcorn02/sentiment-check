"""
Compare prediction runs against the gold labels: macro F1 per aspect + overall.

    python evaluation/final_sentiment_analysis.py                # every predictions/*.csv
    python evaluation/final_sentiment_analysis.py a.csv b.csv    # specific runs

The legacy gpt-4o-mini baseline (predictions.csv, column llm_sentiment) is
included automatically when present.
"""
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parent.parent
# Score only the real label set, so stray labels (e.g. "neutral") count as
# misses instead of adding a zero-F1 class that drags macro F1 down.
LABELS = ["positive", "negative", "not_mentioned"]


def load_runs(paths: list[str]) -> dict[str, pd.DataFrame]:
    runs = {}
    legacy = ROOT / "predictions.csv"
    if legacy.exists():
        df = pd.read_csv(legacy).rename(columns={"llm_sentiment": "pred_sentiment"})
        runs["gpt-4o-mini (baseline)"] = df[["review_id", "aspect", "gold_sentiment", "pred_sentiment"]]
    files = [Path(p) for p in paths] or sorted((ROOT / "predictions").glob("*.csv"))
    for f in files:
        runs[f.stem] = pd.read_csv(f)
    return runs


def main() -> None:
    runs = load_runs(sys.argv[1:])
    if not runs:
        sys.exit("No prediction files found. Run inference/run_inference_on_gold.py first.")

    per_aspect, overall = {}, {}
    for name, df in runs.items():
        gold, pred = df["gold_sentiment"].astype(str), df["pred_sentiment"].astype(str)
        overall[name] = {
            "macro_f1": round(f1_score(gold, pred, labels=LABELS, average="macro"), 3),
            "accuracy": round(accuracy_score(gold, pred), 3),
            "errors": int((pred == "error").sum()),
        }
        per_aspect[name] = {
            aspect: round(f1_score(g["gold_sentiment"].astype(str), g["pred_sentiment"].astype(str), labels=LABELS, average="macro", zero_division=0), 3)
            for aspect, g in df.groupby("aspect")
        }

    print("Overall")
    print(pd.DataFrame(overall).T.to_string())
    print("\nMacro F1 per aspect")
    print(pd.DataFrame(per_aspect).to_string())


if __name__ == "__main__":
    main()
