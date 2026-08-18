import { Button } from "../../components/Button";
import { OptionCard } from "../../components/OptionCard";
import { SLOT } from "../../domain/schedule";
import type { ComposerState } from "../../hooks/useComposer";
import type { PublishFlow } from "../../hooks/usePublishFlow";
import { FlowSteps } from "./FlowSteps";
import "./PublishPanel.css";

interface PublishPanelProps {
  composer: ComposerState;
  flow: PublishFlow;
  onSubmit: () => void;
}

export function PublishPanel({ composer, flow, onSubmit }: PublishPanelProps) {
  const running = flow.status === "running";
  const scheduling = composer.mode === "schedule";
  const blocked = composer.issues.length > 0;

  return (
    <div className="publish">
      <div className="publish__modes">
        <OptionCard
          type="radio"
          name="publish-mode"
          checked={!scheduling}
          onChange={() => composer.setMode("now")}
          title="Publish now"
          description="Queued the moment the upload finishes."
        />
        <OptionCard
          type="radio"
          name="publish-mode"
          checked={scheduling}
          onChange={() => composer.setMode("schedule")}
          title="Add to backlog"
          description={`Goes out in a later daily slot (${SLOT.label}), oldest first.`}
        />
      </div>

      {blocked && (
        <ul className="publish__issues">
          {composer.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}

      <div className="publish__actions">
        <Button variant="primary" onClick={onSubmit} disabled={blocked} loading={running}>
          {scheduling ? "Upload & add to backlog" : "Upload & publish"}
        </Button>
        {running && (
          <Button variant="ghost" onClick={flow.cancel}>
            Cancel upload
          </Button>
        )}
        {flow.status === "error" && (
          <Button variant="ghost" onClick={flow.reset}>
            Dismiss
          </Button>
        )}
      </div>

      {flow.status !== "idle" && <FlowSteps flow={flow} />}
    </div>
  );
}
