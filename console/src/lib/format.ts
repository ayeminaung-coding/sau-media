/** Small pure formatters. No React, no DOM. */

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 MB";
  const mb = bytes / 1_048_576;
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  if (mb >= 10) return `${mb.toFixed(0)} MB`;
  return `${mb.toFixed(1)} MB`;
}

export function formatPercent(fraction: number): string {
  return `${Math.round(Math.min(Math.max(fraction, 0), 1) * 100)}%`;
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
