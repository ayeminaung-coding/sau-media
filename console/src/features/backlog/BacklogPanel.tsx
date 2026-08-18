import { useState } from "react";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { platformName } from "../../domain/platforms";
import { formatSlot, slotDate } from "../../domain/schedule";
import type { BacklogEntry, PublishResult } from "../../api/types";
import "../../components/Table.css";
import "./BacklogPanel.css";

interface BacklogPanelProps {
  entries: readonly BacklogEntry[];
  loading: boolean;
  error: string | null;
  onRelease: (assetId: string) => Promise<PublishResult>;
  onRemove: (assetId: string) => Promise<void>;
}

/**
 * The backlog is the shipped half of the daily-posting story: the console
 * fills it, the n8n cron drains it one asset per day. The dates shown are
 * derived from that slot, not stored anywhere.
 */
export function BacklogPanel({ entries, loading, error, onRelease, onRemove }: BacklogPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);

  if (error) return <EmptyState title="Could not read the backlog." hint={error} />;
  if (loading && entries.length === 0) return <EmptyState title="Loading…" />;
  if (entries.length === 0) {
    return (
      <EmptyState
        title="The backlog is empty."
        hint="Anything added here goes out one asset per slot, oldest first."
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
            <th>Targets</th>
            <th>Caption</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, index) => {
            const caption = entry.jobs.find((job) => job.caption)?.caption ?? "";
            return (
              <tr key={entry.asset_id}>
                <td>
                  <span className="backlog__when">{formatSlot(slotDate(index))}</span>
                  <span className="backlog__pos mono faint">#{index + 1} in line</span>
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
