/**
 * The daily slot, for display only.
 *
 * The schedule itself lives in the n8n Cron node (`n8n/daily-post.workflow.json`)
 * and in `GENERIC_TIMEZONE`. Changing the values here changes what the page
 * claims, not when posts go out — keep the two in step.
 */

export const SLOT = {
  hour: 9,
  minute: 0,
  timezone: "Asia/Bangkok",
  label: "09:00 Asia/Bangkok",
} as const;

/**
 * The backlog publishes one asset per slot, oldest first, so entry `index`
 * goes out on the `index`-th upcoming slot: today if the hour has not passed,
 * otherwise starting tomorrow.
 */
export function slotDate(index: number, now: Date = new Date()): Date {
  const slot = new Date(now);
  slot.setHours(SLOT.hour, SLOT.minute, 0, 0);
  if (slot <= now) slot.setDate(slot.getDate() + 1);
  slot.setDate(slot.getDate() + index);
  return slot;
}

export function formatSlot(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}
