/**
 * Formatting for the release schedule.
 *
 * The schedule itself is no longer a constant here. Slots live in the database
 * (`GET /schedule/slots`) so an operator can retune the posting rhythm without
 * a redeploy, and the *times* those slots next fire are computed server-side
 * (`GET /schedule/plan`) because that arithmetic is timezone-aware and two
 * implementations of a DST rule will eventually disagree about one evening.
 *
 * What is left here is presentation: turning what the API returns into
 * something readable.
 */

import type { PlanEntry, Slot, SlotInput } from "../api/types";

/** What a new install starts with, and what the "reset" button restores. */
export const DEFAULT_SLOTS: readonly SlotInput[] = [
  { label: "Lunch", hour: 12, minute: 0, timezone: "Asia/Bangkok", enabled: true },
  { label: "Evening", hour: 18, minute: 0, timezone: "Asia/Bangkok", enabled: true },
  { label: "Night", hour: 21, minute: 0, timezone: "Asia/Bangkok", enabled: true },
];

export function clock(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function slotLabel(slot: Slot | SlotInput): string {
  return slot.label || clock(slot.hour, slot.minute);
}

/** "12:00, 18:00, 21:00 Asia/Bangkok" — the rhythm in one line. */
export function describeSlots(slots: readonly (Slot | SlotInput)[]): string {
  const active = slots.filter((slot) => slot.enabled);
  if (active.length === 0) return "No slots enabled — nothing will be released automatically.";

  const times = [...active]
    .sort((a, b) => a.hour - b.hour || a.minute - b.minute)
    .map((slot) => clock(slot.hour, slot.minute))
    .join(", ");

  const zones = new Set(active.map((slot) => slot.timezone));
  // More than one zone is legal and rare; naming them all beats picking one.
  return `${times} ${[...zones].join(" / ")}`;
}

/** "Tue 19 Aug, 18:00" — a plan entry's firing time in the reader's locale. */
export function formatFiring(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Just the day part, for grouping a plan into days. */
export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

/** What is queued for a plan entry, or a note that the slot is free. */
export function describeEntry(entry: PlanEntry): string {
  if (!entry.asset_id) return "—";
  if (entry.part_index !== null) {
    return entry.series_title
      ? `${entry.series_title} · part ${entry.part_index}`
      : `Part ${entry.part_index}`;
  }
  return "One asset";
}
