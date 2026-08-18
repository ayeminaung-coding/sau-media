import { useCallback, useRef, useState } from "react";
import { errorMessage } from "../api/http";
import { putToStorage } from "../api/upload";
import type { UploadHandle } from "../api/upload";
import type { PublishResult, PublishTarget } from "../api/types";
import { useApi } from "./useApi";

/**
 * The four steps between "a file on a laptop" and "one job per platform".
 * Step 2 is the reason this is not a single API call: the bytes go straight
 * from the browser to R2 and never pass through the service.
 */
export const FLOW_STEPS = [
  { id: "sign", label: "Sign an upload URL", detail: "POST /assets/upload-url" },
  { id: "upload", label: "Upload direct to R2", detail: "PUT, presigned — not via the API" },
  { id: "register", label: "Register the asset", detail: "POST /assets" },
  { id: "fanout", label: "Create one job per platform", detail: "POST /publish" },
] as const;

export type FlowStatus = "idle" | "running" | "success" | "error";

export interface FlowState {
  status: FlowStatus;
  /** Index into FLOW_STEPS: the step in flight, or FLOW_STEPS.length when done. */
  step: number;
  /** 0–1 for the R2 transfer only. */
  progress: number;
  error: string | null;
}

const IDLE: FlowState = { status: "idle", step: 0, progress: 0, error: null };

export interface PublishFlow extends FlowState {
  run: (file: File, targets: PublishTarget[], schedule: boolean) => Promise<PublishResult | null>;
  cancel: () => void;
  reset: () => void;
}

export function usePublishFlow(): PublishFlow {
  const { client } = useApi();
  const [state, setState] = useState<FlowState>(IDLE);
  const uploadRef = useRef<UploadHandle | null>(null);

  const run = useCallback(
    async (file: File, targets: PublishTarget[], schedule: boolean) => {
      setState({ status: "running", step: 0, progress: 0, error: null });
      try {
        // Signed into the URL, so the same value must go back as the PUT header.
        const contentType = file.type || "video/mp4";
        const { storage_key, upload_url } = await client.createUploadUrl(file.name, contentType);

        setState((s) => ({ ...s, step: 1 }));
        const handle = putToStorage(upload_url, file, contentType, (progress) =>
          setState((s) => (s.status === "running" ? { ...s, progress } : s)),
        );
        uploadRef.current = handle;
        await handle.done;
        uploadRef.current = null;

        setState((s) => ({ ...s, step: 2, progress: 1 }));
        const asset = await client.registerAsset(storage_key);

        setState((s) => ({ ...s, step: 3 }));
        const result = await client.publish(asset.id, targets, schedule);

        setState({ status: "success", step: FLOW_STEPS.length, progress: 1, error: null });
        return result;
      } catch (cause) {
        uploadRef.current = null;
        setState((s) => ({ ...s, status: "error", error: errorMessage(cause) }));
        return null;
      }
    },
    [client],
  );

  const cancel = useCallback(() => {
    uploadRef.current?.cancel();
    uploadRef.current = null;
  }, []);

  return { ...state, run, cancel, reset: useCallback(() => setState(IDLE), []) };
}
