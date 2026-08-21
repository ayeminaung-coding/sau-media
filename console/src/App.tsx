import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { EmptyState } from "./components/EmptyState";
import { findView } from "./domain/navigation";
import { PLATFORM_LIST } from "./domain/platforms";
import { describeSlots } from "./domain/schedule";
import { useBacklog } from "./hooks/useBacklog";
import { useComposer } from "./hooks/useComposer";
import { useJobRun } from "./hooks/useJobRun";
import { useLiveJobs } from "./hooks/useLiveJobs";
import { useNav } from "./hooks/useNav";
import { usePublishFlow } from "./hooks/usePublishFlow";
import { useSchedule } from "./hooks/useSchedule";
import { useSeries } from "./hooks/useSeries";
import { BacklogPanel } from "./features/backlog/BacklogPanel";
import { Composer } from "./features/compose/Composer";
import { DropZone } from "./features/upload/DropZone";
import { JobsPanel } from "./features/jobs/JobsPanel";
import { ComingSoon } from "./features/nav/ComingSoon";
import { Sidebar } from "./features/nav/Sidebar";
import { PublishPanel } from "./features/publish/PublishPanel";
import { SlotEditor } from "./features/schedule/SlotEditor";
import { SeriesView } from "./features/series/SeriesView";
import { TargetPicker } from "./features/targets/TargetPicker";
import { TopBar } from "./features/topbar/TopBar";
import "./App.css";

/**
 * The console is a sidebar and one view at a time: publishing in three steps —
 * file, targets, metadata — the Series view for a show that goes out an episode
 * at a time, plus the two things that outlive a session, the backlog and the
 * jobs of whatever was queued last. Views that are planned but not written
 * render their Coming soon page from the same table.
 *
 * App is the only component that knows about more than one feature. Features
 * receive state and callbacks; they never reach for the API themselves.
 *
 * Every hook is mounted here rather than inside a view, so switching tabs never
 * drops a poll in flight — a publish keeps advancing while its operator reads
 * the backlog.
 */
export function App() {
  const nav = useNav();
  const composer = useComposer();
  const flow = usePublishFlow();
  const run = useJobRun();
  const live = useLiveJobs(nav.view === "jobs");
  const backlog = useBacklog();
  const schedule = useSchedule();
  const series = useSeries();

  const busy = flow.status === "running";
  const item = findView(nav.view);
  // The posting rhythm, from the stored slots rather than a constant — the
  // composer and the series view both quote it, and neither should guess.
  const slotSummary = describeSlots(schedule.slots);

  const submit = async () => {
    if (!composer.file || composer.issues.length > 0) return;
    const scheduling = composer.mode === "schedule";
    const result = await flow.run(composer.file, composer.toPublishTargets(), scheduling);
    if (!result) return;

    // A scheduled asset has jobs, but none of them are queued — showing them
    // in the jobs panel would imply work is happening. It goes to the backlog.
    if (scheduling) backlog.reload();
    else run.track(result);
    composer.reset();

    // The result now lives on another tab; take the operator there.
    nav.select(scheduling ? "backlog" : "jobs");
  };

  return (
    <div className="app">
      <TopBar />

      <div className="app__body">
        <Sidebar view={nav.view} onSelect={nav.select} />

        <main className="app__main">
          {item?.locked && <ComingSoon item={item} />}

          {nav.view === "compose" && (
            <>
              <Card step="1" title="Source video" description="One upload, reused by every platform.">
                <DropZone file={composer.file} onSelect={composer.setFile} disabled={busy} />
              </Card>

              <Card
                step="2"
                title="Targets"
                description="Each one becomes an independent job: a TikTok failure never touches the Reel."
                aside={`${composer.targets.length}/${PLATFORM_LIST.length} selected`}
              >
                <TargetPicker
                  selected={composer.targets}
                  onToggle={composer.toggleTarget}
                  disabled={busy}
                />
              </Card>

              <Card
                step="3"
                title="Metadata"
                description="Written per platform, because the platforms do not agree on the fields."
              >
                {composer.targets.length > 0 ? (
                  <Composer composer={composer} />
                ) : (
                  <EmptyState title="Pick a target above to write its caption." />
                )}
                <PublishPanel
                  composer={composer}
                  flow={flow}
                  slotSummary={slotSummary}
                  onSubmit={() => void submit()}
                />
              </Card>
            </>
          )}

          {nav.view === "series" && (
            <SeriesView series={series} slotSummary={slotSummary} />
          )}

          {nav.view === "backlog" && (
            <>
              <Card
                title="Backlog"
                description={`Released one asset per slot (${slotSummary}), in the order shown.`}
                aside={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      backlog.reload();
                      schedule.reload();
                    }}
                    loading={backlog.loading}
                  >
                    Refresh
                  </Button>
                }
              >
                <BacklogPanel
                  entries={backlog.entries}
                  plan={schedule.plan}
                  loading={backlog.loading}
                  error={backlog.error}
                  onRelease={async (assetId) => {
                    const result = await backlog.release(assetId);
                    run.track(result);
                    schedule.reload();
                    return result;
                  }}
                  onRemove={async (assetId) => {
                    await backlog.remove(assetId);
                    schedule.reload();
                  }}
                />
              </Card>

              <Card
                title="Schedule"
                description="When the backlog drains. Stored server-side, so a change takes effect on the next tick — not the next deploy."
              >
                <SlotEditor
                  slots={schedule.slots}
                  plan={schedule.plan}
                  loading={schedule.loading}
                  saving={schedule.saving}
                  error={schedule.error}
                  onSave={(slots) => void schedule.save(slots)}
                  onTick={() => void schedule.runTick()}
                />
              </Card>
            </>
          )}

          {nav.view === "jobs" && (
            <Card
              title="Jobs"
              description="Every job in the system, newest first — including releases this browser never queued. Refreshed every 5s."
              aside={
                live.loading && live.jobs.length === 0 ? (
                  <span className="mono faint">loading…</span>
                ) : (
                  <span className="mono faint">{live.jobs.length} job(s)</span>
                )
              }
            >
              {live.error && <p className="sview__error">{live.error}</p>}
              <JobsPanel jobs={live.jobs} onRetry={live.retry} />
            </Card>
          )}

          <footer className="app__footer faint">
            n8n supplies the heartbeat; the schedule and the ordering live here, and this service
            owns <em>how</em> to post. The video never passes through the API.
          </footer>
        </main>
      </div>
    </div>
  );
}
