# Platform Notes

Everything this codebase assumes about the two platform APIs, in one place.

> **Verify before go-live.** Meta and TikTok change limits, field names, and
> review requirements without notice. Each assumption below is tagged with the
> code that depends on it. Treat this file as the checklist to re-read against
> the live docs when something starts failing.

---

## TikTok — Content Posting API

Base: `https://open.tiktokapis.com/v2`
Docs: <https://developers.tiktok.com/doc/content-posting-api-get-started>

### Authentication

- Access token lifetime ≈ **24 hours**. Refresh token ≈ 365 days.
- **The refresh token rotates on every use.** Using a stale one invalidates the
  pair and forces a manual re-authorisation. This is why
  `sau.tokens.get_access_token` takes `SELECT ... FOR UPDATE` before
  refreshing — two workers refreshing concurrently would brick the account.
- Refresh: `POST /oauth/token/`, form-encoded, `grant_type=refresh_token`.
  → `sau/platforms/tiktok/client.py::refresh_access_token`
- Obtaining the initial pair: [CREDENTIALS.md](CREDENTIALS.md#part-3--tiktok).

### Error envelope

Failures arrive with **HTTP 200** and `error.code != "ok"`. Checking the status
code alone silently accepts them.
→ `sau/platforms/tiktok/client.py::_unwrap`

### Publish flow

1. `POST /post/publish/creator_info/query/` — **required** before a direct
   post. Returns `privacy_level_options`, `max_video_post_duration_sec`,
   `creator_username`.
2. `POST /post/publish/video/init/` with `post_info` + `source_info`.
3. `PULL_FROM_URL`: TikTok downloads from `video_url`. **The URL's domain
   prefix must be verified in the developer portal**, else HTTP 403
   `url_ownership_unverified`. A presigned R2 endpoint will not work, and
   neither will a free `pub-<hash>.r2.dev` URL — that domain is Cloudflare's,
   so it can never be verified. It must be a custom domain bound to the
   bucket. Gated behind `TIKTOK_PULL_FROM_URL`, default off.
4. `FILE_UPLOAD`: PUT each chunk to the returned `upload_url` with
   `Content-Range: bytes <start>-<end>/<total>`.
5. `POST /post/publish/status/fetch/` until `PUBLISH_COMPLETE` or `FAILED`.

### Chunk rules — the fiddly part

- Chunk size **5 MiB minimum, 64 MiB maximum**.
- **At most 1000 chunks.**
- `total_chunk_count = floor(video_size / chunk_size)` — the remainder rides
  along with the **final** chunk, which is therefore larger than `chunk_size`.
  Sending it as an extra short chunk is rejected.
- A file smaller than 5 MiB must be one chunk with `chunk_size == video_size`.

→ `sau/platforms/tiktok/publisher.py::plan_chunks`, covered by
`tests/test_chunking.py`.

There is **no documented resume-at-offset endpoint** for `FILE_UPLOAD`. A
failed transfer restarts from a fresh `init`. Acceptable because TikTok
renditions are capped at 10 minutes and are therefore small.

### One text field

`post_info.title` is the only text TikTok accepts, and it is displayed as the
post caption. It therefore carries the **caption**, not the title: for a series
the title template renders just the header line, so preferring it would publish
the header alone and silently drop the hook and the hashtag block.

### Audit gate

Before the app passes TikTok's audit, every post is forced to `SELF_ONLY`
regardless of what is requested. `_build_post_info` reads
`privacy_level_options` and clamps, logging `tiktok.privacy.clamped`, rather
than letting init fail.

### Known typo

The status response field is `publicaly_available_post_id` (sic). Spelled that
way in `_post_url` on purpose.

---

## Facebook — Graph API

Base: `https://graph.facebook.com/<version>` (pinned by
`FACEBOOK_GRAPH_VERSION`)
Docs: <https://developers.facebook.com/docs/video-api> and
<https://developers.facebook.com/docs/video-api/guides/reels-publishing>

### Authentication

- Uses a **Page access token**, not a User token.
- A long-lived Page token derived from a long-lived User token does not
  expire, which is why no refresh callback is registered for `facebook` in
  `sau.tokens`.
- Minting one: User token → exchange for long-lived User token via
  `/oauth/access_token?grant_type=fb_exchange_token` → `GET /me/accounts` and
  read the Page's `access_token`. Full walkthrough in
  [CREDENTIALS.md](CREDENTIALS.md#part-2--facebook).
- Required permissions: `pages_show_list`, `pages_read_engagement`,
  `pages_manage_posts`, `publish_video`.

### Error codes

`sau/platforms/facebook/client.py` classifies:

| Codes | Meaning | Handling |
|---|---|---|
| 1, 2 | transient backend fault | retry |
| 4, 17, 32, 341, 613 | rate limiting | retry |
| 10, 102, 190, 200, 803 | auth / permission | fail hard |

### Reels — session upload

1. `POST /<page-id>/video_reels` with `upload_phase=start`
   → `{video_id, upload_url}`.
2. Either
   - `POST <upload_url>` with header `file_url: <public url>` (Meta pulls), or
   - `POST <upload_url>` with headers `offset`, `file_size` and the byte range
     as the body.
   Both need `Authorization: OAuth <page token>`.
3. `POST /<page-id>/video_reels` with `upload_phase=finish`,
   `video_state=PUBLISHED`, `description=<caption>`.

**Resume** reads `status.uploading_phase.bytes_transferred` from
`GET /<video-id>?fields=status` rather than trusting a local counter — Meta is
the authority on how many bytes it actually holds.
→ `FacebookReelPublisher._server_offset`

Reels are capped at 90 seconds; `transcode.SPECS` trims to that.

### Feed video — phased upload

1. `POST /<page-id>/videos` `upload_phase=start&file_size=N`
   → `{upload_session_id, video_id, start_offset, end_offset}`.
2. `POST` `upload_phase=transfer` with `start_offset` and the chunk as a
   multipart `video_file_chunk`. **The response carries the next
   `start_offset`/`end_offset`** — Meta, not this code, chooses the window.
   Loop until they converge.
3. `POST` `upload_phase=finish` with `upload_session_id` and `description`.

Or, far simpler: `POST /<page-id>/videos` with a `file_url` parameter and let
Meta download it. Used automatically when `R2_PUBLIC_BASE_URL` is set.

### Status

`GET /<video-id>?fields=status,permalink_url` →
`status.video_status` ∈ `{uploading, processing, ready, error}`, plus per-phase
detail in `uploading_phase` / `processing_phase` / `publishing_phase`.
`permalink_url` comes back **relative** (`/reel/123`) and is normalised in
`_permalink`.

---

## Verification checklist

Re-check these against live docs before go-live, and again whenever a
previously working publish starts failing:

- [ ] TikTok chunk minimum/maximum and the 1000-chunk ceiling
- [ ] TikTok status enum values (`PUBLISH_COMPLETE`, `PROCESSING_UPLOAD`, …)
- [x] TikTok domain-verification requirement for `PULL_FROM_URL` — confirmed
      against the live docs (403 `url_ownership_unverified`)
- [ ] Facebook Reels duration cap and `video_reels` phase parameters
- [ ] Facebook feed video maximum file size and duration for your Page
- [ ] Graph API version in `FACEBOOK_GRAPH_VERSION` is still supported
- [ ] The retryable/auth error-code tables above
