import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import type { BacklogEntry, PublishResult } from "../api/types";
import { useApi } from "./useApi";

export interface BacklogState {
  entries: BacklogEntry[];
  loading: boolean;
  error: string | null;
  reload: () => void;
  /** Publish a backlog entry immediately; the caller decides what to do with the jobs. */
  release: (assetId: string) => Promise<PublishResult>;
  remove: (assetId: string) => Promise<void>;
}

/** The scheduled backlog: what n8n will release, in the order it will do it. */
export function useBacklog(): BacklogState {
  const { client } = useApi();
  const [entries, setEntries] = useState<BacklogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    client
      .listBacklog(50, controller.signal)
      .then((rows) => {
        setEntries(rows);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [client, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const release = useCallback(
    async (assetId: string) => {
      const result = await client.releaseAsset(assetId);
      reload();
      return result;
    },
    [client, reload],
  );

  const remove = useCallback(
    async (assetId: string) => {
      await client.unscheduleAsset(assetId);
      reload();
    },
    [client, reload],
  );

  return { entries, loading, error, reload, release, remove };
}
