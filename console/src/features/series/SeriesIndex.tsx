import { useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { describeSeries } from "../../domain/series";
import type { Series } from "../../api/types";
import type { SeriesState } from "../../hooks/useSeries";
import "./SeriesIndex.css";

interface SeriesIndexProps {
  series: SeriesState;
  onOpen: (id: string) => void;
  onNew: () => void;
}

/**
 * Every series as a box, rather than a name buried in a select.
 *
 * A dropdown shows one series at a time and hides how many there are, how far
 * along each is, and which one has gaps. Those are exactly the things an
 * operator picks a series *by*, so they belong on the surface.
 */
export function SeriesIndex({ series, onOpen, onNew }: SeriesIndexProps) {
  // Held here rather than per card so arming one delete disarms any other:
  // two boxes both reading "Confirm" is a mis-click waiting to happen.
  const [confirming, setConfirming] = useState<string | null>(null);

  return (
    <Card
      title="Series"
      description="Each one is a caption template plus an ordering. Open one to manage its episodes."
      aside={
        <Button size="sm" onClick={onNew}>
          New
        </Button>
      }
    >
      {series.error && <p className="sview__error">{series.error}</p>}
      {series.notice && (
        <p className="sview__notice" onAnimationEnd={series.clearNotice}>
          {series.notice}
        </p>
      )}

      {series.list.length === 0 ? (
        <EmptyState
          title="No series yet."
          hint="A series is worth making when a show goes out one episode at a time, in order."
        />
      ) : (
        <ul className="sindex">
          {series.list.map((row) => (
            <SeriesBox
              key={row.id}
              row={row}
              busy={series.busy}
              confirming={confirming === row.id}
              onOpen={() => onOpen(row.id)}
              onArm={() => setConfirming(row.id)}
              onDisarm={() => setConfirming(null)}
              onDelete={() => {
                setConfirming(null);
                void series.remove(row.id);
              }}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

interface SeriesBoxProps {
  row: Series;
  busy: boolean;
  confirming: boolean;
  onOpen: () => void;
  onArm: () => void;
  onDisarm: () => void;
  onDelete: () => void;
}

function SeriesBox({ row, busy, confirming, onOpen, onArm, onDisarm, onDelete }: SeriesBoxProps) {
  const name = row.title_local || row.title_en || row.slug;
  const gaps = row.missing_parts.length;

  return (
    <li className="sindex__box">
      <button type="button" className="sindex__open" onClick={onOpen}>
        <span className="sindex__name truncate" title={name}>
          {name}
        </span>
        <span className="sindex__slug mono faint truncate">{row.slug}</span>
        <span className="sindex__meta faint">{describeSeries(row)}</span>
        {gaps > 0 && (
          <span className="sindex__gap">
            missing {row.missing_parts.slice(0, 6).join(", ")}
            {gaps > 6 ? "…" : ""}
          </span>
        )}
      </button>

      <div className="sindex__actions">
        {confirming ? (
          <>
            {/* Deleting drops the grouping and the part records. Anything
                already published stays up, which is why this is a confirm and
                not a blocker. */}
            <span className="sindex__warn">Delete {row.parts.length} part record(s)?</span>
            <Button size="sm" variant="danger" loading={busy} onClick={onDelete}>
              Confirm
            </Button>
            <Button size="sm" variant="ghost" onClick={onDisarm}>
              Cancel
            </Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onArm}>
            Delete
          </Button>
        )}
      </div>
    </li>
  );
}
