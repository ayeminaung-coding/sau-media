import { useCallback, useEffect, useState } from "react";
import { allSettled } from "../domain/jobs";
import type { Job, PublishResult } from "../api/types";
import { useApi } from "./useApi";

const POLL_INTERVAL_MS = 5_000;

export interface JobRunState {
  assetId: string | null;
  jobs: Job[];
  /** True once every job is `published` or `failed`. */
  settled: boolean;
  /** Adopt the jobs returned by /publish or /release and start polling them. */
  track: (result: PublishResult) => void;
  retry: (jobId: string) => Promise<void>;
  clear: () => void;
}

/**
 * Follows the jobs of the asset currently being watched.
 *
 * Polling, not streaming: the workers hand off to the platform and exit, so
 * there is nothing holding a connection open to push from. It stops as soon
 * as every job is terminal, which is what keeps an idle console quiet.
 */
export function useJobRun(): JobRunState {
  const { client } = useApi();
  const [assetId, setAssetId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);

  const settled = allSettled(jobs);

  useEffect(() => {
    if (!assetId || settled) return;

    const controller = new AbortController();
    let timer: number | undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const fresh = await client.listAssetJobs(assetId, controller.signal);
        if (!cancelled) setJobs(fresh);
      } catch {
        /* transient — try again on the next tick rather than tearing the view down */
      }
      if (!cancelled) timer = window.setTimeout(tick, POLL_INTERVAL_MS);
    };

    timer = window.setTimeout(tick, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [client, assetId, settled]);

  const track = useCallback((result: PublishResult) => {
    setAssetId(result.asset_id);
    setJobs(result.jobs);
  }, []);

  const retry = useCallback(
    async (jobId: string) => {
      // Re-queues this platform alone; its siblings are never re-uploaded.
      const updated = await client.retryJob(jobId);
      setJobs((current) => current.map((job) => (job.id === updated.id ? updated : job)));
    },
    [client],
  );

  const clear = useCallback(() => {
    setAssetId(null);
    setJobs([]);
  }, []);

  return { assetId, jobs, settled, track, retry, clear };
}
