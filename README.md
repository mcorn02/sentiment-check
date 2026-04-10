# Sentiment Check

An aspect-based sentiment analysis tool that supports IMDB movie review scraping, Google Maps and Yelp review scraping, and CSV upload for any industry. Generates structured sentiment reports broken down by aspect, powered by GPT-4o-mini via the OpenAI API.

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright's Chromium browser (used for scraping IMDB, Google Maps, and Yelp reviews):
```bash
playwright install chromium
```

4. Install frontend dependencies and build:
```bash
cd frontend && npm install && npm run build
```

5. Set up your OpenAI API key:
```bash
export OPENAI_API_KEY=your_api_key_here
```
Or create a `.env` file in the project root:
```
OPENAI_API_KEY=your_api_key_here
```

> **First run:** The sentence-transformer model will be downloaded automatically (~500MB).

## Usage

### Web App (main workflow)

```bash
python -m app.main --web
```

This starts FastAPI on port 8000 and serves the React frontend. Open `http://localhost:8000` in your browser, paste an IMDB movie URL, and click **Generate Report**.

**What the report contains:**
- Per-aspect sentiment breakdown (positive / negative / not mentioned) across all scraped reviews
- Bar, pie, and radar charts visualizing sentiment distribution
- A RAG-generated narrative per aspect — grounded in direct quotes retrieved from the reviews
- An overall summary synthesizing sentiment across all aspects

**Frontend dev server** (with hot reload, proxies `/api` to port 8000):
```bash
cd frontend && npm run dev
```

### IMDB Report API

`POST /api/report/imdb` accepts an IMDB movie URL and streams progress + results as Server-Sent Events (SSE).

Stages: `scraping` → `analyzing` → `generating` → `done`

**Request body:**
```json
{
  "imdb_url": "https://www.imdb.com/title/tt1375666/",
  "aspects": ["acting_performances", "story_plot"]
}
```

The `aspects` field is optional; omitting it uses the default aspects defined in `app/config.py`.

### Competitive Research API

`POST /api/research/competitors` runs a competitive analysis of sentiment analysis tools and platforms and returns a structured report. This is an internal/admin endpoint.

**Request body (optional):**
```json
{
  "focus": "pricing"
}
```

The `focus` field is optional. When provided, the analysis emphasizes that area (e.g. `"pricing"`, `"features"`, `"target market"`). Omitting the body or the field runs a general analysis.

**Response structure:**
```json
{
  "competitors": [
    {
      "name": "...",
      "pricing": "...",
      "key_features": ["..."],
      "strengths": ["..."],
      "weaknesses": ["..."],
      "target_market": "..."
    }
  ],
  "gaps": ["..."],
  "opportunities": ["..."]
}
```

### CSV Upload

When uploading a CSV file to the batch or report endpoints, the API automatically detects which column contains review text. It checks for common column names in the following priority order: `review`, `text`, `comment`, `body`, `content`, `description`, `feedback`. If none of these are found, it falls back to the first string column. To specify a column explicitly, pass a `review_column` parameter in your request.

CSV files are parsed with UTF-8 encoding, falling back to Latin-1 if needed. Malformed lines are skipped automatically.

### Command-Line Interface

```bash
# Analyze a single review
python -m app.main --review "This movie had great acting but a weak plot."

# Analyze from a file
python -m app.main --file review.txt

# Custom aspects
python -m app.main --review "..." --aspects acting plot soundtrack

# Test with dataset (first N reviews)
python -m app.main --dataset-kaggle --test 5
python -m app.main --dataset path/to/IMDB_Dataset.csv --test 5
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--web` | Start the web server |
| `--review TEXT` | Review text to analyze |
| `--file PATH` | Path to file containing review text |
| `--dataset PATH` | Path to a local CSV dataset |
| `--dataset-kaggle` | Download IMDB dataset from Kaggle |
| `--aspects A B ...` | Custom aspects to analyze |
| `--method METHOD` | `"LLM (OpenAI)"` |
| `--test N` | Analyze first N reviews from a dataset |

## Default Aspects

Defined in `app/config.py`:
- `quality`
- `value`
- `service`
- `features`
- `reliability`
- `usability`

Movie-specific aspects (`MOVIE_ASPECTS`) are used automatically by the IMDB endpoint:
- `acting_performances`, `story_plot`, `pacing`, `visuals`, `directing`, `writing`

## Evaluation

Run inference on the gold dataset and evaluate:

```bash
# Generate predictions (saves to predictions.csv, checkpoints every 10 reviews)
python inference/run_inference_on_gold.py

# Compute macro F1 per aspect
python evaluation/final_sentiment_analysis.py
```

## Troubleshooting

**OpenAI API key not found:** Ensure `OPENAI_API_KEY` is set as an environment variable or in a `.env` file in the project root.

**Import errors:** Always run from the project root using `python -m app.main` — direct invocation (`python app/main.py`) breaks package imports.

**NLTK data missing:** Run `python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"` manually.

**IMDB scraper blocked or returning no results:** The scraper uses Playwright with headless Chromium to bypass bot detection. If reviews fail to load, ensure Playwright's Chromium browser is installed (`playwright install chromium`) and try again.

**Google Maps or Yelp scraper blocked or returning no results:** Both scrapers use Playwright with headless Chromium. If reviews fail to load, ensure Playwright's Chromium browser is installed (`playwright install chromium`) and try again. For Google Maps, both full `google.com/maps/` URLs and short `maps.app.goo.gl` links are supported.