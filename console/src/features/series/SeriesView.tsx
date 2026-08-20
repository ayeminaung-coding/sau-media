import { useState } from "react";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { TextField } from "../../components/Field";
import { Tabs } from "../../components/Tabs";
import { describeSeries, pendingParts } from "../../domain/series";
import type { Platform } from "../../api/types";
import type { SeriesState } from "../../hooks/useSeries";
import { CaptionPreviewList } from "./CaptionPreviewList";
import { NamePreview, PartDropZone } from "./PartDropZone";
import { PartsTable } from "./PartsTable";
import { SeriesForm } from "./SeriesForm";
import { TargetPicker } from "../targets/TargetPicker";
import "./SeriesView.css";

interface SeriesViewProps {
  series: SeriesState;
  /** The posting rhythm, described in one line, for the publish step. */
  slotSummary: string;
}

type Tab = "episodes" | "caption" | "publish";

const TABS = [
  { id: "episodes", label: "Episodes" },
  { id: "caption", label: "Caption" },
  { id: "publish", label: "Publish" },
] as const;

/**
 * The series view: upload the parts, settle the caption, drip them out.
 *
 * It is a separate view from the composer because the unit is different. The
 * composer publishes one video with one caption per platform; here one caption
 * template covers every episode and the only per-episode text is the hook.
 */
export function SeriesView({ series, slotSummary }: SeriesViewProps) {
  const [tab, setTab] = useState<Tab>("episodes");
  const [staged, setStaged] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);

  const selected = series.selected;

  if (series.loading && series.list.length === 0) {
    return (
      <Card title="Series" description="Loading…">
        <EmptyState title="Loading…" />
      </Card>
    );
  }

  if (!selected || creating) {
    return (
      <NewSeriesCard
        series={series}
        cancellable={Boolean(selected)}
        onCancel={() => setCreating(false)}
        onCreated={() => setCreating(false)}
      />
    );
  }

  return (
    <>
      <Card
        title={selected.title_local || selected.title_en || selected.slug}
        description={describeSeries(selected)}
        aside={
          <div className="sview__pick">
            <select
              className="sview__select"
              aria-label="Series"
              value={selected.id}
              onChange={(event) => series.select(event.target.value)}
            >
              {series.list.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.title_local || row.title_en || row.slug}
                </option>
              ))}
            </select>
            <Button size="sm" onClick={() => setCreating(true)}>
              New
            </Button>
          </div>
        }
      >
        {series.error && <p className="sview__error">{series.error}</p>}
        {series.notice && (
          <p className="sview__notice" onAnimationEnd={series.clearNotice}>
            {series.notice}
          </p>
        )}

        <Tabs
          items={TABS}
          active={tab}
          label="Series section"
          onSelect={(id) => setTab(id as Tab)}
        />

        {tab === "episodes" && (
          <div className="sview__body">
            <PartDropZone
              disabled={series.busy}
              onSelect={(files) => {
                setStaged(files);
                void series.addFiles(selected.id, files).finally(() => setStaged([]));
              }}
            />
            <NamePreview files={staged} />

            <div className="sview__row">
              <p className="faint sview__hint">
                One call drafts every episode's hook together, so part 3 can end on the question
                part 4 answers. Always a draft — read them before publishing.
              </p>
              <div className="sview__buttons">
                <Button
                  loading={series.busy}
                  onClick={() => void series.generate(selected.id, { overwrite: false })}
                >
                  Draft missing hooks
                </Button>
                <Button
                  variant="ghost"
                  loading={series.busy}
                  onClick={() => void series.generate(selected.id, { overwrite: true })}
                >
                  Redraft all
                </Button>
              </div>
            </div>

            <PartsTable
              series={selected}
              uploads={series.uploads}
              busy={series.busy}
              onHookChange={(partId, hook) => void series.setHook(selected.id, partId, hook)}
              onPreview={(partId) => void series.showPreview(selected.id, partId)}
              onRemove={(partId) => void series.removePart(selected.id, partId)}
              onDraft={(partIndex) =>
                void series.generate(selected.id, { parts: [partIndex], overwrite: true })
              }
            />

            {series.previews && (
              <CaptionPreviewList previews={series.previews} onClose={series.closePreview} />
            )}
          </div>
        )}

        {tab === "caption" && (
          <div className="sview__body">
            <SeriesForm
              series={selected}
              busy={series.busy}
              onSave={(patch) => void series.update(selected.id, patch)}
            />
          </div>
        )}

        {tab === "publish" && (
          <PublishTab series={series} slotSummary={slotSummary} />
        )}
      </Card>
    </>
  );
}

interface PublishTabProps {
  series: SeriesState;
  slotSummary: string;
}

function PublishTab({ series, slotSummary }: PublishTabProps) {
  const selected = series.selected;
  const [targets, setTargets] = useState<Platform[]>(selected?.default_targets ?? []);
  const [schedule, setSchedule] = useState(true);

  if (!selected) return null;
  const queueable = pendingParts(selected);

  const toggle = (platform: Platform) =>
    setTargets((current) =>
      current.includes(platform)
        ? current.filter((id) => id !== platform)
        : [...current, platform],
    );

  return (
    <div className="sview__body">
      <TargetPicker selected={targets} onToggle={toggle} />

      <label className="sview__check">
        <input
          type="checkbox"
          checked={schedule}
          onChange={(event) => setSchedule(event.target.checked)}
        />
        <span>
          Drip through the backlog — one episode per slot ({slotSummary}), strictly in episode
          order. Unticked, every remaining episode is queued at once.
        </span>
      </label>

      <p className="faint">
        {queueable.length === 0
          ? "Every uploaded episode already has jobs."
          : `${queueable.length} episode(s) will be queued: parts ${queueable
              .map((part) => part.part_index)
              .join(", ")}.`}
      </p>

      <div className="sview__buttons">
        <Button
          variant="primary"
          loading={series.busy}
          disabled={targets.length === 0 || queueable.length === 0}
          onClick={() =>
            void series.publish(selected.id, { targets, schedule })
          }
        >
          {schedule ? "Add to backlog" : "Publish now"}
        </Button>
      </div>
    </div>
  );
}

interface NewSeriesCardProps {
  series: SeriesState;
  cancellable: boolean;
  onCancel: () => void;
  onCreated: () => void;
}

function NewSeriesCard({ series, cancellable, onCancel, onCreated }: NewSeriesCardProps) {
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");

  // The slug is the handle a human types into a URL, so it is constrained to
  // what the API accepts rather than being rejected after the fact.
  const cleaned = slug
    .toLowerCase()
    .replace(/[^a-z0-9\-_]+/g, "-")
    .replace(/^-+/, "");

  return (
    <Card
      title="New series"
      description="A series is caption material plus an ordering. Everything else is per-episode."
      aside={
        cancellable ? (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null
      }
    >
      {series.error && <p className="sview__error">{series.error}</p>}
      <div className="sview__body">
        <TextField
          label="Slug"
          value={slug}
          max={128}
          onChange={setSlug}
          hint={cleaned ? `Will be saved as ${cleaned}` : "Lowercase, no spaces. Used in the URL."}
        />
        <TextField
          label="Title"
          value={title}
          max={255}
          onChange={setTitle}
          hint="Leave it empty and the first episode's filename fills it in — part1_movieName.mp4 already carries it."
        />
        <div className="sview__buttons">
          <Button
            variant="primary"
            loading={series.busy}
            disabled={!cleaned}
            onClick={() => {
              void series
                .create({ slug: cleaned, title_local: title })
                .then((created) => created && onCreated());
            }}
          >
            Create series
          </Button>
        </div>
      </div>
    </Card>
  );
}
