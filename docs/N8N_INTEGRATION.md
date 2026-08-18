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

**Scheduled posting.** See the backlog below — that is the shipped version of
this idea.

**Human approval.** Insert a Wait-for-Webhook node between registration and
`POST /publish`. Nothing has been sent to any platform at that point.

**Caption generation.** If you want an LLM writing captions, that belongs
*before* step 4 — its output becomes the `caption` field. Keep it out of the
upload path. For a series the service does this itself, at
`POST /series/{ref}/generate-hooks`, and it is still upstream: it writes a
database column that the publish path renders from.

## Why the split

n8n is good at triggers, branching, waiting on humans, and notifying. It is
bad at multi-gigabyte binaries and byte-offset resume loops. This division
gives each side the part it handles well, and means a broken workflow never
corrupts an in-flight upload.

---

# Scheduled backlog

Several posts a day, drawn from a queue filled by hand in the console.

The backlog lives in Postgres, not in n8n and not in Redis: a month of posts
scheduled onto RQ would vanish with a `docker compose down` or a Redis flush.
Jobs sit in state `scheduled` — created, captioned, and targeted, but never
enqueued.

## Where the schedule lives

**Not in n8n.** The posting times are rows in `schedule_slots`, edited in the
console under Backlog → Schedule. n8n ticks every 15 minutes and the service
decides whether a slot has come due.

This is the opposite of the obvious arrangement, and it is deliberate: the
rhythm is something an operator retunes, and a redeploy is too high a price for
moving a slot by an hour. n8n keeps the parts it is good at — a heartbeat,
branching, waiting on humans, notifying — and stops being a place a posting
time is defined.

```
Console                       n8n (every 15 min)            Workers
───────                       ──────────────────            ───────
POST /series/{id}/publish
  → jobs in state `scheduled`
    (nothing queued)
                              POST /schedule/tick
                              │  service checks the slots
                              │  releases one asset per
                              │  slot that is due    ──────▶ transcode,
                              │                              upload,
                              IF fired > 0                   publish
                              Wait 4m
                              GET /assets/{id}/jobs
                              → notify
```

Defaults are 12:00, 18:00 and 21:00 `Asia/Bangkok`. They are seeded only into
an empty table, so re-running `scripts/init_db.py` never resets a schedule that
has since been edited.

## Endpoints

| Call | Effect |
|---|---|
| `POST /publish` with `"schedule": true` | Creates the jobs in `scheduled`. Nothing is queued. |
| `POST /series/{ref}/publish` | The same, for every episode of a series at once. |
| `GET /schedule?limit=n` | Backlog grouped by asset, **in the exact order it will publish** — series parts by episode number, standalone assets oldest first. |
| `GET /schedule/slots` / `PUT /schedule/slots` | Read or replace the posting times. |
| `GET /schedule/plan?count=n` | The next firing times, paired with what is queued for them. |
| `POST /schedule/tick` | Release one asset for every slot that has come due. **This is what n8n calls.** |
| `POST /assets/{id}/release` | Release one asset immediately, ignoring the slots. The "post now" button. |
| `DELETE /assets/{id}/schedule` | Drops it from the backlog. Only deletes `scheduled` rows, so an in-flight job is never cancelled. |
| `POST /schedule/slots/reset` | Clears every fired marker, so today's slots can fire again. |

A `scheduled` job that somehow reaches a worker is declined by `_claim` rather
than run: reaching a worker without going through a release means the schedule
never chose it, and publishing it would post at the wrong time.

## Why the tick can run more often than the slots

`POST /schedule/tick` is idempotent within a slot's local day.
`ScheduleSlot.last_fired_on` is stamped on release, so ticking every minute
inside the grace window still publishes exactly one asset per slot. Three
consequences worth knowing:

- A slot fires up to **60 minutes late**, then skips for the day. Better a
  missed slot than a backlog dumped at an hour nobody chose.
- A slot that comes due with an **empty backlog is not stamped as fired**, so it
  stays armed for the rest of its grace window — content added a few minutes
  late still catches the slot it was meant for.
- **Saving the slots re-arms them all.** An operator who has just moved this
  evening's slot means the new time, not "already fired, see you tomorrow".

## Install the workflow

1. <http://localhost:5678> → *Workflows* → *Import from File* →
   `n8n/slot-tick.workflow.json`.
2. Toggle **Active**. Without this it only ever runs when you click Execute —
   a manual run is logged as `"isManual": true` and no Cron is armed.

There is no hour to confirm in the workflow any more; the times are in the
console. The 15-minute interval only bounds how late a slot can fire, and any
interval below the 60-minute grace window works.

> Replaces `daily-post.workflow.json`, which released one asset at 09:00
> regardless of the stored slots. If both are imported and active, they will
> double-post — delete the old one.

The timezone still matters in two places that must agree: the workflow's
`settings.timezone` and `GENERIC_TIMEZONE` in `docker-compose.yml`. Slots carry
their own IANA zone, so a slot's time is unambiguous either way, but n8n's own
scheduling and log timestamps are not.

## Notifications

`Summarise` and `Nothing Released` end their branches with a JSON summary and
no side effect, so add a Slack/Telegram/email node after each.

`Nothing Released` fires on most ticks — that is the normal case — so gate the
notification on its `notify` field, which is true only when a slot came due
with an empty backlog. That case is worth telling someone about: from the
outside it looks exactly like a switched-off workflow.

`Summarise` reports per platform rather than pass/fail, because a mixed result
is normal — TikTok can fail while the Reel publishes. Jobs still on the queue
after the 4-minute wait are reported as `still_running`, not as failures; a
long Facebook video can take longer than that.
