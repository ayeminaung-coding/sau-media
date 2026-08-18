import { Progress } from "../../components/Progress";
import { FLOW_STEPS } from "../../hooks/usePublishFlow";
import type { PublishFlow } from "../../hooks/usePublishFlow";
import { formatPercent } from "../../lib/format";
import { cx } from "../../lib/cx";
import "./FlowSteps.css";

/** Live trace of the four-step publish sequence, including where it stopped. */
export function FlowSteps({ flow }: { flow: PublishFlow }) {
  return (
    <ol className="flow">
      {FLOW_STEPS.map((step, index) => {
        const done = index < flow.step || flow.status === "success";
        const active = index === flow.step && flow.status === "running";
        const failed = index === flow.step && flow.status === "error";

        return (
          <li
            key={step.id}
            className={cx(
              "flow__step",
              done && "flow__step--done",
              active && "flow__step--active",
              failed && "flow__step--failed",
            )}
          >
            <span className="flow__marker" aria-hidden="true">
              {done ? "✓" : failed ? "✕" : index + 1}
            </span>
            <div className="grow">
              <p className="flow__label">{step.label}</p>
              <p className="flow__detail mono faint">{step.detail}</p>
              {step.id === "upload" && (active || (done && flow.progress > 0)) && (
                <div className="flow__progress">
                  <Progress value={flow.progress} label="Upload progress" />
                  <span className="flow__pct mono">{formatPercent(flow.progress)}</span>
                </div>
              )}
            </div>
          </li>
        );
      })}
      {flow.error && <li className="flow__error mono">{flow.error}</li>}
    </ol>
  );
}
