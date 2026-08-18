/**
 * The control-plane API, as functions. One per endpoint in `sau/api/main.py`.
 *
 * Note what is *not* here: no endpoint accepts video bytes. The file goes
 * straight from the browser to R2 with a presigned URL (see `upload.ts`) and
 * only its storage key ever reaches this service.
 */

import { request } from "./http";
import type { Asset, BacklogEntry, Health, Job, PublishResult, PublishTarget, UploadUrl } from "./types";

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
  };
}
