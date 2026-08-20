/**
 * The control-plane API, as functions. One per endpoint in `sau/api/main.py`.
 *
 * Note what is *not* here: no endpoint accepts video bytes. The file goes
 * straight from the browser to R2 with a presigned URL (see `upload.ts`) and
 * only its storage key ever reaches this service.
 */

import { request } from "./http";
import type {
  Asset,
  BacklogEntry,
  CaptionPreview,
  GenerateHooksResult,
  Health,
  Job,
  PlanEntry,
  Platform,
  PublishResult,
  PublishTarget,
  Series,
  SeriesInput,
  SeriesPart,
  Slot,
  SlotInput,
  TickResult,
  UploadUrl,
} from "./types";

/** What `POST /series/{id}/parts` needs to place an upload in a series. */
export interface RegisterPartBody {
  storage_key: string;
  /** The original name — the episode number is read from it. */
  filename: string;
  /** Overrides the parsed number, for the file that was named wrongly. */
  part_index?: number;
  hook?: string;
}

export interface GenerateHooksBody {
  language?: string;
  max_chars?: number;
  /** Redraft hooks that already have text. */
  overwrite?: boolean;
  /** Only these episodes. The rest still go into the prompt as settled, so a
   *  single redraft still follows on from its neighbours. */
  parts?: number[];
}

export interface PublishSeriesBody {
  targets?: Platform[];
  privacy?: string;
  parts?: number[];
  /** Default true: a series is the case the drip schedule exists for. */
  schedule?: boolean;
}

export interface SauClient {
  health(signal?: AbortSignal): Promise<Health>;
  createUploadUrl(filename: string, contentType: string): Promise<UploadUrl>;
  registerAsset(storageKey: string): Promise<Asset>;
  publish(assetId: string, targets: PublishTarget[], schedule: boolean): Promise<PublishResult>;
  listAssetJobs(assetId: string, signal?: AbortSignal): Promise<Job[]>;
  retryJob(jobId: string): Promise<Job>;
  listBacklog(limit?: number, signal?: AbortSignal): Promise<BacklogEntry[]>;
  releaseAsset(assetId: string): Promise<PublishResult>;
  unscheduleAsset(assetId: string): Promise<void>;

  listSeries(signal?: AbortSignal): Promise<Series[]>;
  getSeries(ref: string, signal?: AbortSignal): Promise<Series>;
  createSeries(body: SeriesInput & { slug: string }): Promise<Series>;
  updateSeries(ref: string, body: SeriesInput): Promise<Series>;
  deleteSeries(ref: string): Promise<void>;
  registerPart(ref: string, body: RegisterPartBody): Promise<SeriesPart>;
  updatePart(ref: string, partId: string, body: { hook?: string; part_index?: number }): Promise<Series>;
  deletePart(ref: string, partId: string): Promise<void>;
  previewPart(ref: string, partId: string, signal?: AbortSignal): Promise<CaptionPreview[]>;
  generateHooks(ref: string, body: GenerateHooksBody): Promise<GenerateHooksResult>;
  publishSeries(ref: string, body: PublishSeriesBody): Promise<PublishResult>;

  listSlots(signal?: AbortSignal): Promise<Slot[]>;
  replaceSlots(slots: SlotInput[]): Promise<Slot[]>;
  releasePlan(count?: number, signal?: AbortSignal): Promise<PlanEntry[]>;
  tick(): Promise<TickResult>;
}

export function createClient(base: string): SauClient {
  return {
    health: (signal) => request<Health>(base, "/healthz", { signal }),

    createUploadUrl: (filename, contentType) =>
      request<UploadUrl>(base, "/assets/upload-url", {
        method: "POST",
        body: { filename, content_type: contentType },
      }),

    registerAsset: (storageKey) =>
      request<Asset>(base, "/assets", { method: "POST", body: { storage_key: storageKey } }),

    publish: (assetId, targets, schedule) =>
      request<PublishResult>(base, "/publish", {
        method: "POST",
        body: { asset_id: assetId, targets, schedule },
      }),

    listAssetJobs: (assetId, signal) =>
      request<Job[]>(base, `/assets/${assetId}/jobs`, { signal }),

    // Retrying one leg never touches its siblings — jobs are independent.
    retryJob: (jobId) => request<Job>(base, `/jobs/${jobId}/retry`, { method: "POST" }),

    listBacklog: (limit = 50, signal) =>
      request<BacklogEntry[]>(base, `/schedule?limit=${limit}`, { signal }),

    releaseAsset: (assetId) =>
      request<PublishResult>(base, `/assets/${assetId}/release`, { method: "POST" }),

    unscheduleAsset: (assetId) =>
      request<void>(base, `/assets/${assetId}/schedule`, { method: "DELETE" }),

    // A series is addressable by id or by slug; the slug is what a human types.
    listSeries: (signal) => request<Series[]>(base, "/series", { signal }),

    getSeries: (ref, signal) => request<Series>(base, `/series/${ref}`, { signal }),

    createSeries: (body) => request<Series>(base, "/series", { method: "POST", body }),

    updateSeries: (ref, body) =>
      request<Series>(base, `/series/${ref}`, { method: "PATCH", body }),

    deleteSeries: (ref) => request<void>(base, `/series/${ref}`, { method: "DELETE" }),

    // Only the storage key crosses the wire — the video went browser → R2.
    registerPart: (ref, body) =>
      request<SeriesPart>(base, `/series/${ref}/parts`, { method: "POST", body }),

    updatePart: (ref, partId, body) =>
      request<Series>(base, `/series/${ref}/parts/${partId}`, { method: "PATCH", body }),

    deletePart: (ref, partId) =>
      request<void>(base, `/series/${ref}/parts/${partId}`, { method: "DELETE" }),

    // Rendered server-side, by the same function the publish path uses, so the
    // preview cannot drift from what actually goes out.
    previewPart: (ref, partId, signal) =>
      request<CaptionPreview[]>(base, `/series/${ref}/parts/${partId}/preview`, { signal }),

    // One call drafts every episode's hook, so they read as one arc.
    generateHooks: (ref, body) =>
      request<GenerateHooksResult>(base, `/series/${ref}/generate-hooks`, {
        method: "POST",
        body,
      }),

    publishSeries: (ref, body) =>
      request<PublishResult>(base, `/series/${ref}/publish`, { method: "POST", body }),

    listSlots: (signal) => request<Slot[]>(base, "/schedule/slots", { signal }),

    // Sent as a set, not patched one at a time: the operator is editing one
    // daily rhythm, and half a rhythm is not a state worth saving.
    replaceSlots: (slots) =>
      request<Slot[]>(base, "/schedule/slots", { method: "PUT", body: { slots } }),

    releasePlan: (count = 12, signal) =>
      request<PlanEntry[]>(base, `/schedule/plan?count=${count}`, { signal }),

    tick: () => request<TickResult>(base, "/schedule/tick", { method: "POST" }),
  };
}
