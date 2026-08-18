# socials-auto-upload

Automated video publishing to **TikTok** and **Facebook** (Reels and feed
video), designed so each platform succeeds or fails on its own.

One upload, one API call, N independent jobs.

```bash
cp .env.example .env      # see docs/CREDENTIALS.md to fill this in
docker compose up -d --build
docker compose exec api python scripts/init_db.py
```

## How it works

The source video goes **straight to Cloudflare R2** via a presigned URL — it
never passes through this service. `POST /publish` then creates one job per
platform, each on its own queue with its own worker, retries, and credentials.

Where possible the platform **pulls** the file from R2 rather than being fed
chunks. That is what makes large Facebook uploads a non-problem, and R2's zero
egress makes it free.

```
source ──▶ R2 ──▶ ┬── job:tiktok        ─▶ TikTok Content Posting API
                  ├── job:facebook_reel ─▶ Graph /video_reels
                  └── job:facebook_video─▶ Graph /videos
```

A TikTok rate-limit retries while the Facebook post is already live. Retrying
one leg never re-uploads the other.

## Stack

| Concern | Choice | Why |
|---|---|---|
| Storage | Cloudflare R2 | 10 GB free, **zero egress** — platforms pull for free |
| Queue | Redis + RQ | one queue per platform, independently scalable |
| API | FastAPI | typed, async, self-documenting |
| State | Postgres | job history, resume offsets, rotating tokens |
| Media | ffmpeg | per-platform renditions (9:16 vertical, 16:9 feed) |
| Orchestration | n8n | triggers, scheduling, approvals, notifications |

n8n handles *when* to post. This service handles *how*. See
[docs/N8N_INTEGRATION.md](docs/N8N_INTEGRATION.md).

## Documentation

| Document | For |
|---|---|
| [Credentials](docs/CREDENTIALS.md) | step-by-step: R2, Facebook, and TikTok keys for `.env` |
| [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) | what is built, what is left, what is blocked |
| [Architecture](docs/ARCHITECTURE.md) | the design and the reasoning behind it |
| [Platform Notes](docs/PLATFORM_NOTES.md) | every TikTok/Facebook API assumption, with a verification checklist |
| [Development Guide](docs/DEVELOPMENT.md) | setup, endpoints, end-to-end example, layout |
| [n8n Integration](docs/N8N_INTEGRATION.md) | wiring the workflow |
| [CLAUDE.md](CLAUDE.md) | conventions and invariants for AI agents |

## Status

The pipeline is complete and internally consistent. The platform request
shapes follow Meta's and TikTok's published docs but have **not been run
against the live APIs** here — work through the checklist in
[Platform Notes](docs/PLATFORM_NOTES.md#verification-checklist) before go-live,
and start app review first, since that is the real critical path.
