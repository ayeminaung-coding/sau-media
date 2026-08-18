# Architecture

## The shape of the problem

Publishing one video to several social platforms looks like one task and is
actually N independent ones. Each platform has its own transfer protocol,
credential lifecycle, encoding constraints, rate limits, and review process.
The moment they share a code path, a failure on one becomes a failure on all.

So the system is a **fan-out**, not a chain.

```
                        ┌──────────────┐
   client / n8n ───────▶│  presigned   │──────▶ Cloudflare R2
   (uploads bytes)      │  PUT to R2   │        sources/<uuid>.mp4
                        └──────────────┘
                               │
                               ▼  POST /assets      (register)
                        ┌──────────────┐
                        │   FastAPI    │
                        └──────┬───────┘
                               │  POST /publish     (fan out)
              ┌────────────────┴────────────────┐
              ▼                                 ▼
      ┌───────────────┐                 ┌───────────────┐
      │ queue:tiktok  │                 │queue:facebook │
      └───────┬───────┘                 └───────┬───────┘
              ▼                                 ▼
      ┌───────────────┐                 ┌───────────────┐
      │ worker-tiktok │                 │worker-facebook│
      │  ffmpeg 9:16  │                 │ ffmpeg 9:16 / │
      │  init+publish │                 │ 16:9, session │
      └───────┬───────┘                 └───────┬───────┘
              ▼                                 ▼
        TikTok Content              Graph API /video_reels
        Posting API                 Graph API /videos
```

One `Asset` row, one `PublishJob` row per platform. Jobs share nothing except
the source asset. A TikTok 429 retries on its own queue while the Facebook job
is already `published`.

## Why not do it all in n8n

n8n is the right place for *triggers, scheduling, human approval, and
notifications*. It is the wrong place for the transfer itself:

- Binary data in n8n is buffered in memory. A 4 GB Facebook video will not
  survive that.
- Both platforms need byte-offset loops with resume. Expressing that in HTTP
  Request nodes is possible and miserable to debug.
- Retry semantics need to distinguish "429, back off" from "caption rejected,
  stop". Node-level retry cannot.

n8n calls this service's API and polls job state. See
[N8N_INTEGRATION.md](N8N_INTEGRATION.md).

## Why not an LLM agent

Uploading is deterministic: fixed endpoints, fixed state machine, strict byte
accounting. An agent in that loop adds nondeterminism, latency, and cost while
removing the ability to reason about correctness. Agents are useful *upstream*
— writing captions, picking a cover frame, deciding a posting time — and those
outputs enter the pipeline as ordinary fields on `POST /publish`.

The caption generator added for series is exactly that shape: it is an
operator-triggered endpoint that writes a `hook` into a database column, and
the publish path renders from that column whether or not anything ever
generated it. No worker calls a model, and no publish waits on one. See
[SERIES.md](SERIES.md).

## Transfer strategy: let the platform pull

Both platforms can fetch the file themselves given a URL:

| Platform | Pull mechanism | Push fallback |
|---|---|---|
| TikTok | `source: PULL_FROM_URL` at init *(needs a TikTok-verified domain)* | `FILE_UPLOAD`, 5–64 MiB chunks |
| Facebook Reel | `file_url` header on the rupload session | byte ranges with resume |
| Facebook feed video | `file_url` param on `/videos` | phased chunked upload |

Facebook uses pull whenever `R2_PUBLIC_BASE_URL` is set — Meta downloads from
any public URL, including a free `r2.dev` one.

TikTok additionally requires `TIKTOK_PULL_FROM_URL=true`, because it will only
fetch from a domain verified in its developer portal. An `r2.dev` URL is
public but unverifiable, so the flag defaults to off and TikTok uploads in
chunks. That asymmetry is deliberate and matches the file sizes: Facebook
videos are large and benefit most from pull, TikTok's are small and capped at
10 minutes, so chunking them is cheap.

Pull removes the chunk loop, the resume bookkeeping, and the memory pressure,
and R2's zero egress makes the platform's download free. The push paths are
fully implemented and used automatically otherwise.

This is why the "Facebook files are large" problem largely dissolves: the
large file never moves through this service.

## Storage: Cloudflare R2

Chosen over B2/S3/Drive for one reason that dominates: **zero egress fees**.
The pull-based upload strategy means every publish causes a platform to
download the full file, sometimes more than once across retries. On S3 that is
a per-gigabyte bill; on R2 it is free. The free tier is 10 GB stored, which is
enough for a rolling working set if renditions are pruned after publish.

R2 is S3-compatible, so [`sau/storage.py`](../sau/storage.py) is plain boto3
and can be pointed at S3, B2, or MinIO by changing the endpoint.

## Renditions

Each platform gets its own encode, cached in `renditions/<asset>/<platform>.mp4`
and recorded in the `renditions` table. Retrying a failed publish never
re-encodes. Specs live in `sau.transcode.SPECS`:

| Platform | Target | Duration cap | Fit |
|---|---|---|---|
| `tiktok` | 1080×1920 @ 6M | 600 s | pad to 9:16 |
| `facebook_reel` | 1080×1920 @ 6M | 90 s | pad to 9:16 |
| `facebook_video` | ≤1920×1080 @ 8M | none | preserve aspect |

All outputs are H.264 High / yuv420p / AAC with `+faststart`, so the moov atom
is at the front and platforms can begin processing before the last byte lands.

## Series: an ordering on top of the fan-out

One `Series` groups many assets that must publish in a fixed order, and carries
the caption material they share. It adds a layer above the fan-out without
changing it — a series part still becomes ordinary independent jobs.

```
       Series ──┬── SeriesPart(part_index=1) ── Asset ──┬── job: tiktok
                │                                       └── job: facebook_reel
                ├── SeriesPart(part_index=2) ── Asset ──┬── ...
                └── SeriesPart(part_index=3) ── Asset ──┴── ...
                        │
                        └─ hook: the one line that differs per episode
```

The ordering is the load-bearing part. The backlog used to sort by
`PublishJob.created_at`; a batch upload timestamps eight parts milliseconds
apart in whatever order the transfers finished, so part 5 could overtake part
3. `sau.schedule.order_groups` sorts series parts by `part_index` and places
the series as a whole by its earliest part, so a series stays contiguous and
in episode order while standalone assets keep their oldest-first behaviour.

## Scheduling: slots in the database, heartbeat in n8n

The posting rhythm is a `schedule_slots` table (12:00 / 18:00 / 21:00
`Asia/Bangkok` by default), not a Cron expression in n8n. n8n ticks every 15
minutes and calls `POST /schedule/tick`; this service decides whether a slot
has come due and releases one asset for each that has.

That inverts the obvious arrangement deliberately. The schedule is something
an operator retunes, and a redeploy is too high a price for moving a slot by an
hour. n8n keeps the part it is good at — a heartbeat, branching, notifying —
and stops being the place a posting time is defined. `last_fired_on` makes the
tick idempotent within a slot's local day, so a faster heartbeat cannot
double-post.

## Job state machine

```
PENDING ──▶ TRANSCODING ──▶ UPLOADING ──▶ PROCESSING ──▶ PUBLISHED
   ▲                                          │
   └──── retryable error, attempts < 3        └──▶ FAILED
```

`PROCESSING` means the bytes are delivered and the platform is encoding. That
phase is *polled*, never waited on: `run_publish_job` ends and schedules
`poll_publish_job` 30 s later, so no worker is parked on someone else's
encoder. Polling gives up after 80 attempts (~40 minutes) and fails the job.

Two retry layers, deliberately separate:

- **`sau.http.with_retries`** — inside one task, for 429/5xx/transport blips.
  Exponential backoff with full jitter.
- **task-level attempts** — `PublishJob.attempts`, max 3, survives a worker
  crash. Only retryable `PlatformError`s re-queue; an auth failure or a
  rejected caption fails immediately.

`PlatformError.retryable` is the only signal the queue reads. Getting the
classification right in each client's `_unwrap` is what makes retries correct.

## Credentials

The two platforms are opposite, which is the clearest single argument for
splitting the workers:

| | Facebook | TikTok |
|---|---|---|
| Access token life | long-lived Page token, effectively permanent | ~24 hours |
| Refresh | none needed | rotating refresh token, single use |
| Failure mode | revoked → code 190, fail hard | expired → refresh transparently |

Both are stored in the `oauth_tokens` table. `sau.tokens.get_access_token`
takes a row lock before refreshing, so concurrent workers cannot both consume
the same single-use TikTok refresh token.

## Adding a platform

1. Add a value to `Platform` and a spec to `transcode.SPECS`.
2. Write an adapter implementing `sau.platforms.base.Publisher`
   (`publish` + `check_status`).
3. Register it in `sau/platforms/__init__.py` and map it to a queue in
   `sau/queue/__init__.py`.
4. Add a worker service to `docker-compose.yml`.

Nothing in the API or the queue tasks changes. YouTube slots in this way.
