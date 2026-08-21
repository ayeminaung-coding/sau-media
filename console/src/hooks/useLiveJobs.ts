import { useCallback, useEffect, useState } from "react";
import type { Job } from "../api/types";
import { useApi } from "./useApi";

const POLL_INTERVAL_MS = 5_000;

export interface LiveJobsState {
  jobs: Job[];
  loading: boolean;
  error: string | null;
  retry: (jobId: string) => Promise<void>;
}

/**
 * Every job in the system, refreshed while the view is open.
 *
 * Distinct from `useJobRun`, which follows the one asset this browser session
 * published. Most releases are not that: the n8n tick fires on a slot with
 * nobody watching, so a panel that only knows what it queued itself shows an
 * empty table while four episodes go out.
 *
 * `active` is the view being on screen. Polling a table nobody is reading is
 * the reason this is not simply always on.
 */
export function useLiveJobs(active: boolean): LiveJobsState {
  const { client } = useApi();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!active) return;

    const controller = new AbortController();
    let timer: number | undefined;
    let cancelled = false;

    const tick = async (first: boolean) => {
      if (first) setLoading(true);
      try {
        const fresh = await client.listJobs(50, controller.signal);
        if (!cancelled) {
          setJobs(fresh);
          setError(null);
        }
      } catch {
        // Transient: keep the last good table on screen rather than blanking
        // it, and try again on the next tick.
        if (!cancelled && first) setError("Could not reach the API.");
      } finally {
        if (!cancelled && first) setLoading(false);
      }
      if (!cancelled) timer = window.setTimeout(() => void tick(false), POLL_INTERVAL_MS);
    };

    void tick(true);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [client, active, nonce]);

  const retry = useCallback(
    async (jobId: string) => {
      await client.retryJob(jobId);
      setNonce((n) => n + 1);
    },
    [client],
  );

  return { jobs, loading, error, retry };
}
