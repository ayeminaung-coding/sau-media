import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "../api/http";
import { putToStorage } from "../api/upload";
import type { PublishSeriesBody } from "../api/client";
import type { CaptionPreview, PublishResult, Series, SeriesInput } from "../api/types";
import { parsePart } from "../domain/series";
import { useApi } from "./useApi";

/** One file's journey from the operator's disk into a series. */
export interface PartUpload {
  name: string;
  /** Parsed from the filename before anything is sent, or null if it has none. */
  index: number | null;
  status: "queued" | "uploading" | "registering" | "done" | "error";
  progress: number;
  error?: string;
}

export interface SeriesState {
  list: Series[];
  loading: boolean;
  error: string | null;
  /** A short outcome line for the last action taken. */
  notice: string | null;
  clearNotice: () => void;
  busy: boolean;

  selectedId: string | null;
  selected: Series | null;
  select: (id: string | null) => void;
  reload: () => void;

  create: (input: SeriesInput & { slug: string }) => Promise<Series | null>;
  update: (ref: string, patch: SeriesInput) => Promise<void>;
  remove: (ref: string) => Promise<void>;

  uploads: PartUpload[];
  addFiles: (ref: string, files: File[]) => Promise<void>;
  setHook: (ref: string, partId: string, hook: string) => Promise<void>;
  removePart: (ref: string, partId: string) => Promise<void>;

  generate: (ref: string, overwrite: boolean) => Promise<void>;
  publish: (ref: string, body: PublishSeriesBody) => Promise<PublishResult | null>;

  previews: CaptionPreview[] | null;
  previewPartId: string | null;
  showPreview: (ref: string, partId: string) => Promise<void>;
  closePreview: () => void;
}

/**
 * Everything the Series view does.
 *
 * Uploads run one file at a time, in episode order rather than the order they
 * were dropped. Sequential because a folder of eight 2–3 minute parts opened
 * in parallel is a good way to have the browser stall every one of them, and
 * in episode order so a partial upload still leaves a contiguous run.
 */
export function useSeries(): SeriesState {
  const { client } = useApi();
  const [list, setList] = useState<Series[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploads, setUploads] = useState<PartUpload[]>([]);
  const [previews, setPreviews] = useState<CaptionPreview[] | null>(null);
  const [previewPartId, setPreviewPartId] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    client
      .listSeries(controller.signal)
      .then((rows) => {
        setList(rows);
        setError(null);
        // Keep whatever was selected if it still exists; otherwise fall to the
        // newest, so the panel is never pointing at nothing after a delete.
        setSelectedId((current) =>
          current && rows.some((s) => s.id === current) ? current : (rows[0]?.id ?? null),
        );
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

  /** Run an action, surfacing its failure rather than letting it reject. */
  const act = useCallback(
    async <T,>(action: () => Promise<T>, success?: string): Promise<T | null> => {
      setBusy(true);
      try {
        const result = await action();
        if (success) setNotice(success);
        setError(null);
        return result;
      } catch (cause) {
        setError(errorMessage(cause));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const create = useCallback(
    async (input: SeriesInput & { slug: string }) => {
      const series = await act(() => client.createSeries(input), "Series created.");
      if (series) {
        reload();
        setSelectedId(series.id);
      }
      return series;
    },
    [act, client, reload],
  );

  const update = useCallback(
    async (ref: string, patch: SeriesInput) => {
      const updated = await act(() => client.updateSeries(ref, patch), "Saved.");
      if (updated) setList((rows) => rows.map((s) => (s.id === updated.id ? updated : s)));
    },
    [act, client],
  );

  const remove = useCallback(
    async (ref: string) => {
      await act(() => client.deleteSeries(ref), "Series deleted.");
      reload();
    },
    [act, client, reload],
  );

  const addFiles = useCallback(
    async (ref: string, files: File[]) => {
      // Episode order, not drop order: a run that fails halfway should leave
      // parts 1..n uploaded rather than a scattering with holes in it.
      const planned = files
        .map((file) => ({ file, index: parsePart(file.name)?.index ?? null }))
        .sort((a, b) => (a.index ?? Number.MAX_SAFE_INTEGER) - (b.index ?? Number.MAX_SAFE_INTEGER));

      setUploads(
        planned.map(({ file, index }) => ({
          name: file.name,
          index,
          status: "queued" as const,
          progress: 0,
        })),
      );

      const patch = (position: number, change: Partial<PartUpload>) =>
        setUploads((current) =>
          current.map((row, i) => (i === position ? { ...row, ...change } : row)),
        );

      for (const [position, { file }] of planned.entries()) {
        try {
          const contentType = file.type || "video/mp4";
          patch(position, { status: "uploading" });

          const { storage_key, upload_url } = await client.createUploadUrl(file.name, contentType);
          const handle = putToStorage(upload_url, file, contentType, (progress) =>
            patch(position, { progress }),
          );
          await handle.done;

          patch(position, { status: "registering", progress: 1 });
          // The filename goes with it: the server parses the episode number
          // itself rather than trusting what the browser worked out.
          await client.registerPart(ref, { storage_key, filename: file.name });
          patch(position, { status: "done" });
        } catch (cause) {
          // One bad file does not abandon the rest of the batch.
          patch(position, { status: "error", error: errorMessage(cause) });
        }
      }

      reload();
    },
    [client, reload],
  );

  const setHook = useCallback(
    async (ref: string, partId: string, hook: string) => {
      const updated = await act(() => client.updatePart(ref, partId, { hook }));
      if (updated) setList((rows) => rows.map((s) => (s.id === updated.id ? updated : s)));
    },
    [act, client],
  );

  const removePart = useCallback(
    async (ref: string, partId: string) => {
      await act(() => client.deletePart(ref, partId), "Part removed.");
      reload();
    },
    [act, client, reload],
  );

  const generate = useCallback(
    async (ref: string, overwrite: boolean) => {
      const result = await act(() => client.generateHooks(ref, { overwrite }));
      if (result) {
        setNotice(
          `${result.provider} drafted ${result.parts_updated} hook(s). Read them before publishing.`,
        );
        reload();
      }
    },
    [act, client, reload],
  );

  const publish = useCallback(
    async (ref: string, body: PublishSeriesBody) => {
      const result = await act(() => client.publishSeries(ref, body));
      if (result) {
        setNotice(
          body.schedule === false
            ? `Queued ${result.jobs.length} job(s) now.`
            : `${result.jobs.length} job(s) added to the backlog, in episode order.`,
        );
        reload();
      }
      return result;
    },
    [act, client, reload],
  );

  const showPreview = useCallback(
    async (ref: string, partId: string) => {
      setPreviewPartId(partId);
      const rows = await act(() => client.previewPart(ref, partId));
      setPreviews(rows);
    },
    [act, client],
  );

  const closePreview = useCallback(() => {
    setPreviews(null);
    setPreviewPartId(null);
  }, []);

  return {
    list,
    loading,
    error,
    notice,
    clearNotice: useCallback(() => setNotice(null), []),
    busy,
    selectedId,
    selected: list.find((s) => s.id === selectedId) ?? null,
    select: setSelectedId,
    reload,
    create,
    update,
    remove,
    uploads,
    addFiles,
    setHook,
    removePart,
    generate,
    publish,
    previews,
    previewPartId,
    showPreview,
    closePreview,
  };
}
