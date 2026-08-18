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

**Scheduled posting.** A Cron trigger reading from a content sheet, calling the
same flow. Posting time is entirely n8n's concern; the service publishes
whenever it is told.

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
