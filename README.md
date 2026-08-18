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
| Orchestration | n8n | triggers, approvals, notifications, the schedule heartbeat |

n8n supplies the heartbeat and the notifications; the posting slots and the
release order live in this service, editable from the console. See
[docs/N8N_INTEGRATION.md](docs/N8N_INTEGRATION.md).

## Console

A React operator console ships with the stack at <http://localhost:8080>: drop
a video, tick the platforms, write one caption per platform, then publish now
or add it to the scheduled backlog. It watches each job independently and can
retry a single failed platform.

The Series view handles a serialised show: drop `part1_….mp4`, `part2_….mp4`,
write one caption template for the whole series, and it goes out one episode
per slot in episode order. See [docs/SERIES.md](docs/SERIES.md).

It is a static bundle that talks to the API from the browser — see
[console/README.md](console/README.md) for its layout and configuration.

> The console has **no authentication**. Anyone who can reach it can post to
> your accounts. Keep it on localhost, or put both it and the API behind an
> access proxy (Cloudflare Access, Tailscale, or basic auth) before exposing
> either of them.

## Hosting

Media stays on R2 wherever the rest runs — zero egress is the reason the
platforms can pull directly.

| Piece | What it needs | Good fit |
|---|---|---|
| Console (`dist/`) | static file hosting | Cloudflare Pages, Netlify, GitHub Pages — all free |
| API + workers + Postgres + Redis + n8n | always-on containers, ffmpeg CPU, scratch disk | one small VPS running this compose file |
| Media | S3-compatible, zero egress | Cloudflare R2 |

**The simple answer: one VPS.** A 2 vCPU / 4 GB box (Hetzner, DigitalOcean,
Vultr — roughly $5–12/month) runs the entire compose file, n8n included, with
Caddy or nginx in front for TLS. Everything is already containerised, so it is
`git pull && docker compose up -d --build`.

Sizing is set by ffmpeg, not by traffic: transcoding is CPU-bound and writes
the rendition to scratch disk, so give the box a couple of gigabytes of free
space per concurrent job.

What does **not** work: serverless platforms (Vercel, Netlify Functions,
Cloudflare Workers) for the API or the workers. The workers are long-running
processes that shell out to ffmpeg and hold Redis connections, which is the
opposite of a request-scoped function. Free tiers that sleep idle containers
(Render's free web services, for instance) also break the schedule tick and the
polling of in-flight jobs.

Managed alternatives, if you would rather not run a box: Fly.io or Railway for
the API and workers, Neon or Supabase for Postgres, Upstash for Redis, and
either n8n Cloud or n8n on the same host. This costs more than the VPS and buys
convenience, not capability.

## Documentation

| Document | For |
|---|---|
| [Credentials](docs/CREDENTIALS.md) | step-by-step: R2, Facebook, and TikTok keys for `.env` |
| [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) | what is built, what is left, what is blocked |
| [Architecture](docs/ARCHITECTURE.md) | the design and the reasoning behind it |
| [Platform Notes](docs/PLATFORM_NOTES.md) | every TikTok/Facebook API assumption, with a verification checklist |
| [Series](docs/SERIES.md) | serialised uploads: episode ordering, caption templates, the hook generator, and the posting slots |
| [Development Guide](docs/DEVELOPMENT.md) | setup, endpoints, end-to-end example, layout |
| [n8n Integration](docs/N8N_INTEGRATION.md) | wiring the workflow |
| [Console](console/README.md) | the operator UI: layout, configuration, deploying |
| [CLAUDE.md](CLAUDE.md) | conventions and invariants for AI agents |

## Status

The pipeline is complete and internally consistent. The platform request
shapes follow Meta's and TikTok's published docs but have **not been run
against the live APIs** here — work through the checklist in
[Platform Notes](docs/PLATFORM_NOTES.md#verification-checklist) before go-live,
and start app review first, since that is the real critical path.
