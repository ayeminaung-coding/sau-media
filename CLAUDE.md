# CLAUDE.md

Guidance for AI agents working in this repository.

## What this is

A fan-out publishing pipeline: one source video becomes one independent
publish job per social platform (TikTok, Facebook Reels, Facebook feed video).
FastAPI for the control plane, Redis/RQ for per-platform queues, R2 for media,
ffmpeg for per-platform renditions.

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing anything
structural. Read [docs/PLATFORM_NOTES.md](docs/PLATFORM_NOTES.md) before
touching anything under `sau/platforms/` — the API rules there are unintuitive
and the code encodes them deliberately.

## Invariants — do not break these

1. **Jobs are independent.** One `PublishJob` per platform per asset. Never
   introduce a code path where one platform's failure affects another's state.
   This is the whole design.

2. **`PlatformError.retryable` is the only retry signal.** The queue reads
   nothing else. Adding a new platform error code means classifying it in that
   client's `_unwrap`. Do not add retry logic elsewhere.

3. **Workers never block on a platform.** After the bytes are transferred, the
   task ends and schedules `poll_publish_job`. Do not add `sleep`-until-ready
   loops.

4. **Video bytes never pass through the API process.** Clients PUT directly to
   R2 with a presigned URL. Do not add an endpoint that accepts a video body.

5. **Prefer the platform-pull path.** When `R2_PUBLIC_BASE_URL` is set, both
   platforms fetch the file themselves. The push/chunk paths are the fallback,
   not the default.

6. **TikTok refresh tokens are single-use.** `sau.tokens.get_access_token`
   refreshes under `SELECT ... FOR UPDATE`. Removing that lock will
   intermittently invalidate the account's credentials.

## Layout

`client.py` = transport (HTTP, headers, error envelopes).
`publisher.py` = flow (the publish sequence).
Keep that separation; tests target the client boundary.

The console is a React/TypeScript app under `console/`, layered
`api → domain → hooks → features`; its rules are in
[console/README.md](console/README.md). Platform quirks belong in
`console/src/domain/platforms.ts`, never inline in a component.

Everything else is mapped in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#layout).

Credential acquisition is documented in
[docs/CREDENTIALS.md](docs/CREDENTIALS.md); do not duplicate those steps
elsewhere.

## Style

- Python 3.11+, full type annotations, `from __future__ import annotations`.
- `ruff` (line length 100) and `mypy --strict` must pass.
- Structured logging via `sau.logging.get_logger`, dotted event names
  (`tiktok.chunk.sent`), never f-strings in log messages.
- **Comments explain why, not what.** The non-obvious platform rules earn a
  comment; `# increment the counter` does not.
- No new dependencies without a reason that cannot be met by the existing set.

## Adding a platform

1. `Platform` enum value + `transcode.SPECS` entry.
2. Adapter implementing `sau.platforms.base.Publisher`.
3. Register in `sau/platforms/__init__.py`, map to a queue in `sau/queue/__init__.py`.
4. Worker service in `docker-compose.yml`.
5. Document its API quirks in `docs/PLATFORM_NOTES.md`.

## Testing

`pytest` covers pure logic only — chunk planning, error classification, retry
behaviour, transcode specs. No network, no database. Keep it that way: if a
change needs a live API to test, the logic is in the wrong place.

## Unverified areas

The platform request/response shapes were written against Meta's and TikTok's
published documentation but have **not been executed against the live APIs** in
this repository. The verification checklist at the end of
[docs/PLATFORM_NOTES.md](docs/PLATFORM_NOTES.md) lists exactly what to confirm.
If a publish fails with a field-name or parameter error, check there first.
