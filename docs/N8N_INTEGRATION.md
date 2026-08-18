# n8n Integration

n8n owns **when** and **whether** to post. This service owns **how**. The
boundary is the HTTP API; n8n never touches video bytes.

Inside the compose network the API is `http://api:8000`.

## Publish workflow

```
┌─────────────┐   ┌──────────────┐   ┌───────────┐   ┌──────────────┐
│  Trigger    │──▶│ POST         │──▶│ PUT file  │──▶│ POST /assets │
│ (schedule / │   │ /assets/     │   │ to R2     │   │  (register)  │
│  webhook /  │   │  upload-url  │   │ (presigned│   └──────┬───────┘
│  Drive)     │   └──────────────┘   │  URL)     │          │
└─────────────┘                      └───────────┘          ▼
                                                     ┌──────────────┐
                                                     │ POST /publish│
                                                     │  targets: [] │
                                                     └──────┬───────┘
                                                            ▼
                     ┌───────────────────────────────────────────┐
                     │ Wait 60s → GET /assets/{id}/jobs → IF all │
                     │ terminal? ── no ──┘                       │
                     └────────────┬──────────────────────────────┘
                                  ▼
                  ┌───────────── Switch ─────────────┐
                  ▼                                  ▼
          all published                      any failed
        → notify success                → notify with last_error
                                        → optional POST /jobs/{id}/retry
```

## Node configuration

**1. Get an upload URL** — HTTP Request
`POST http://api:8000/assets/upload-url`, body `{"filename": "{{$json.filename}}"}`

**2. Upload the file** — HTTP Request
`PUT {{$json.upload_url}}`, body type *Binary File*, header
`Content-Type: video/mp4`.

> If the source is already reachable at a public URL, skip steps 1–2 entirely:
> copy it into R2 out of band and register the key. Moving bytes through n8n
> is the thing to avoid — it buffers binaries in memory.

**3. Register** — HTTP Request
`POST http://api:8000/assets`, body `{"storage_key": "{{$node["Get an upload URL"].json.storage_key}}"}`

**4. Fan out** — HTTP Request
`POST http://api:8000/publish`

```json
{
  "asset_id": "{{$json.id}}",
  "targets": [
    { "platform": "tiktok",        "caption": "{{$json.caption}}" },
    { "platform": "facebook_reel", "caption": "{{$json.caption}}" }
  ]
}
```

Returns `202` immediately with one job per target. Nothing blocks.

**5. Poll** — Wait (60 s) → HTTP Request `GET /assets/{{$json.asset_id}}/jobs`
→ IF `{{ $json.every(j => ["published","failed"].includes(j.state)) }}`
→ false loops back to Wait.

Reels and TikTok typically settle in 1–5 minutes; a long feed video can take
longer. The service itself gives up after ~40 minutes and marks the job
`failed`, so the n8n loop cannot spin forever.

**6. Branch on outcome** — Switch on whether any job has `state == "failed"`,
then Slack/Telegram/email with `platform` and `last_error`.

## Things worth wiring up

**Per-platform retry.** Because jobs are independent, the failure branch can
call `POST /jobs/{{$json.id}}/retry` for just the failed leg. The published
sibling is untouched and is *not* re-uploaded.

**Scheduled posting.** See the daily backlog below — that is the shipped
version of this idea.

**Human approval.** Insert a Wait-for-Webhook node between registration and
`POST /publish`. Nothing has been sent to any platform at that point.

**Caption generation.** If you want an LLM writing captions, that belongs
*before* step 4 — its output becomes the `caption` field. Keep it out of the
upload path.

## Why the split

n8n is good at triggers, branching, waiting on humans, and notifying. It is
bad at multi-gigabyte binaries and byte-offset resume loops. This division
gives each side the part it handles well, and means a broken workflow never
corrupts an in-flight upload.

---

# Daily backlog

One post per day, drawn from a queue filled by hand in the console.

The backlog lives in Postgres, not in n8n and not in Redis: a month of posts
scheduled onto RQ would vanish with a `docker compose down` or a Redis flush.
Jobs sit in state `scheduled` — created, captioned, and targeted, but never
enqueued. n8n decides only *when* one is released.

```
Console                          n8n (daily 09:00)              Workers
───────                          ─────────────────              ───────
POST /publish {schedule:true}
  → jobs in state `scheduled`
    (nothing queued)
                                 GET /schedule?limit=1
                                 IF asset_id exists
                                 POST /assets/{id}/release ────▶ transcode,
                                                                 upload,
                                 Wait 4m                         publish
                                 GET /assets/{id}/jobs
                                 → notify
```

## Endpoints

| Call | Effect |
|---|---|
| `POST /publish` with `"schedule": true` | Creates the jobs in `scheduled`. Nothing is queued. |
| `GET /schedule?limit=n` | Backlog grouped by asset, **oldest first** — the order it publishes in. |
| `POST /assets/{id}/release` | Flips that asset's `scheduled` jobs to `pending` and queues them. 409 if it has none. |
| `DELETE /assets/{id}/schedule` | Drops it from the backlog. Only deletes `scheduled` rows, so an in-flight job is never cancelled. |

A `scheduled` job that somehow reaches a worker is declined by `_claim` rather
than run: reaching a worker without going through `release_asset` means the
schedule never chose it, and publishing it would post on the wrong day.

## Install the workflow

1. <http://localhost:5678> → *Workflows* → *Import from File* →
   `n8n/daily-post.workflow.json`.
2. Open **Daily 09:00** and confirm the hour.
3. Toggle **Active**. Without this it only ever runs when you click Execute —
   a manual run is logged as `"isManual": true` and no Cron is armed.

The timezone is `Asia/Bangkok`, set in two places that must agree: the
workflow's own `settings.timezone`, and `GENERIC_TIMEZONE` in
`docker-compose.yml`. A workflow imported before that variable was set may
have captured UTC — check the workflow settings if posts land seven hours off.

## Notifications

`Summarise` and `Backlog Empty` end their branches with a JSON summary and no
side effect, so add a Slack/Telegram/email node after each. Wire both: a silent
failure and a switched-off workflow look identical from the outside, which is
why the empty-backlog branch notifies at all.

`Summarise` reports per platform rather than pass/fail, because a mixed result
is normal — TikTok can fail while the Reel publishes. Jobs still on the queue
after the 4-minute wait are reported as `still_running`, not as failures; a
long Facebook video can take longer than that.
