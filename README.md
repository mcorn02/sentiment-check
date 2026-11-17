# Sentiment Check

Upload a file of reviews and get an aspect-based sentiment report: per-aspect positive/negative breakdowns, charts, quote-grounded narratives, an overall summary, business insights, and a chat box for follow-up questions about the reviews.

Works for any industry. Pick a domain preset (restaurant, hotel, software, etc.) or add your own aspects.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && npm run build && cd ..
```

Add your Anthropic API key to a `.env` file in the project root: `ANTHROPIC_API_KEY=...`. The app uses Claude Sonnet 5.5 (`app/config.py`).

> **First run:** the sentence-transformer and cross-encoder models download automatically (~500MB). NLTK tokenizers download on first use.

## Run

```bash
uvicorn api.main:app --port 8000
```

Open `http://localhost:8000`, drop in a reviews file, choose a domain/aspects, and click **Analyze Reviews**.

**Frontend dev server** (hot reload, proxies `/api` to :8000):
```bash
uvicorn api.main:app --reload        # terminal 1
cd frontend && npm run dev           # terminal 2 → http://localhost:5173
```

## Supported upload formats

| Format | How reviews are found |
|---|---|
| `.csv`, `.tsv`, `.xlsx` | Review column auto-detected (see below) |
| `.json` | Array of strings, array of objects, or an object wrapping a list (e.g. `{"reviews": [...]}`); nested objects are flattened (`review.body`) |
| `.jsonl` / `.ndjson` | One object or string per line |
| `.txt` | Paragraphs separated by blank lines; if there are none, one review per line |

**Column detection:** known names first (`review`, `review_text`, `text`, `comment`, `comments`, `body`, `content`, `feedback`, `message`, `description`), otherwise the text column with the longest average value. Override with the optional **Review column** field in the UI (or `review_column` form field). Max upload size is 25 MB.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/report/upload` | Multipart upload (`file`, optional `domain_id`, `domain`, `aspects` comma-separated, `review_column`). Streams Server-Sent Events. |
| `POST /api/report/chat` | `{"report_id", "question"}` → RAG answer over the report's reviews |
| `GET/POST /api/domains`, `GET /api/domains/{id}` | Domain presets + custom domains (aspect lists) |
| `GET /api/health` | Health check |

SSE events from `/report/upload`: `stage` (`parsing` → `analyzing` with progress → `generating`), `warning`, `aspect_complete`, `insights`, `charts`, `report`, `error`, `done`.

## Evaluation

```bash
python inference/run_inference_on_gold.py      # writes predictions.csv
python evaluation/final_sentiment_analysis.py  # macro F1 per aspect
```

Requires the gold dataset at `data/gold_dataset_aspect_level - gold_dataset_aspect_level.csv` (not committed).

## Troubleshooting

- **API key not found** — set it in `.env` at the project root.
- **NLTK data missing** — `python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"`.
- **Blank page at :8000** — the frontend isn't built; run `npm run build` in `frontend/`.
