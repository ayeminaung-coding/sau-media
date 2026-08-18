import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { tone } from "../../domain/jobs";
import { byPart, isQueued } from "../../domain/series";
import type { Series, SeriesPart } from "../../api/types";
import type { PartUpload } from "../../hooks/useSeries";
import { cx } from "../../lib/cx";
import "../../components/Table.css";
import "./PartsTable.css";

interface PartsTableProps {
  series: Series;
  uploads: readonly PartUpload[];
  busy: boolean;
  onHookChange: (partId: string, hook: string) => void;
  onPreview: (partId: string) => void;
  onRemove: (partId: string) => void;
}

/**
 * The episode list, in episode order, with the hook editable in place.
 *
 * The hook is the only per-episode text there is — everything else in the
 * caption comes from the series template — so it gets a row each rather than
 * a separate form.
 */
export function PartsTable({
  series,
  uploads,
  busy,
  onHookChange,
  onPreview,
  onRemove,
}: PartsTableProps) {
  const parts = byPart(series.parts);
  const active = uploads.filter((upload) => upload.status !== "done");

  return (
    <>
      {uploads.length > 0 && (
        <ul className="uploads">
          {uploads.map((upload) => (
            <li key={upload.name} className={cx("uploads__row", `uploads__row--${upload.status}`)}>
              <span className="uploads__index mono">
                {upload.index ? `part ${upload.index}` : "?"}
              </span>
              <span className="truncate grow" title={upload.name}>
                {upload.name}
              </span>
              <span className="uploads__status mono faint">
                {upload.status === "uploading"
                  ? `${Math.round(upload.progress * 100)}%`
                  : upload.status}
              </span>
              {upload.error && <span className="uploads__error">{upload.error}</span>}
            </li>
          ))}
        </ul>
      )}

      {series.missing_parts.length > 0 && (
        <p className="parts__warning">
          Missing {series.missing_parts.length === 1 ? "episode" : "episodes"}{" "}
          <strong>{series.missing_parts.join(", ")}</strong> — the schedule will skip straight over
          the gap.
        </p>
      )}

      {parts.length === 0 ? (
        <EmptyState
          title={active.length > 0 ? "Uploading…" : "No episodes yet."}
          hint="Drop the part files above. The number in each filename sets its position."
        />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Part</th>
                <th>Hook — the one line that varies</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {parts.map((part) => (
                <PartRow
                  key={part.id}
                  part={part}
                  busy={busy}
                  onHookChange={onHookChange}
                  onPreview={onPreview}
                  onRemove={onRemove}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

interface PartRowProps {
  part: SeriesPart;
  busy: boolean;
  onHookChange: (partId: string, hook: string) => void;
  onPreview: (partId: string) => void;
  onRemove: (partId: string) => void;
}

function PartRow({ part, busy, onHookChange, onPreview, onRemove }: PartRowProps) {
  // Kept locally while it is being typed, and pushed on blur: saving every
  // keystroke would be one request per character.
  const [draft, setDraft] = useState(part.hook);
  useEffect(() => setDraft(part.hook), [part.hook]);

  const queued = isQueued(part);
  const state = part.jobs[0]?.state;

  return (
    <tr>
      <td>
        <span className="parts__index">part {part.part_index}</span>
        <span className="parts__file mono faint truncate" title={part.source_filename}>
          {part.source_filename || part.asset_id.slice(0, 8)}
        </span>
      </td>
      <td>
        <input
          type="text"
          className="parts__hook"
          value={draft}
          placeholder="Why watch this episode?"
          maxLength={500}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => draft !== part.hook && onHookChange(part.id, draft)}
        />
      </td>
      <td>
        {queued && state ? (
          <Badge tone={tone(state)}>{state}</Badge>
        ) : (
          <span className="faint">not queued</span>
        )}
      </td>
      <td>
        <div className="table__actions">
          <Button size="sm" variant="ghost" onClick={() => onPreview(part.id)}>
            Preview
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={busy || queued}
            title={queued ? "This episode already has jobs." : undefined}
            onClick={() => onRemove(part.id)}
          >
            Remove
          </Button>
        </div>
      </td>
    </tr>
  );
}
