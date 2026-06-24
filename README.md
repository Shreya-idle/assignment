# AI-Powered Transaction Processing Pipeline

Backend API that accepts a CSV of financial transactions, processes them asynchronously via Celery, uses an LLM to classify uncategorised rows and generate a narrative summary, and exposes results through a polling API.

## Stack

- **API:** FastAPI
- **Database:** PostgreSQL
- **Job queue:** Celery + Redis
- **LLM:** Google Gemini 1.5 Flash (optional; heuristic fallback without API key)
- **Containers:** Docker Compose

## Quick Start

```bash
# Optional: enable live LLM calls
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key

docker compose up --build
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

## Example Requests

### Upload CSV

```bash
curl -X POST "http://localhost:8000/jobs/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@transactions.csv"
```

Response:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Job enqueued for processing"
}
```

### Poll job status

```bash
curl "http://localhost:8000/jobs/{job_id}/status"
```

When `status` is `completed`, a high-level `summary` is included.

### Get full results

```bash
curl "http://localhost:8000/jobs/{job_id}/results"
```

Returns cleaned transactions, flagged anomalies, per-category spend breakdown, and LLM narrative summary.

### List all jobs

```bash
curl "http://localhost:8000/jobs"
curl "http://localhost:8000/jobs?status=completed"
```

## Processing Pipeline

1. **Data cleaning** — ISO 8601 dates, strip `$` from amounts, uppercase status/currency, fill missing categories with `Uncategorised`, remove exact duplicate rows
2. **Anomaly detection** — flag amounts > 3× account median; flag USD at domestic merchants (Swiggy, Ola, IRCTC)
3. **LLM classification** — batched category assignment for originally uncategorised transactions (retries ×3 with exponential backoff)
4. **LLM narrative** — single JSON summary with spend totals, top merchants, anomaly count, narrative, and risk level
5. **Graceful LLM failure** — marks batches as `llm_failed` and continues with heuristic fallback

## Project Structure

```
app/
├── api/jobs.py          # REST endpoints
├── services/
│   ├── cleaning.py      # CSV parse & normalize
│   ├── anomaly.py       # Statistical & rule-based flags
│   └── llm.py           # Gemini integration + fallbacks
├── tasks/pipeline.py    # Celery worker task
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic response models
├── celery_app.py
└── main.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@db:5432/transactions` | PostgreSQL connection |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker |
| `GEMINI_API_KEY` | (empty) | Google AI API key for LLM calls |

## Health Check

```bash
curl http://localhost:8000/health
```
