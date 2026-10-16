---
description: Review a completed agent task against scope, evidence, and repository invariants
agent: qa-reviewer
subtask: true
---

Review the following task or diff:

$ARGUMENTS

Use CLAUDE.md and docs/AGENT_PM_WORKFLOW.md as the review contract. Inspect the actual diff and run only the relevant verification commands. Return PASS, REQUEST CHANGES, or BLOCKED with specific evidence and file references. Do not edit files.
