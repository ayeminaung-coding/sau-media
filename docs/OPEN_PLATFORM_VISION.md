# Open Platform Vision

## Status

Proposed product direction. This document describes the next product shape; it is not a statement that every feature is already implemented.

## Product promise

An open-source, self-hosted content operations platform that helps a creator or small team move from a blank page to a consistent publishing cadence without living inside each social platform.

The product should answer four questions every day:

1. What should I post?
2. Which assets and ideas are ready?
3. When should each platform receive it?
4. What happened after publishing?

The system should never publish without a clear approval rule, and it should never make an LLM the final authority for a public post.

## User pain points

- Posting is repetitive and tiring.
- Creators do not know what to post on a particular day.
- Captions, hashtags, thumbnails, and platform formatting are repeated manually.
- One video needs different versions for different platforms.
- A single platform failure creates uncertainty about the other platforms.
- Scheduling rules are confusing when time zones, quiet hours, and series ordering are involved.
- Existing tools are too closed, too expensive, or too difficult to customize.
- Public SaaS tools make it hard to keep credentials and content under the user's control.

## Product principles

### Human-controlled automation

Automation can create ideas, draft copy, suggest times, and prepare a post. The owner chooses an approval policy: manual approval, approve-by-default for low-risk content, or scheduled auto-publish inside explicit limits.

### Configuration over code changes

A normal deployment should be configurable through environment variables, a workspace configuration file, and database-backed settings. Platform adapters, LLM providers, storage providers, and notification channels should be replaceable without changing the core product.

### One source, many destinations

A content item can create one or more platform posts. Each platform post has its own state, errors, attempts, and retry controls.

### Explain every decision

Generated ideas, captions, schedules, and recommendations should store the prompt version, model, inputs, and reason for the decision when practical.

### Graceful degradation

If an LLM provider, notification service, analytics provider, or optional platform is unavailable, the core publishing path should remain usable with manual input and deterministic templates.

### Privacy and ownership

Users should be able to self-host, use their own object storage, configure their own LLM provider, export their data, and remove their workspace.

## Solution brainstorm

| Pain point | Product capability | User value |
|---|---|---|
| No idea what to post | Idea inbox, seasonal calendar, evergreen library, weekly brief | Starts with useful options instead of a blank page |
| Repetitive captions | Brand voice, content pillars, templates, LLM variations | Faster and more consistent writing |
| One video, many platforms | Content item plus platform-specific targets and versions | One upload, controlled adaptations |
| Scheduling fatigue | Smart recommendations, quiet hours, time zones, recurring plans | A reliable cadence with less planning |
| Last-minute changes | Draft, review, scheduled, publishing, published, failed states | Clear control before and after scheduling |
| Platform-specific failures | Independent jobs, retry classification, health dashboard | One platform failure does not block the rest |
| Repetitive production | Remixes, clip candidates, series templates, batch workflows | More output without starting from zero |
| Tool customization | Provider registry, plugin contracts, configuration files | The platform fits the user's stack |
| Team overload | Roles, approval queues, assignment, comments, audit log | Collaboration without losing control |

## Core product surfaces

### 1. Idea inbox

Capture a rough note, link, transcript, product note, or content gap. The system can classify the idea, estimate effort, assign a pillar, and turn it into a content brief.

### 2. Daily and weekly brief

Generate a practical shortlist rather than an infinite feed. Show a small number of recommended ideas, why they were selected, required assets, and a one-click create-draft action.

The default policy should be explainable and conservative. A recommendation is not an instruction to publish.

### 3. Content studio

A content item owns the canonical message, audience, source material, brand voice, media, and platform versions. Every edit should be versioned.

### 4. Approval inbox

Reviewers see the exact caption, media, platform, schedule, privacy level, and generated provenance. Approval or rejection is an auditable event.

### 5. Publishing calendar

Show drafts, scheduled posts, conflicts, quiet hours, and platform capacity. A calendar should make it obvious when a post is actually safe to release.

### 6. Content library

Search reusable videos, images, hooks, transcripts, product references, and successful post structures. Reuse should preserve attribution and licensing information.

### 7. Performance learning loop

Import platform metrics when available and use them to improve recommendations. This phase must be opt-in and should not change publishing behavior without explicit configuration.

## Supported operating modes

### Personal mode

One owner, one workspace, minimal setup, manual or semi-automatic publishing.

### Creator studio

Multiple content pillars, reusable series, approval workflow, several channels, and richer scheduling.

### Team mode

Members, roles, assignment, comments, approval policies, audit history, and notifications.

### Bring-your-own-provider mode

The deployment can use R2, S3, MinIO, or another supported S3-compatible store; OpenAI-compatible, Anthropic, Gemini, or local LLM providers; and optional notification providers.

## MVP boundary

The first useful open-source release should include:

- Multi-workspace data isolation
- Manual and LLM-assisted idea capture
- Content templates and deterministic caption rendering
- Content versioning and approval states
- Direct-to-object-storage media upload
- Existing TikTok and Facebook publishing adapters
- Timezone-aware schedule windows and quiet hours
- Independent platform jobs and retries
- Provider registry for LLM and storage
- Import/export of workspace data
- Audit log and health dashboard

The first release should not promise fully autonomous content creation, universal platform support, guaranteed virality, or automatic analytics optimization.

## Product success signals

- A creator can produce a publishable draft in less than five minutes.
- A week of content can be planned from one daily or weekly brief.
- A failed platform job does not obscure the status of other platform jobs.
- Every scheduled post has an explicit owner, approval state, and audit history.
- A user can replace the LLM provider or storage provider without changing application code.
- A failed LLM provider does not prevent manual publishing.

## Licensing and ecosystem

The core should remain permissively licensed and self-hostable. Platform-specific integrations should be isolated so a provider can be maintained independently. Community adapters should use a documented capability contract rather than undocumented assumptions about the core database.
