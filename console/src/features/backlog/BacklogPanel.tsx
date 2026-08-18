import { useState } from "react";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { platformName } from "../../domain/platforms";
import { formatFiring } from "../../domain/schedule";
import type { BacklogEntry, PlanEntry, PublishResult } from "../../api/types";
import "../../components/Table.css";
import "./BacklogPanel.css";

interface BacklogPanelProps {
  entries: readonly BacklogEntry[];
  /** Upcoming firing times, position-matched to `entries`. */
  plan: readonly PlanEntry[];
  loading: boolean;
  error: string | null;
  onRelease: (assetId: string) => Promise<PublishResult>;
  onRemove: (assetId: string) => Promise<void>;
}

/**
 * The backlog is the shipped half of the scheduled-posting story: the console
 * fills it, the tick drains it one asset per slot.
 *
 * The order shown is the order it will publish in — the API sorts it with the
 * same function the release uses, so a series cannot appear here in one order
 * and go out in another. The dates come from the API too, because they are
 * timezone arithmetic over the stored slots.
 */
export function BacklogPanel({
  entries,
  plan,
  loading,
  error,
  onRelease,
  onRemove,
}: BacklogPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);

  if (error) return <EmptyState title="Could not read the backlog." hint={error} />;
  if (loading && entries.length === 0) return <EmptyState title="Loading…" />;
  if (entries.length === 0) {
    return (
      <EmptyState
        title="The backlog is empty."
        hint="Anything added here goes out one asset per slot, in the order shown."
      />
    );
  }

  const act = async (assetId: string, action: () => Promise<unknown>) => {
    setBusy(assetId);
    try {
      await action();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Slot</th>
            <th>What</th>
            <th>Targets</th>
            <th>Caption</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, index) => {
            const caption = entry.jobs.find((job) => job.caption)?.caption ?? "";
            const firing = plan[index]?.fires_at;
            return (
              <tr key={entry.asset_id}>
                <td>
                  <span className="backlog__when">
                    {firing ? formatFiring(firing) : "No slot"}
                  </span>
                  <span className="backlog__pos mono faint">#{index + 1} in line</span>
                </td>
                <td>
                  {entry.part_index === null ? (
                    <span className="faint">One-off</span>
                  ) : (
                    <>
                      <span className="backlog__series truncate">{entry.series_title}</span>
                      <span className="backlog__pos mono faint">part {entry.part_index}</span>
                    </>
                  )}
                </td>
                <td>{entry.jobs.map((job) => platformName(job.platform)).join(", ")}</td>
                <td className="backlog__caption">{caption || <span className="faint">—</span>}</td>
                <td>
                  <div className="table__actions">
                    <Button
                      size="sm"
                      loading={busy === entry.asset_id}
                      onClick={() => void act(entry.asset_id, () => onRelease(entry.asset_id))}
                    >
                      Post now
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={busy === entry.asset_id}
                      onClick={() => void act(entry.asset_id, () => onRemove(entry.asset_id))}
                    >
                      Remove
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
