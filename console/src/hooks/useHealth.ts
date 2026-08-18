import { useCallback, useEffect, useState } from "react";
import { useApi } from "./useApi";

const PING_INTERVAL_MS = 20_000;

export type HealthStatus = "checking" | "up" | "down";

export interface HealthState {
  status: HealthStatus;
  version: string | null;
  refresh: () => void;
}

/** Polls `/healthz` so a dead stack is visible before an upload is attempted. */
export function useHealth(): HealthState {
  const { client, base } = useApi();
  const [status, setStatus] = useState<HealthStatus>("checking");
  const [version, setVersion] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let cancelled = false;

    const ping = async () => {
      try {
        const health = await client.health(controller.signal);
        if (cancelled) return;
        setStatus("up");
        setVersion(health.version);
      } catch {
        if (cancelled) return;
        setStatus("down");
        setVersion(null);
      }
      if (!cancelled) timer = window.setTimeout(ping, PING_INTERVAL_MS);
    };

    setStatus("checking");
    void ping();

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [client, base, nonce]);

  return { status, version, refresh: useCallback(() => setNonce((n) => n + 1), []) };
}
