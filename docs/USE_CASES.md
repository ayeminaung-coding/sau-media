# Use Cases

## Actors

- **Owner**: manages the workspace, connections, policies, and publishing.
- **Editor**: creates and edits content, media, captions, and drafts.
- **Approver**: reviews and approves or rejects scheduled content.
- **Scheduler**: releases approved content at the correct time.
- **Platform worker**: prepares and submits one platform post.
- **LLM gateway**: generates suggestions and drafts using configured providers.
- **Notification provider**: delivers operational and review notifications.
- **Agent PM**: plans engineering work and coordinates coding-agent tasks; it cannot publish content.

## Use-case diagram

```mermaid
usecaseDiagram
    actor Owner
    actor Editor
    actor Approver
    actor Scheduler
    actor PlatformWorker
    actor LLMGateway
    actor NotificationProvider
    actor AgentPM

    rect Workspace
        Owner: Configure workspace
        Owner: Connect social account
        Editor: Capture idea
        Editor: Create content draft
        Editor: Upload media
        Editor: Request LLM suggestions
        Editor: Submit for approval
        Approver: Review content
        Approver: Approve or reject
        Owner: Configure schedule and quiet hours
    end

    rect Generation
        LLMGateway: Generate idea candidates
        LLMGateway: Draft platform variants
        LLMGateway: Recommend schedule
    end

    rect Publishing
        Scheduler: Release approved content
        Scheduler: Create independent platform jobs
        PlatformWorker: Validate and prepare rendition
        PlatformWorker: Submit to platform
        PlatformWorker: Poll platform status
        PlatformWorker: Retry retryable failure
    end

    rect Operations
        NotificationProvider: Notify approval and failure
        AgentPM: Decompose roadmap tasks
        AgentPM: Assign coding-agent task
        AgentPM: Review task evidence
    end

    Owner --> Configure workspace
    Owner --> Connect social account
    Owner --> Configure schedule and quiet hours
    Editor --> Capture idea
    Editor --> Create content draft
    Editor --> Upload media
    Editor --> Request LLM suggestions
    Editor --> Submit for approval
    Approver --> Review content
    Approver --> Approve or reject
    Scheduler --> Release approved content
    Scheduler --> Create independent platform jobs
    PlatformWorker --> Validate and prepare rendition
    PlatformWorker --> Submit to platform
    PlatformWorker --> Poll platform status
    PlatformWorker --> Retry retryable failure
    NotificationProvider --> Notify approval and failure
    AgentPM --> Decompose roadmap tasks
    AgentPM --> Assign coding-agent task
    AgentPM --> Review task evidence
```

## UC-01: Configure a self-hosted workspace

**Goal:** Make the platform usable without editing source code.

**Preconditions:** The deployment is running and the owner has authenticated.

**Main flow:**

1. Owner selects storage, LLM, notification, and platform providers.
2. System validates provider configuration without exposing secret values.
3. System stores workspace defaults and encrypted connection references.
4. System runs a connection test.
5. Owner chooses manual, approval-required, or policy-based publishing.

**Acceptance criteria:**

- Invalid configuration fails with an actionable error.
- Secret values are never returned by the API.
- A provider can be replaced without changing application code.
- A default workspace can be created safely for an existing installation.

## UC-02: Capture an idea

**Goal:** Record a thought before losing it.

**Main flow:**

1. Editor enters a note, link, transcript, or voice-to-text result.
2. System saves the idea with its workspace, source, and optional tags.
3. Editor can ask for an LLM brief.
4. LLM gateway returns structured candidates with rationale and required assets.
5. Editor accepts one candidate into the content studio.

**Failure behavior:** If the LLM provider fails, the raw idea remains saved and the editor can continue manually.

## UC-03: Create and approve a content item

**Goal:** Make the intended post explicit before execution.

**Main flow:**

1. Editor creates a content item with audience, pillar, message, and source material.
2. Editor uploads media directly to object storage.
3. System validates metadata and creates deterministic renditions where required.
4. LLM gateway may create platform-specific caption variants.
5. Editor submits an immutable content version for approval.
6. Approver reviews media, copy, targets, privacy, and proposed time.
7. Approver approves or rejects with feedback.

**Rules:**

- Approval applies to a specific content version and target set.
- Editing an approved item creates a new version and invalidates prior approval.
- A failed LLM call never blocks manual content.

## UC-04: Schedule a post

**Goal:** Release content without requiring the owner to watch a clock.

**Main flow:**

1. Editor chooses a one-time time, recurring rule, or smart recommendation.
2. System validates timezone, quiet hours, frequency caps, and platform availability.
3. System creates or updates a scheduled post for each selected target.
4. Scheduler releases the scheduled post at the due time.
5. System creates one publish job per target in a transaction.
6. System records the release in the audit log.

**Rules:**

- One content item can have multiple platform posts.
- A platform failure does not change the state of sibling posts.
- A schedule can be paused, moved, or cancelled before release.
- DST gaps and repeated local times are explicit states, not silent surprises.

## UC-05: Publish a video

**Goal:** Execute an approved post without passing video bytes through the API.

**Main flow:**

1. Dispatcher claims the scheduled post idempotently.
2. Media worker validates the source and prepares the target rendition.
3. Platform worker selects pull or chunk upload.
4. Platform worker submits the post.
5. Worker stores the external platform ID.
6. Worker schedules a delayed status poll and exits.
7. Poll worker checks the platform until terminal state.
8. System updates the platform post and notifies the owner.

**Failure behavior:**

- Retryable platform errors use bounded exponential backoff.
- Authentication and validation errors fail immediately.
- A worker crash is recovered by a stale-job watchdog.
- A platform post may fail without changing other platform posts.

## UC-06: Handle a platform failure

**Goal:** Give the operator a clear recovery path.

**Main flow:**

1. System stores the error code, user-safe message, retryability, and platform context.
2. UI shows the failed platform and the reason category.
3. Operator may retry only that platform post.
4. System creates a new attempt without changing successful siblings.
5. System records who initiated the retry.

## UC-07: Generate a daily or weekly brief

**Goal:** Reduce the daily decision burden.

**Main flow:**

1. Scheduler creates a brief job before the planning horizon.
2. System selects open ideas, unused content pillars, upcoming themes, and recent gaps.
3. LLM gateway ranks and explains a bounded number of candidates.
4. Owner sees the candidates, required assets, and estimated effort.
5. Owner accepts, edits, snoozes, or dismisses a candidate.
6. Feedback is recorded for future ranking.

**Guardrails:**

- Never show an unbounded idea feed.
- Never fabricate analytics or claim a post will go viral.
- Keep provider failure non-blocking.
- Record the prompt and model used for each recommendation.

## UC-08: Reuse and remix content

**Goal:** Produce more content without repeatedly starting from zero.

**Main flow:**

1. Editor selects a content item, series, or media asset.
2. System creates a derivative content item with a source reference.
3. Editor chooses a remix template or asks the LLM for angles.
4. System creates new versioned variants for selected platforms.
5. Approval and scheduling follow the normal publishing path.

## UC-09: Engineering agent task management

**Goal:** Keep coding-agent work aligned with product intent.

**Main flow:**

1. Agent PM decomposes a product goal into independently verifiable tasks.
2. Each task has scope, non-goals, dependencies, acceptance criteria, and test commands.
3. A coding agent claims one task and records evidence.
4. QA reviewer checks the diff, tests, security, and documentation.
5. Agent PM closes, splits, or reopens the task.
6. No agent may publish, rotate credentials, or approve content as a side effect.

## Cross-cutting use cases

- Export a workspace with content, versions, jobs, and audit history.
- Import content from a CSV or JSON package.
- Revoke a social connection and cancel future scheduled posts.
- Add a new platform adapter without changing planning workflows.
- Add a new LLM provider through the provider registry.
- Recover stale jobs after a worker or host restart.
- Configure a notification provider for approval and failure alerts.
