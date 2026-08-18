# Development Guide

## Prerequisites

- Docker + Docker Compose (the quickest path — the image ships ffmpeg)
- Or: Python 3.11+, ffmpeg/ffprobe on `PATH`, Postgres 16, Redis 7

## First run

Getting the credential values is a separate walkthrough:
**[CREDENTIALS.md](CREDENTIALS.md)**.

```bash
cp .env.example .env
# fill in R2 + platform credentials, then:
docker compose up -d --build
docker compose exec api python scripts/init_db.py
docker compose exec api python scripts/init_r2_cors.py
```

`init_r2_cors.py` allows `CORS_ORIGINS` to PUT into the bucket from a browser.
Without it the console's upload fails before a single byte leaves the tab — a
presigned URL authorises the upload, but the bucket policy decides which origin
may use it. Re-run it whenever `CORS_ORIGINS` changes.

Services: API on `:8000`, n8n on `:5678`, one worker per platform.

## Local, without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL=postgresql+psycopg://sau:sau@localhost:5432/sau
export REDIS_URL=redis://localhost:6379/0

python scripts/init_db.py
uvicorn sau.api.main:app --reload      # terminal 1
python scripts/worker.py facebook      # terminal 2
python scripts/worker.py tiktok        # terminal 3
```

`python scripts/worker.py` with no arguments consumes every queue — convenient
locally, but keep them separate in production so a long Facebook transfer
cannot delay a TikTok post.

## Publishing a video end to end

```bash
API=http://localhost:8000

# 1. Get a presigned URL and upload the source straight to R2.
#    The file never passes through the API process.
read KEY URL < <(curl -s -X POST $API/assets/upload-url \
  -H 'content-type: application/json' \
  -d '{"filename":"clip.mp4"}' | jq -r '.storage_key + " " + .upload_url')

curl -s -X PUT "$URL" -H 'content-type: video/mp4' --upload-file clip.mp4

# 2. Register it.
ASSET=$(curl -s -X POST $API/assets -H 'content-type: application/json' \
  -d "{\"storage_key\":\"$KEY\"}" | jq -r .id)

# 3. Fan out. One entry per platform; each becomes an independent job.
curl -s -X POST $API/publish -H 'content-type: application/json' -d "{
  \"asset_id\": \"$ASSET\",
  \"targets\": [
    {\"platform\": \"tiktok\",         \"caption\": \"hello #fyp\"},
    {\"platform\": \"facebook_reel\",  \"caption\": \"hello\"}
  ]
}" | jq

# 4. Poll.
curl -s $API/assets/$ASSET/jobs | jq '.[] | {platform, state, external_url, last_error}'
```

Retry only the leg that failed:

```bash
curl -s -X POST $API/jobs/<job-id>/retry | jq
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | liveness |
| `POST` | `/assets/upload-url` | presigned PUT for the source file |
| `POST` | `/assets` | register an uploaded object |
| `GET` | `/assets/{id}` | asset metadata |
| `POST` | `/publish` | create one job per target platform |
| `GET` | `/jobs/{id}` | single job state |
| `GET` | `/assets/{id}/jobs` | all jobs for an asset |
| `POST` | `/jobs/{id}/retry` | re-queue one failed job |

Interactive docs at `http://localhost:8000/docs`.

## Tests

```bash
pytest
ruff check sau tests
mypy sau
```

Tests cover the pure logic that is easy to get wrong and expensive to debug
against a live API: chunk planning, error-envelope classification, retry
behaviour, transcode specs, permalink normalisation. They make no network
calls and need no database.

To exercise a platform for real, point `.env` at a test Page / a TikTok
sandbox account and run a single job through `POST /publish`.

## Layout

```
sau/
  config.py        typed settings
  errors.py        error taxonomy; `retryable` drives all retry decisions
  http.py          shared httpx client + jittered backoff
  storage.py       R2: presigned URLs, ranged reads, chunk iteration
  transcode.py     ffprobe/ffmpeg, per-platform specs
  models.py        assets, renditions, publish_jobs, oauth_tokens
  db.py            engine + transactional session scope
  tokens.py        credential storage with race-safe refresh
  renditions.py    transcode-and-cache
  api/             FastAPI surface
  queue/           per-platform queues and worker tasks
  platforms/
    base.py        the Publisher interface
    facebook/      client.py (transport) + publisher.py (flow)
    tiktok/        client.py (transport) + publisher.py (flow)
console/           React operator console (see console/README.md)
  src/api/         wire types + the only place a fetch is issued
  src/domain/      platform rules, job lifecycle, slot maths — pure
  src/hooks/       state: composer, publish flow, polling, backlog
  src/components/  generic UI kit
  src/features/    one folder per panel, composed by App.tsx
docs/              this documentation
n8n/               importable workflows (daily backlog release)
scripts/           init_db, init_r2_cors, worker, seed_tokens
tests/
```

## Conventions

- **Transport and flow are separate.** `client.py` knows HTTP, headers, and
  error envelopes. `publisher.py` knows the publish sequence. Tests target
  `client.py` boundaries without mocking a whole flow.
- **Errors carry `retryable`.** Nothing else in the system decides whether to
  retry. If a new error code is added, classify it in the client's `_unwrap`.
- **No blocking waits.** A worker never sleeps waiting for a platform; it
  schedules a poll and exits.
- **Comments explain why.** The APIs here have non-obvious rules (single-use
  refresh tokens, remainder-in-last-chunk, HTTP 200 errors). Those get a
  comment. Restating what the code does does not.
