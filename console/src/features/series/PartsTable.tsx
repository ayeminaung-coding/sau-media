import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { STATE_HELP, tone } from "../../domain/jobs";
import { byPart, failedJobs, isLive, isQueued } from "../../domain/series";
import { formatBytes, formatTime } from "../../lib/format";
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
  /** Redraft one episode's hook, by episode number. */
  onDraft: (partIndex: number) => void;
  /** Re-queue this episode's failed jobs. */
  onRetry: (part: SeriesPart) => void;
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
  onDraft,
  onRetry,
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
                  onDraft={onDraft}
                  onRetry={onRetry}
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
  onDraft: (partIndex: number) => void;
  onRetry: (part: SeriesPart) => void;
}

function PartRow({
  part,
  busy,
  onHookChange,
  onPreview,
  onRemove,
  onDraft,
  onRetry,
}: PartRowProps) {
  // Kept locally while it is being typed, and pushed on blur: saving every
  // keystroke would be one request per character.
  const [draft, setDraft] = useState(part.hook);
  const [open, setOpen] = useState(false);
  useEffect(() => setDraft(part.hook), [part.hook]);

  const queued = isQueued(part);
  const live = isLive(part);
  const failed = failedJobs(part);
  const state = part.jobs[0]?.state;

  return (
    <>
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
          <Button
            size="sm"
            loading={busy}
            title="Redraft this episode's hook. The rest of the series still goes into the prompt, so it follows on from its neighbours."
            onClick={() => onDraft(part.part_index)}
          >
            Draft
          </Button>
          {failed.length > 0 && (
            <Button
              size="sm"
              loading={busy}
              title={`Re-queue ${failed.length} failed job(s). This publishes now rather than waiting for a slot.`}
              onClick={() => onRetry(part)}
            >
              Retry
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => onPreview(part.id)}>
            Preview
          </Button>
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open}
            onClick={() => setOpen((current) => !current)}
          >
            {open ? "Hide" : "Details"}
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={busy || live}
            title={
              live
                ? "This episode has jobs that have not failed."
                : failed.length > 0
                  ? "Every job failed — removing this lets the file be re-uploaded."
                  : undefined
            }
            onClick={() => onRemove(part.id)}
          >
            Remove
          </Button>
        </div>
      </td>
    </tr>
    {open && <PartDetails part={part} />}
    </>
  );
}

/** The asset behind one episode, and what each platform has done with it. */
function PartDetails({ part }: { part: SeriesPart }) {
  // Duration and resolution are written by the first transcode, which is the
  // first time anything actually opens the file. Saying so beats showing a
  // blank that reads like a failure.
  const probed = part.duration_seconds !== null;

  return (
    <tr className="parts__details-row">
      <td colSpan={4}>
        <dl className="parts__details">
          <div>
            <dt>File</dt>
            <dd className="mono truncate">{part.source_filename || "—"}</dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{formatBytes(part.size_bytes)}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>
              {probed ? `${Math.round(part.duration_seconds ?? 0)}s` : <span className="faint">not probed yet</span>}
            </dd>
          </div>
          <div>
            <dt>Resolution</dt>
            <dd>
              {part.width && part.height ? (
                `${part.width}×${part.height}`
              ) : (
                <span className="faint">not probed yet</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Uploaded</dt>
            <dd>{formatTime(part.created_at)}</dd>
          </div>
          <div>
            <dt>Storage key</dt>
            <dd className="mono truncate">{part.storage_key || "—"}</dd>
          </div>
          <div>
            <dt>Hook length</dt>
            <dd>{part.hook.length} chars</dd>
          </div>
          <div className="parts__details-wide">
            <dt>Jobs</dt>
            <dd>
              {part.jobs.length === 0 ? (
                <span className="faint">Not queued on any platform yet.</span>
              ) : (
                <ul className="parts__jobs">
                  {part.jobs.map((job) => (
                    <li key={job.id}>
                      <Badge tone={tone(job.state)}>{job.platform}</Badge>
                      <span className="faint">{STATE_HELP[job.state]}</span>
                      {job.last_error && <span className="parts__joberr">{job.last_error}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        </dl>
        {!probed && (
          <p className="parts__details-note faint">
            Duration and resolution are read by ffmpeg during the first transcode, which happens
            when this episode is first published. Until then only the byte size is known.
          </p>
        )}
      </td>
    </tr>
  );
}
