# Agent Backlog

## Status vocabulary

`BACKLOG`, `READY`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `BLOCKED`, `CANCELLED`

## Prioritized tasks

| Key | Task | Priority | Status | Depends on | Verification |
|---|---|---:|---|---|---|
| FND-001 | Reconcile the actual transcode contract with docs and UI | P0 | IN_REVIEW | — | Worker integration test, ffprobe metadata test, docs review |
| FND-001-B | Add deterministic media profile identity and source validation | P0 | IN_REVIEW | FND-001 | Pure transcode tests |
| FND-001-C | Add idempotent media preparation orchestration | P0 | IN_REVIEW | FND-001-B | Preparation, reuse, failure, and cleanup tests |
| FND-002 | Add authentication and workspace authorization | P0 | BACKLOG | FND-001 | API auth tests, tenant-isolation tests |
| FND-003 | Add Alembic migrations and a production migration path | P0 | BACKLOG | FND-002 | Fresh DB and upgrade-path tests |
| REL-001 | Add transactional outbox and idempotent queue dispatch | P1 | BACKLOG | FND-003 | Dispatch failure and duplicate delivery tests |
| REL-002 | Add atomic job claim, stale-job watchdog, and dead letters | P1 | BACKLOG | REL-001 | Crash recovery and concurrent claim tests |
| SCH-001 | Add schedule windows, quiet hours, frequency caps, and DST behavior | P1 | BACKLOG | FND-002 | Timezone and concurrent tick tests |
| PLN-001 | Add workspace, user, member, and role model | P1 | BACKLOG | FND-002 | Authorization and migration tests |
| PLN-002 | Add idea inbox and content brief generation | P1 | BACKLOG | PLN-001, LLM-001 | LLM fallback and workspace isolation tests |
| LLM-001 | Add provider registry, prompt versions, and run ledger | P1 | READY | PLN-001 | Schema validation and provider fallback tests |
| CNT-001 | Add content items, versions, media, and platform variants | P1 | BACKLOG | PLN-001, FND-001 | Version and approval tests |
| APR-001 | Add approval inbox and version-bound approvals | P1 | BACKLOG | CNT-001, SCH-001 | Approval and invalidation tests |
| EXT-001 | Add workspace import and export | P2 | BACKLOG | PLN-001, CNT-001 | Round-trip export tests |
| OBS-001 | Add health metrics, alerts, and job dashboards | P2 | BACKLOG | REL-002 | Failure and stale-job observability tests |
| PMX-001 | Add file-to-database Agent PM task synchronization | P2 | BACKLOG | FND-003 | Idempotent synchronization tests |

## Task notes

### FND-001

Owner accepted the contract: use real, validated, versioned per-platform renditions. See [ADR-0001](decisions/0001-prepared-per-platform-renditions.md). FND-001 remains in review because the full worker and migration slices have not started.

### LLM-001

LLM output must be structured and versioned. The LLM gateway is upstream of publishing and must not be required for manual content creation. Do not store secret values in prompt or run records.

### REL-001

The database must write jobs and outbox rows in one transaction. A dispatcher must safely retry enqueueing with the same idempotency key.

### SCH-001

A schedule release must be safe under concurrent heartbeat requests. Invalid timezone names, DST gaps, and repeated local times need explicit behavior.

## Handoff checklist

- [ ] Problem and user value are documented.
- [ ] Scope and non-goals are explicit.
- [ ] Acceptance criteria are testable.
- [ ] Architecture impact is reviewed.
- [ ] Migration and rollback impact are reviewed.
- [ ] Security and tenant-isolation impact are reviewed.
- [ ] Verification evidence is attached.
- [ ] QA review outcome is recorded.
