/** Reading a job's lifecycle: how far along it is, and how to colour it. */

import type { Job, JobState } from "../api/types";

/** Mirrors `sau.models.TERMINAL_STATES`. */
export const TERMINAL_STATES: ReadonlySet<JobState> = new Set<JobState>(["published", "failed"]);

/** The happy path, in order. `failed` is not on it and `scheduled` precedes it. */
const PIPELINE: readonly JobState[] = [
  "pending",
  "transcoding",
  "uploading",
  "processing",
  "published",
];

export type Tone = "neutral" | "running" | "ok" | "err";

export function isTerminal(job: Job): boolean {
  return TERMINAL_STATES.has(job.state);
}

export function allSettled(jobs: readonly Job[]): boolean {
  return jobs.length > 0 && jobs.every(isTerminal);
}

export function tone(state: JobState): Tone {
  if (state === "published") return "ok";
  if (state === "failed") return "err";
  if (state === "scheduled" || state === "pending") return "neutral";
  return "running";
}

/** 0–1, for the per-job progress rail. `failed` keeps the progress it reached. */
export function completion(state: JobState): number {
  if (state === "failed") return 1;
  const index = PIPELINE.indexOf(state);
  if (index < 0) return 0;
  return (index + 1) / PIPELINE.length;
}

export const STATE_HELP: Record<JobState, string> = {
  scheduled: "In the backlog. Nothing is queued until its slot releases it.",
  pending: "Queued. Waiting for a free worker.",
  transcoding: "ffmpeg is building this platform's rendition.",
  uploading: "Transferring bytes to the platform.",
  processing: "The platform has the file and is encoding it. Polled, not pushed.",
  published: "Live.",
  failed: "Gave up. Retrying re-queues this platform alone.",
};
