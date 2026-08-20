# Deployment — free and near-free options

This pipeline is harder to host free than a typical web app, and it is worth
being precise about why. Three of its properties disqualify most free tiers:

1. **Two long-lived processes.** The RQ workers are not request-driven. A
   platform that only runs code in response to an HTTP request (Vercel,
   Netlify, Cloudflare Workers) can host the console and nothing else.
2. **ffmpeg on local disk.** `sau/renditions.py` downloads the source and
   writes the output side by side in a `TemporaryDirectory`. Peak disk is
   roughly *source + output*, and the transcode is CPU-bound. A 512 MB /
   shared-CPU container is the binding constraint, not the API traffic.
3. **Stateful backing services.** Postgres (with `SELECT ... FOR UPDATE`, see
   invariant 6) and Redis, both durable, both always reachable.

Storage is already solved: R2 is free to 10 GB with no egress charge, and it
stays where it is in every option below.

The single biggest lever on hosting cost is **invariant 5**. With
`R2_PUBLIC_BASE_URL` set, Facebook and TikTok fetch the rendition from R2
themselves and the dyno/container never streams gigabytes outbound. Set it
before deploying anywhere small; it is the difference between a 512 MB tier
being viable and not.

---

## Option 1 — Oracle Cloud Always Free VM *(recommended)*

A free-forever ARM VM. Clone the repo, `docker compose up -d --build`, and
every service in [docker-compose.yml](../docker-compose.yml) runs unchanged:
API, both workers, Postgres, Redis, the console, n8n. No sleeping, no per-
service juggling, real disk for ffmpeg.

| | |
|---|---|
| Shape | `VM.Standard.A1.Flex` (Ampere ARM) |
| Always Free allowance | **2 OCPU / 12 GB RAM** — halved from 4/24 on 15 June 2026 |
| Storage | 200 GB block volume |
| Cost | $0, no expiry |

Two caveats. Oracle cut the Ampere allowance in June 2026 without an
announcement and began terminating over-limit instances on 18 August 2026, so
size at 2 OCPU / 12 GB and do not assume the old numbers from older guides.
And A1 capacity is frequently exhausted in popular regions — expect to retry
the create call, or pick a quieter region. A card is required for identity
verification.

The image builds on ARM without changes (`python:3.12-slim` and `ffmpeg` are
both multi-arch).

## Option 2 — Heroku, via the GitHub Student Developer Pack

The pack grants **$13/month for 24 months**, which is exactly the price of the
smallest viable configuration: Eco dynos ($5) + Postgres Essential-0 ($5) +
Key-Value Store Mini ($3). Effectively free for two years, then a cliff.

Managed Postgres and Redis, `git push` deploys, no VM to patch. The costs are
a shared-CPU dyno for ffmpeg, ~1 GB of ephemeral scratch disk, and Eco's
1000-shared-dyno-hour ceiling, which the two worker processes have to be
arranged around.

Full walkthrough: **[HEROKU_PLAN.md](HEROKU_PLAN.md)**.

## Option 3 — Northflank free tier

Containers, no forced sleep, GitHub deploys. The free tier is 2 services + 2
jobs + 1 addon, which maps to `api` + one worker as services and Postgres as
the single addon — Redis then has to come from Upstash. Workable, but the
service budget leaves nothing spare, and the free container sizes are small
for a transcode.

## Option 4 — Assembled from single-purpose free tiers

| Piece | Where | Notes |
|---|---|---|
| API + worker | Render free | 750 instance-hours/month; background workers are declarable in `render.yaml` |
| Postgres | Neon or Supabase | Supabase free pauses after a week of inactivity |
| Redis | Upstash free | RQ needs the **TCP** endpoint, not the REST API |
| Console | Cloudflare Pages | build with `VITE_API_BASE_URL` pointing at the API |
| Media | Cloudflare R2 | already the storage layer — 10 GB free |

Most moving parts, most accounts, most things that can silently expire. Use it
if Oracle capacity is unavailable and the Heroku credit is spent.

## Not viable

- **Fly.io** — the free tier is gone. New accounts get a trial of 2 VM-hours
  or 7 days, whichever ends first.
- **Koyeb** — acquired by Mistral in early 2026; the free Starter tier is
  closed to new signups.
- **Vercel / Netlify / Cloudflare Workers** — can host `console/`, cannot run
  an RQ worker at all. Fine as the console half of any option above.

## Choosing

Take Oracle if you can get an A1 instance: it is the only option where the
repo deploys as designed, with no process collapsing and no disk ceiling.
Take Heroku if you cannot, and treat the 24-month credit as a runway rather
than a permanent home. Put the console on Cloudflare Pages either way — it is
static, it costs nothing, and it keeps a browser-facing origin off the box
that holds the credentials.

Sources: [Oracle free-tier reduction (InfoQ, July 2026)](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/) ·
[Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) ·
[Eco dyno hours](https://devcenter.heroku.com/articles/eco-dyno-hours) ·
[GitHub Student Developer Pack](https://education.github.com/pack)
