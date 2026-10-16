# ADR-0001: Prepared per-platform renditions

## Status

Accepted for implementation. This records the product contract; it is not a claim that the runtime is already implemented.

## Context

The repository currently uploads a source object directly to R2, creates a `Rendition` row that aliases the source key, and sends that source key to the platform publisher. The worker does not call `ffprobe` or `ffmpeg`. The `TRANSCODING` state exists in the model and UI but is not reached.

The architecture and development documents promise per-platform encoding, rendition caching, metadata backfill, and ffmpeg workers. The active UI also tells operators that a rendition is being built. The current implementation and the product contract therefore disagree.

## Decision

Adopt a single contract:

> A source media object is canonical input. Before transfer, each platform job must resolve a validated, immutable, versioned, platform-specific rendition. The source object is never treated as a prepared rendition.

The first release should not accept arbitrary media silently. It should validate the source against a versioned platform profile and fail preparation when the source cannot be handled. Duration overflow should fail by default rather than silently trimming user content.

## Why this direction

- It preserves the product promise of one source and many destinations.
- It matches the active `TRANSCODING` state and existing architecture documents.
- It makes the `Rendition` model represent a real output rather than a source alias.
- It supports different aspect ratios, duration limits, and codecs per platform.
- It keeps each platform preparation and publish job independent.
- It gives a custom deployment a stable profile contract for adding platform adapters.

## Non-goals for this decision

- No arbitrary user-supplied ffmpeg command strings.
- No operator-selectable dual contract in the first release.
- No automatic migration of already-published jobs.
- No new LLM dependency in the media path.
- No changes to platform retry classification beyond a separate preparation failure policy.

## Data flow

```text
source object
  -> controlled temporary download
  -> ffprobe
  -> source validation
  -> platform profile selection
  -> ffmpeg output in temporary storage
  -> output probe and verification
  -> claim-scoped rendition object upload
  -> Rendition(READY)
  -> platform publisher
```

The platform publisher receives the prepared rendition key and should not know whether storage uses pull URLs, chunk upload, or another adapter mechanism.

A claim-scoped object key prevents a stale worker from overwriting a newer worker's output. The cost is that a failed or superseded claim can leave an object without a database row, so orphan cleanup and retention are mandatory operations.

## Profile contract

Each platform profile should declare a stable profile key and version, then include:

- Supported input containers and codecs
- Output codec, pixel format, dimensions, and bitrate
- Maximum duration and maximum source size
- Duration overflow policy
- Audio requirements
- Deterministic profile hash

The profile should be declared near the platform adapter and validated by a pure media module. Deployment configuration may select overrides, but users should not be able to inject arbitrary shell commands.

## State model

Rendition preparation requires a state separate from platform transfer:

```text
PENDING -> PROCESSING -> READY
                         \-> FAILED
```

A publish job follows:

```text
PENDING -> TRANSCODING -> UPLOADING -> PROCESSING -> PUBLISHED
```

A preparation failure must remain isolated to the platform job that requested the rendition. It must not change sibling platform jobs.

## Identity and idempotency

A rendition identity should be deterministic:

```text
workspace_id + asset_id + platform + profile_version/profile_hash
```

A worker must claim a rendition atomically. A ready rendition may be reused. An incomplete rendition may be retried or marked failed. A ready output must never be overwritten by another worker.

The publish job should bind to the exact rendition profile it resolved when it was released, so a later profile change cannot silently redirect a queued job.

## Migration

Existing rendition rows are source aliases and must be marked as legacy or unprepared. They must not be treated as `READY` outputs.

1. Add preparation fields and a versioned profile identity.
2. Mark existing source-alias rows as legacy.
3. Leave published history unchanged.
4. Rebuild pending and failed jobs on an explicit retry.
5. Keep source objects available for rollback and manual recovery.
6. Do not delete legacy or new rendition objects automatically until retention is designed.

## Implementation slices

### FND-001-A: Contract and documentation

- Record accepted source and duration policies.
- Update architecture, development, deployment, README, and implementation-plan documents.
- Remove language that treats a source alias as an encoded rendition.

### FND-001-B: Pure profile and validation

- Add deterministic profile identity and validation.
- Add timeout, resource, and input/output limit settings.
- Test profiles and validation without network or database access.

### FND-001-C: Preparation orchestration

- Add atomic rendition claims and leases.
- Download, probe, transcode, verify, and upload with temporary-file cleanup.
- Persist metadata and `READY` only after successful upload.

### FND-001-D: Worker integration

- Add the `TRANSCODING` transition.
- Prepare before platform transfer.
- Keep platform errors and media errors classified separately.
- Preserve independent job and retry behavior.

### FND-001-E: Runtime packaging and UI

- Install ffmpeg and ffprobe in the worker image.
- Add readiness checks for required binaries and storage.
- Show source metadata, preparation state, and target-specific errors.
- Keep the UI honest about queued, processing, and failed states.

### FND-001-F: Verification and migration

- Add mocked worker, storage, ffmpeg, and failure-cleanup tests.
- Add metadata persistence, rendition reuse, and legacy-alias tests.
- Add Docker smoke tests for ffmpeg and ffprobe.
- Run lint, strict typecheck, and console build.

## Open questions

- Which containers, codecs, frame rates, and audio profiles must the first release accept?
- Should source probing happen at asset registration or when the first job is released?
- Should media preparation use the platform queues or a separate media queue?
- How long should prepared renditions be retained?
- Should media preparation have a separate `PreparationError.retryable` contract?

## Definition of done

- Code, schema, Docker image, worker state machine, API, console, and documentation describe the same contract.
- No publish path passes an unprepared source alias to a platform.
- Each platform rendition can be prepared, reused, retried, and failed independently.
- Invalid or overlong source media produces an explicit operator-visible error.
- Temporary files are cleaned up on success, failure, and timeout.
- Tests cover pure profile logic and the orchestration boundary.
