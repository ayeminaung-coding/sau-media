/**
 * Series rules: reading an episode number out of a filename, and the
 * placeholders a caption template may use.
 *
 * The parser here mirrors `sau/series.py`. It exists so the operator sees the
 * episode number the moment a file is dropped, before anything is uploaded —
 * the server is still the authority, and it re-parses the name it is sent.
 * Two implementations of one rule is a cost worth paying only because the
 * alternative is a round trip per file just to render a list.
 *
 * Caption *rendering* is deliberately not mirrored: the preview comes from the
 * API, rendered by the same function the publish path uses, so what is shown
 * cannot drift from what publishes.
 */

import type { Job, Series, SeriesPart } from "../api/types";

/** `part1_name`, `Part 02 - name`, `ep3_name`, `episode_4_name`. */
const PART_RE = /^\s*(?:part|ep|episode)[\s_\-.]*(\d{1,4})(?:[\s_\-.]+(.*))?$/i;

export interface ParsedPart {
  index: number;
  /** Whatever followed the number. Shown to confirm the right file matched. */
  label: string;
}

function stem(filename: string): string {
  const base = filename.split("/").pop() ?? filename;
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

/**
 * Pull the episode number out of a filename, or null if it does not carry one.
 *
 * The separator after the digits is required, which is what stops `part12_x`
 * being read as part 1 — a series that silently renumbers itself is the worst
 * failure this feature has.
 */
export function parsePart(filename: string): ParsedPart | null {
  const match = PART_RE.exec(stem(filename));
  if (!match) return null;

  const index = Number.parseInt(match[1] ?? "", 10);
  // part0 would sort ahead of the real first episode.
  if (!Number.isFinite(index) || index < 1) return null;

  return { index, label: (match[2] ?? "").replace(/[_\-.]+/g, " ").trim() };
}

/** Episode numbers absent from an otherwise contiguous run, lowest first. */
export function missingParts(indices: readonly number[]): number[] {
  const present = new Set(indices.filter((n) => n >= 1));
  if (present.size === 0) return [];
  const highest = Math.max(...present);
  const gaps: number[] = [];
  for (let n = 1; n < highest; n += 1) if (!present.has(n)) gaps.push(n);
  return gaps;
}

/** Episode order — never the order the uploads happened to finish in. */
export function byPart<T extends { part_index: number }>(parts: readonly T[]): T[] {
  return [...parts].sort((a, b) => a.part_index - b.part_index);
}

/** A part is publishable until it has jobs; after that it is spoken for. */
export function isQueued(part: SeriesPart): boolean {
  return part.jobs.length > 0;
}

/** The jobs that gave up on this episode, one per platform that failed. */
export function failedJobs(part: SeriesPart): Job[] {
  return part.jobs.filter((job) => job.state === "failed");
}

/**
 * Whether anything is still riding on this episode.
 *
 * A part whose every job has failed holds nothing: the file was rejected and
 * no platform is going to act on it again unless it is retried. That is the
 * one case where replacing the episode is the right move, so it is not the
 * same question as `isQueued`, which governs whether publishing it again
 * would duplicate work.
 */
export function isLive(part: SeriesPart): boolean {
  return part.jobs.some((job) => job.state !== "failed");
}

export function pendingParts(series: Series): SeriesPart[] {
  return byPart(series.parts).filter((part) => !isQueued(part));
}

/**
 * The placeholders a template may use, with what each resolves to.
 *
 * Shown next to the template fields, because a placeholder an operator cannot
 * remember is one they will not use.
 */
export const TEMPLATE_FIELDS: readonly { name: string; description: string }[] = [
  { name: "{series}", description: "The series title, as it reads in the caption" },
  { name: "{series_en}", description: "English series title" },
  { name: "{part}", description: "This episode's number" },
  { name: "{total}", description: "Declared episode count, or how many are registered" },
  { name: "{next_part}", description: "The next episode's number; empty on the last one" },
  { name: "{next_teaser}", description: "The teaser line, rendered; empty on the last episode" },
  { name: "{hook}", description: "This episode's hook — the one line that varies" },
  { name: "{hashtags}", description: "The hashtag block for the platform being rendered" },
  { name: "{synopsis}", description: "The series synopsis" },
];

/** A one-line description of where a series stands, for the list. */
export function describeSeries(series: Series): string {
  const total = series.effective_total;
  const queued = series.parts.filter(isQueued).length;
  const gaps = series.missing_parts.length;

  const parts = [`${series.parts.length} of ${total || "?"} parts`];
  if (queued > 0) parts.push(`${queued} queued`);
  if (gaps > 0) parts.push(`${gaps} missing`);
  return parts.join(" · ");
}
