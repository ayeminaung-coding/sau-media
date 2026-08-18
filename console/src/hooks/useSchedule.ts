import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import type { PlanEntry, Slot, SlotInput } from "../api/types";
import { useApi } from "./useApi";

export interface ScheduleState {
  slots: Slot[];
  /** The next firing times, paired with what is queued for them. */
  plan: PlanEntry[];
  loading: boolean;
  error: string | null;
  saving: boolean;
  reload: () => void;
  /** Replace the whole day's rhythm. Returns false if the save failed. */
  save: (slots: SlotInput[]) => Promise<boolean>;
  /** Run the release check now, without waiting for n8n's next tick. */
  runTick: () => Promise<string>;
}

/**
 * The posting rhythm and what it is about to release.
 *
 * Both come from the API. The slots are stored server-side so they can be
 * edited without a redeploy, and the firing times are computed there too —
 * they are timezone-aware, and a second implementation of a DST rule in the
 * browser would eventually disagree with the one that actually releases.
 */
export function useSchedule(planCount = 12): ScheduleState {
  const { client } = useApi();
  const [slots, setSlots] = useState<Slot[]>([]);
  const [plan, setPlan] = useState<PlanEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    Promise.all([
      client.listSlots(controller.signal),
      client.releasePlan(planCount, controller.signal),
    ])
      .then(([nextSlots, nextPlan]) => {
        setSlots(nextSlots);
        setPlan(nextPlan);
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
  }, [client, nonce, planCount]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const save = useCallback(
    async (next: SlotInput[]) => {
      setSaving(true);
      try {
        setSlots(await client.replaceSlots(next));
        setError(null);
        // The plan is derived from the slots, so it is stale the moment they
        // change; refetch rather than trying to recompute it here.
        reload();
        return true;
      } catch (cause) {
        setError(errorMessage(cause));
        return false;
      } finally {
        setSaving(false);
      }
    },
    [client, reload],
  );

  const runTick = useCallback(async () => {
    try {
      const result = await client.tick();
      reload();
      if (result.fired > 0) return `Released ${result.fired} asset(s).`;
      if (result.idle_slots.length > 0) {
        return `${result.idle_slots.join(", ")} came due with an empty backlog.`;
      }
      return "No slot is due right now.";
    } catch (cause) {
      return errorMessage(cause);
    }
  }, [client, reload]);

  return { slots, plan, loading, error, saving, reload, save, runTick };
}
