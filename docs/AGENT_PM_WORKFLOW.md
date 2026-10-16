# Agent PM Workflow

## Purpose

This repository needs a lightweight product-management layer for coding agents. The PM layer should turn product goals into small, verifiable tasks, preserve architectural decisions, and prevent agents from silently expanding scope.

The first version is file-based. It should be possible to move the records into the product database later without changing the task contract.

## Roles

### Product Manager agent

Owns problem framing, user value, scope, priorities, acceptance criteria, and task decomposition. It may update planning documents and task files, but it does not make product code changes unless explicitly assigned.

### Architecture agent

Owns boundaries, data flows, database shape, compatibility, security, and migration impact. It produces an architecture decision or a design note before a structural coding task starts.

### Implementation agent

Implements one task at a time, follows repository conventions, and provides test evidence. It must not change unrelated files or weaken an invariant.

### QA/reviewer agent

Checks the diff, requirements, tests, security impact, and documentation. It can request changes but does not silently fix the implementation.

### Release agent

Validates migration, configuration, observability, and rollback readiness. It is optional until the project has a production release process.

## Task lifecycle

```text
BACKLOG -> READY -> IN_PROGRESS -> IN_REVIEW -> DONE
                    \-> BLOCKED
                    \-> CANCELLED
```

Only one task should be `IN_PROGRESS` for the same component. Prefer one implementation agent per task to keep evidence attributable.

## Task contract

Every task must contain:

- Stable key, such as `PLAT-001`
- Problem statement
- User value
- Scope
- Non-goals
- Dependencies
- Acceptance criteria
- Test commands
- Relevant files and architecture notes
- Risk and rollback notes
- Definition of done

A task is ready only when an implementation agent can complete it without asking for a new product decision.

## Task template

```markdown
# TASK-XXX: Title

## Problem

## User value

## Scope

## Non-goals

## Dependencies

## Acceptance criteria

- [ ]

## Verification

- [ ] pytest
- [ ] ruff check .
- [ ] mypy --strict sau
- [ ] console build

## Files likely to change

## Risks and rollback
```

## Agent PM operating rules

1. Start with a user problem, not an implementation idea.
2. Separate the first useful release from later extensions.
3. Make one architectural decision per structural task.
4. Put database changes behind a migration and a rollback note.
5. Require tests for pure logic; require integration tests for orchestration boundaries.
6. Never let an agent publish content, rotate credentials, or change production configuration during normal coding work.
7. Do not mark a task done because code was written. Done means acceptance criteria and verification passed.
8. Preserve repository invariants in the task description and reviewer checklist.
9. Update the roadmap and decision log when scope changes.
10. Keep an open question list instead of hiding assumptions in implementation.

## Suggested roadmap

### R0: Foundation and product contract

- Decide the multi-workspace tenancy model.
- Reconcile the transcode contract with the actual implementation.
- Add authentication and authorization.
- Add migrations and remove production `create_all()`.
- Add an outbox, idempotency keys, and stale-job recovery.
- Document the provider and plugin contracts.

### R1: Planning MVP

- Add workspaces, members, content pillars, and ideas.
- Add daily and weekly brief generation.
- Add prompt registry and LLM run ledger.
- Add content items, versions, and platform variants.
- Add manual approval workflow.
- Add import and export for workspace data.

### R2: Calendar and operations

- Add schedule windows, quiet hours, and frequency caps.
- Add DST-aware calendar behavior.
- Add notifications for approval, publish, failure, and stale jobs.
- Add a health dashboard and dead-letter handling.
- Add optional metrics import and recommendation feedback.

### R3: Ecosystem

- Add a documented third-party adapter SDK.
- Add more platforms and storage providers.
- Add community prompt packs and templates.
- Add a hosted control plane while keeping self-hosting first-class.
- Add a task database integration for Agent PM records.

## Handoffs

### PM to architecture

Provide the problem, target users, constraints, non-goals, and open questions. The architect returns boundaries, data flows, migration impact, and unresolved risks.

### Architecture to implementation

Provide an approved design note, schema changes, interface contracts, tests, and rollback plan. The implementer works on one task only.

### Implementation to QA

Provide the task key, diff summary, tests run, known limitations, and migration notes. QA returns pass, request changes, or block with evidence.

### QA to PM

Report which user value is delivered, which acceptance criteria remain open, and which risks changed. PM decides whether to close, split, or reprioritize.

## Repository layout

- `docs/OPEN_PLATFORM_VISION.md`: product direction and MVP boundary.
- `docs/TARGET_ARCHITECTURE.md`: target components and data flows.
- `docs/USE_CASES.md`: actors, use-case diagram, and acceptance criteria.
- `docs/DATABASE_DESIGN.md`: proposed relational model and migration path.
- `docs/AGENT_PM_WORKFLOW.md`: this operating model.
- `.opencode/agents/`: agent role definitions.
- `.opencode/commands/`: repeatable PM planning and review commands.

## Definition of done for an agent task

- The task has an accepted scope and non-goals.
- Code and schema follow existing conventions.
- Tests cover new behavior at the appropriate boundary.
- Documentation is updated when behavior or operations change.
- Security and tenant-isolation implications are documented.
- Lint, typecheck, and build commands pass or the blocker is recorded.
- QA has reviewed the evidence.
- No unrelated changes are included.
