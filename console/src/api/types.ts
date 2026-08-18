/**
 * Wire types. These mirror `sau/api/schemas.py` one for one — if a field is
 * added there, add it here rather than reaching for `any` at the call site.
 */

export const PLATFORM_IDS = ["tiktok", "facebook_reel", "facebook_video"] as const;
export type Platform = (typeof PLATFORM_IDS)[number];

/** `sau.models.JobState`, in lifecycle order. */
export const JOB_STATES = [
  "scheduled",
  "pending",
  "transcoding",
  "uploading",
  "processing",
  "published",
  "failed",
] as const;
export type JobState = (typeof JOB_STATES)[number];

export interface Health {
  status: string;
  version: string;
}

export interface UploadUrl {
  storage_key: string;
  upload_url: string;
  expires_seconds: number;
}

export interface Asset {
  id: string;
  storage_key: string;
  size_bytes: number;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  created_at: string;
}

export interface PublishTarget {
  platform: Platform;
  caption: string;
  title: string;
  privacy?: string;
}

export interface Job {
  id: string;
  asset_id: string;
  platform: Platform;
  state: JobState;
  caption: string;
  title: string;
  external_id: string | null;
  external_url: string | null;
  uploaded_bytes: number;
  attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishResult {
  asset_id: string;
  jobs: Job[];
}

/** One scheduled asset and every platform waiting to go out with it. */
export interface BacklogEntry {
  asset_id: string;
  created_at: string;
  jobs: Job[];
}
