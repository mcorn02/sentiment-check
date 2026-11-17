# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Sentiment Check** — a web app: upload a file of reviews, get an aspect-based sentiment report streamed back (charts, per-aspect narratives grounded in quotes, overall summary, insights, Q&A chat). Upload-only by design; URL scraping was removed (recoverable from commit `132f104` if ever wanted, but it's a separate project).

- **Backend:** FastAPI in `api/`, analysis core in `app/`
- **Frontend:** React 19 + TypeScript + Vite + Tailwind v4 + Recharts in `frontend/`
- **LLM:** currently OpenAI `gpt-4o-mini` via `AsyncOpenAI` (`app/config.py`). The owner plans to switch to Claude Sonnet 5.5 **manually** — don't migrate the provider unless asked.
- **Local models:** `all-MiniLM-L6-v2` (embeddings) + `cross-encoder/ms-marco-MiniLM-L-6-v2` (rerank), lazily loaded module globals.

There is no CLI — the web app is the only interface. Python env in use: `~/.pyenv/versions/venv311`.

## Commands

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build      # prod build → frontend/dist, served by FastAPI

uvicorn api.main:app --reload                    # API (+ built SPA) on :8000
cd frontend && npm run dev                       # dev UI on :5173, proxies /api → :8000

cd frontend && npx tsc -b && npx eslint src      # typecheck + lint

python inference/run_inference_on_gold.py        # gold-set predictions → predictions.csv
python evaluation/final_sentiment_analysis.py    # macro F1 per aspect
```

No automated test suite yet.

## Request flow

1. `ReviewInput.tsx` → `useSSE.startUploadReport` → `POST /api/report/upload` (multipart)
2. `api/upload_parsing.py::parse_upload` turns csv/tsv/xlsx/json/jsonl/txt into `list[str]`; raises `UploadError` (user-facing message → HTTP 400)
3. `api/routes/report.py::_resolve_domain` picks domain label + aspects (explicit aspects > domain config > `DEFAULT_ASPECTS`)
4. `_stream_report` runs `app/report_generator.py::async_generate_report` as a task; the generator calls a sync `emit(event, data)` callback which feeds an `asyncio.Queue` that the SSE generator drains. Task is cancelled if the client disconnects.
5. `async_generate_report`:
   - `sentiment_analyzer.async_analyze_batch` — one LLM call per review, semaphore concurrency 10, per-review progress (throttled to ~100 events)
   - `build_corpus` — sentence-split + embed all reviews (run in a thread)
   - per aspect: cosine top-30 → cross-encoder rerank to top-10 → LLM narrative (concurrent)
   - overall summary LLM call, then `insights_agent.async_generate_insights`
   - returns `(report, corpus)`; the corpus is cached for chat so reviews are embedded once
6. Route emits `charts`, `report` (with `report_id`), `done`. Report + corpus go in an in-memory LRU (`_REPORT_CACHE_MAX = 20`) for `POST /api/report/chat`.

SSE event names and payload shapes are a contract with `frontend/src/hooks/useSSE.ts` and `frontend/src/types/report.ts` — change both sides together. Stages: `parsing` → `analyzing` → `generating` → `done` (matches `ProgressStepper.tsx`).

## Other pieces

- `api/db.py` — SQLite (`data/api.db`) holding domain presets (seeded on startup) and custom domains. `api/routes/domains.py` exposes them; the UI's domain dropdown uses it.
- `app/config.py` — `DEFAULT_ASPECTS`, model names, `OPENAI_MAX_TOKENS`, API key loading (`.env` via dotenv).
- `app/preprocessing.py` — HTML/whitespace cleanup + NLTK sentence splitting for the corpus.
- `inference/` + `evaluation/` — offline accuracy check against a hand-labelled gold set (data files are gitignored). Use this to compare models/prompts before and after changes.

## Planned work (owner-requested — not done yet)

1. **Per-review labeling is outdated — rework it.** Current issues in `sentiment_analyzer.py`:
   - Only positive / negative / not_mentioned; no mixed/neutral, no confidence, no evidence quote per label.
   - JSON is parsed by stripping code fences; should use structured output / tool calling.
   - On API failure a review silently becomes `not_mentioned` for every aspect, skewing distributions — failures should be counted and surfaced.
   - `OPENAI_MAX_TOKENS = 350` can truncate the JSON when many aspects are requested.
2. **Aspect selection: keep user-picked aspects up front, plus have the model suggest/review aspects** from a sample of the reviews, so themes the user didn't anticipate get surfaced. (Domain presets may become less central once this exists.)
3. **Summaries and insights are thin.** The overall summary and insights only see percentage tables, not review text. With a stronger long-context model, feed the reviews (or a large sample) directly; this may let the local embedding/rerank models (and the `sentence-transformers`/`torch` deps) be dropped.
4. Model switch to Sonnet 5.5 (owner doing it manually). That will need the `anthropic` package re-added to `requirements.txt` and the client getters in `sentiment_analyzer.py` replaced; the eval scripts give a before/after F1 comparison.

## Gotchas

- Run Python from the project root (imports are `api.*` / `app.*`).
- `numpy<2.0` is pinned for the installed torch.
- pandas here may use the dedicated string dtype — check text columns with `pd.api.types.is_string_dtype`, not `dtype == object`.
- The Claude Code local settings (`.claude/`) are gitignored; this file is tracked.
