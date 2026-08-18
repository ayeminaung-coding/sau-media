import { useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Progress } from "../../components/Progress";
import { completion, STATE_HELP, tone } from "../../domain/jobs";
import { platformName } from "../../domain/platforms";
import { formatBytes } from "../../lib/format";
import type { Job } from "../../api/types";
import "../../components/Table.css";
import "./JobsPanel.css";

interface JobsPanelProps {
  jobs: readonly Job[];
  onRetry: (jobId: string) => Promise<void>;
}

export function JobsPanel({ jobs, onRetry }: JobsPanelProps) {
  const [retrying, setRetrying] = useState<string | null>(null);

  if (jobs.length === 0) {
    return (
      <EmptyState
        title="Nothing published from this browser session yet."
        hint="Jobs published elsewhere keep running — this panel only follows the last asset queued here."
      />
    );
  }

  const retry = async (jobId: string) => {
    setRetrying(jobId);
    try {
      await onRetry(jobId);
    } finally {
      setRetrying(null);
    }
  };

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Platform</th>
            <th>State</th>
            <th>Transferred</th>
            <th>Result</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td>
                <span className="job__platform">{platformName(job.platform)}</span>
                <span className="job__id mono faint">{job.id.slice(0, 8)}</span>
              </td>
              <td>
                <Badge tone={tone(job.state)} title={STATE_HELP[job.state]}>
                  {job.state}
                </Badge>
                <div className="job__rail">
                  <Progress
                    value={completion(job.state)}
                    tone={job.state === "failed" ? "err" : job.state === "published" ? "ok" : "accent"}
                    label={`${platformName(job.platform)} progress`}
                  />
                </div>
              </td>
              <td className="mono">
                {formatBytes(job.uploaded_bytes)}
                {job.attempts > 1 && <span className="faint"> · attempt {job.attempts}</span>}
              </td>
              <td>
                {job.external_url ? (
                  <a href={job.external_url} target="_blank" rel="noreferrer">
                    View post ↗
                  </a>
                ) : job.last_error ? (
                  <div className="table__error">{job.last_error}</div>
                ) : (
                  <span className="faint">—</span>
                )}
              </td>
              <td>
                <div className="table__actions">
                  {job.state === "failed" && (
                    <Button
                      size="sm"
                      loading={retrying === job.id}
                      onClick={() => void retry(job.id)}
                    >
                      Retry
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
