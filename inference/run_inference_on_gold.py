"""
Label the gold dataset with Claude and write predictions for evaluation.

    python inference/run_inference_on_gold.py --model claude-haiku-5-5 --effort low
    -> predictions/claude-haiku-5-5_low.csv

Each review is labeled once for the aspects it has gold labels for. Reviews run
concurrently (same semaphore pattern as the web app). Prints token usage at the end.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from app.config import CLAUDE_MODEL, LABEL_EFFORT  # noqa: E402
from app.llm import USAGE  # noqa: E402
from app.sentiment_analyzer import async_llm_aspect_sentiment  # noqa: E402

GOLD = ROOT / "data" / "gold_dataset_aspect_level - gold_dataset_aspect_level.csv"


async def main(model: str, effort: str, domain: str, concurrency: int) -> None:
    df = pd.read_csv(GOLD)
    groups = list(df.groupby("review_id"))
    sem = asyncio.Semaphore(concurrency)
    preds: dict[tuple, str] = {}
    failures = 0

    async def label(review_id, group):
        nonlocal failures
        aspects = list(dict.fromkeys(group["aspect"]))
        async with sem:
            try:
                results = await async_llm_aspect_sentiment(
                    group.iloc[0]["review"], aspects, domain=domain, model=model, effort=effort
                )
                for r in results:
                    preds[(review_id, r["aspect"])] = r["sentiment"]
            except Exception as e:
                failures += 1
                print(f"review {review_id}: {type(e).__name__}: {e}")
                for a in aspects:
                    preds[(review_id, a)] = "error"

    t = time.time()
    await asyncio.gather(*[label(rid, g) for rid, g in groups])
    elapsed = time.time() - t

    out = df[["review_id", "aspect", "gold_sentiment"]].copy()
    out["pred_sentiment"] = [preds[(r, a)] for r, a in zip(out["review_id"], out["aspect"])]
    out_dir = ROOT / "predictions"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{model}_{effort}.csv"
    out.to_csv(path, index=False)

    u = USAGE.get(model, {})
    print(f"{model} @ {effort}: {len(groups)} reviews in {elapsed:.1f}s, {failures} failed -> {path.relative_to(ROOT)}")
    print(f"tokens: {u.get('input_tokens', 0)} in / {u.get('output_tokens', 0)} out over {u.get('calls', 0)} calls")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=CLAUDE_MODEL)
    ap.add_argument("--effort", default=LABEL_EFFORT)
    ap.add_argument("--domain", default="movie")
    ap.add_argument("--concurrency", type=int, default=10)
    a = ap.parse_args()
    asyncio.run(main(a.model, a.effort, a.domain, a.concurrency))
