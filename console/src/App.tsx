import { Button } from "./components/Button";
import { Card } from "./components/Card";
import { EmptyState } from "./components/EmptyState";
import { PLATFORM_LIST } from "./domain/platforms";
import { SLOT } from "./domain/schedule";
import { useBacklog } from "./hooks/useBacklog";
import { useComposer } from "./hooks/useComposer";
import { useJobRun } from "./hooks/useJobRun";
import { usePublishFlow } from "./hooks/usePublishFlow";
import { BacklogPanel } from "./features/backlog/BacklogPanel";
import { Composer } from "./features/compose/Composer";
import { DropZone } from "./features/upload/DropZone";
import { JobsPanel } from "./features/jobs/JobsPanel";
import { PublishPanel } from "./features/publish/PublishPanel";
import { TargetPicker } from "./features/targets/TargetPicker";
import { TopBar } from "./features/topbar/TopBar";
import "./App.css";

/**
 * The whole console is one page in three steps — file, targets, metadata —
 * plus the two things that outlive a session: the backlog and the jobs of
 * whatever was queued last.
 *
 * App is the only component that knows about more than one feature. Features
 * receive state and callbacks; they never reach for the API themselves.
 */
export function App() {
  const composer = useComposer();
  const flow = usePublishFlow();
  const run = useJobRun();
  const backlog = useBacklog();

  const busy = flow.status === "running";

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
  };

  return (
    <div className="app">
      <TopBar />

      <main className="app__main">
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
          <PublishPanel composer={composer} flow={flow} onSubmit={() => void submit()} />
        </Card>

        <Card
          title="Backlog"
          description={`Released one asset per day at ${SLOT.label} by the n8n workflow.`}
          aside={
            <Button variant="ghost" size="sm" onClick={backlog.reload} loading={backlog.loading}>
              Refresh
            </Button>
          }
        >
          <BacklogPanel
            entries={backlog.entries}
            loading={backlog.loading}
            error={backlog.error}
            onRelease={async (assetId) => {
              const result = await backlog.release(assetId);
              run.track(result);
              return result;
            }}
            onRemove={backlog.remove}
          />
        </Card>

        <Card
          title="Jobs"
          description="Live state of the last asset queued here. Polled until every leg settles."
          aside={run.assetId ? <span className="mono faint">asset {run.assetId.slice(0, 8)}</span> : null}
        >
          <JobsPanel jobs={run.jobs} onRetry={run.retry} />
        </Card>

        <footer className="app__footer faint">
          n8n owns <em>when</em> to post; this service owns <em>how</em>. The video never passes
          through the API.
        </footer>
      </main>
    </div>
  );
}
