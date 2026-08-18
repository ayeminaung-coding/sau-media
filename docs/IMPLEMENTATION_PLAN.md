# Implementation Plan

Sequenced so the slowest external dependency — platform app review — starts on
day one and runs in parallel with the build.

Legend: `[x]` in this repo · `[ ]` still to do · `[!]` blocked on an external
party.

---

## Phase 0 — Platform access (start immediately, blocks go-live)

Step-by-step instructions for every value below: **[CREDENTIALS.md](CREDENTIALS.md)**.

App review is the critical path, not the code. Both platforms will happily let
you build and test against a private/self-only account for weeks; neither will
let you post publicly without review.

- [!] **Meta**: create app, add *Facebook Login for Business*, request
      `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
      `publish_video`. Submit for App Review with a screencast.
- [!] **TikTok**: register app on the TikTok for Developers portal, request the
      *Content Posting API* with scopes `video.publish` and `user.info.basic`,
      submit for audit.
- [ ] Verify the R2 custom domain in the TikTok portal (required for
      `PULL_FROM_URL`) **and** confirm it serves `Content-Type: video/mp4`.
- [ ] Mint a long-lived Facebook Page token; store via `scripts/seed_tokens.py`.
- [ ] Complete the TikTok OAuth handshake once; store the access/refresh pair.

**Until review passes:** TikTok forces `SELF_ONLY` on every post (the publisher
detects this via `creator_info` and clamps automatically), and Facebook posts
are visible only to app roles. This is expected, not a bug.

## Phase 1 — Foundations `[x]`

- [x] Typed settings (`sau/config.py`), structured JSON logging.
- [x] Schema: `assets`, `renditions`, `publish_jobs`, `oauth_tokens`.
- [x] R2 storage layer with presigned PUT, ranged reads, chunk iteration.
- [x] Error taxonomy with the `retryable` flag the queue depends on.
- [x] HTTP client with jittered exponential backoff.

## Phase 2 — Media pipeline `[x]`

- [x] ffprobe metadata extraction, backfilled at first transcode.
- [x] Per-platform ffmpeg specs (9:16 padded, 16:9 preserved, `+faststart`).
- [x] Rendition caching so retries never re-encode.

## Phase 3 — Platform adapters `[x]`

- [x] `Publisher` interface + registry.
- [x] TikTok: creator-info query, privacy clamping, `PULL_FROM_URL`,
      `FILE_UPLOAD` with compliant chunk planning, status polling.
- [x] Facebook Reels: rupload session, hosted `file_url`, resumable byte
      ranges using the server-reported offset, finish phase.
- [x] Facebook feed video: hosted `file_url`, phased chunked upload following
      the server's `start_offset`/`end_offset` windows.
- [x] Token refresh under a row lock (TikTok refresh tokens are single-use).

## Phase 4 — Orchestration `[x]`

- [x] Per-platform Redis queues; independent workers.
- [x] `run_publish_job` (transcode → transfer → start) and `poll_publish_job`
      (status polling) split so workers never block on platform encoding.
- [x] Attempt limits, error classification, per-job retry.
- [x] FastAPI: presigned upload, asset registration, fan-out publish, job
      status, single-job retry.
- [x] docker-compose: postgres, redis, api, two workers, n8n.

## Phase 5 — Wire up n8n `[ ]`

- [ ] Build the publish workflow described in
      [N8N_INTEGRATION.md](N8N_INTEGRATION.md).
- [ ] Add a failure branch that notifies (Slack/Telegram/email) with
      `job.last_error`.
- [ ] Add a scheduled workflow that posts from a content queue at fixed times.

## Phase 6 — Production hardening `[ ]`

- [ ] Replace `create_all()` with Alembic migrations.
- [ ] API authentication (shared secret header is sufficient for a private
      deployment; the API must not be internet-exposed unauthenticated).
- [ ] Lifecycle rule on R2: delete renditions 7 days after a job reaches
      `published`, to stay inside the 10 GB free tier.
- [ ] Dead-letter handling: a queue for jobs that exhausted attempts.
- [ ] Metrics: job duration by platform, failure rate by error code.
- [ ] Alembic-backed `oauth_tokens` encryption at rest, or move tokens to a
      secrets manager.

## Phase 7 — Extensions `[ ]`

- [ ] YouTube adapter, folding the existing upload script into the same
      `Publisher` interface.
- [ ] Instagram Reels (shares the Graph API and the Page token, so it is
      mostly a new edge on the existing Facebook client).
- [ ] Optional agent step upstream: caption/hashtag generation writing into
      `PublishTarget.caption` before `POST /publish`.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| App review rejected | Cannot post publicly | Start Phase 0 first; keep the screencast and privacy policy ready |
| TikTok refresh token consumed twice | Both tokens invalidated, manual re-auth | Row lock in `sau.tokens.get_access_token` |
| Free-tier 10 GB exceeded | Uploads start failing | Phase 6 lifecycle rule; renditions are the bulk |
| Platform API drift | Silent failures | All API assumptions listed in [PLATFORM_NOTES.md](PLATFORM_NOTES.md) with a verification checklist |
| Large FB upload times out | Job stuck | Prefer `file_url`; push path resumes from the server-reported offset |
