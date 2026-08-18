import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { DEFAULT_SLOTS, clock, describeEntry, describeSlots, formatFiring } from "../../domain/schedule";
import type { PlanEntry, Slot, SlotInput } from "../../api/types";
import { cx } from "../../lib/cx";
import "./SlotEditor.css";

interface SlotEditorProps {
  slots: readonly Slot[];
  plan: readonly PlanEntry[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  onSave: (slots: SlotInput[]) => void;
  onTick: () => void;
}

const BLANK: SlotInput = { label: "", hour: 12, minute: 0, timezone: "Asia/Bangkok", enabled: true };

/**
 * The posting rhythm, editable.
 *
 * These times are not a display of a cron expression written somewhere else —
 * they are the schedule. n8n only supplies a heartbeat; what is saved here is
 * what decides when the backlog drains, so changing it takes effect on the
 * next tick rather than on the next deploy.
 */
export function SlotEditor({
  slots,
  plan,
  loading,
  saving,
  error,
  onSave,
  onTick,
}: SlotEditorProps) {
  const [draft, setDraft] = useState<SlotInput[]>([]);

  useEffect(() => {
    setDraft(
      slots.map(({ label, hour, minute, timezone, enabled }) => ({
        label,
        hour,
        minute,
        timezone,
        enabled,
      })),
    );
  }, [slots]);

  const set = (position: number, patch: Partial<SlotInput>) =>
    setDraft((current) =>
      current.map((slot, index) => (index === position ? { ...slot, ...patch } : slot)),
    );

  const dirty = JSON.stringify(draft) !== JSON.stringify(
    slots.map(({ label, hour, minute, timezone, enabled }) => ({
      label,
      hour,
      minute,
      timezone,
      enabled,
    })),
  );

  if (loading && slots.length === 0) return <EmptyState title="Loading…" />;

  return (
    <div className="slots">
      {error && <p className="slots__error">{error}</p>}

      <p className="slots__summary">
        <strong>{describeSlots(draft)}</strong>
      </p>

      <ul className="slots__list">
        {draft.map((slot, index) => (
          <li key={index} className={cx("slots__row", !slot.enabled && "slots__row--off")}>
            <input
              type="checkbox"
              aria-label={`Enable ${slot.label || clock(slot.hour, slot.minute)}`}
              checked={slot.enabled}
              onChange={(event) => set(index, { enabled: event.target.checked })}
            />
            <input
              type="text"
              className="slots__label"
              placeholder="Label"
              maxLength={64}
              value={slot.label}
              onChange={(event) => set(index, { label: event.target.value })}
            />
            <input
              type="time"
              className="slots__time"
              value={clock(slot.hour, slot.minute)}
              onChange={(event) => {
                const [hour, minute] = event.target.value.split(":");
                set(index, {
                  hour: Number.parseInt(hour ?? "0", 10) || 0,
                  minute: Number.parseInt(minute ?? "0", 10) || 0,
                });
              }}
            />
            <input
              type="text"
              className="slots__zone"
              aria-label="Timezone"
              maxLength={64}
              value={slot.timezone}
              onChange={(event) => set(index, { timezone: event.target.value })}
            />
            <Button
              size="sm"
              variant="danger"
              onClick={() => setDraft((current) => current.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>

      <div className="slots__actions">
        <Button size="sm" onClick={() => setDraft((current) => [...current, { ...BLANK }])}>
          Add a slot
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setDraft([...DEFAULT_SLOTS])}>
          Reset to 12:00 / 18:00 / 21:00
        </Button>
        <span className="grow" />
        <Button size="sm" variant="ghost" onClick={onTick} title="Run the release check now">
          Check now
        </Button>
        <Button
          size="sm"
          variant="primary"
          loading={saving}
          disabled={!dirty}
          onClick={() => onSave(draft)}
        >
          Save schedule
        </Button>
      </div>

      <p className="slots__note faint">
        Saving re-arms every slot, so a time moved to later today still fires today. A slot that
        comes due with an empty backlog is skipped, not carried over.
      </p>

      {plan.length > 0 && (
        <>
          <p className="slots__heading">Next releases</p>
          <ol className="slots__plan">
            {plan.map((entry) => (
              <li key={entry.fires_at} className={cx("slots__plan-row", !entry.asset_id && "faint")}>
                <span className="slots__when mono">{formatFiring(entry.fires_at)}</span>
                <span className="truncate">{describeEntry(entry)}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
