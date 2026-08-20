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
  /** Set when the asset is an episode. The backlog is ordered by these. */
  series_id: string | null;
  series_title: string;
  part_index: number | null;
}

/** One episode: an asset, its position in the series, and its jobs. */
export interface SeriesPart {
  id: string;
  series_id: string;
  asset_id: string;
  part_index: number;
  /** The one line that differs between episodes. */
  hook: string;
  source_filename: string;
  /** Known as soon as the part is registered. */
  size_bytes: number;
  storage_key: string;
  /** Filled by the first transcode — null on a part that has never published. */
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  jobs: Job[];
  created_at: string;
}

export interface Series {
  id: string;
  slug: string;
  /** The title as it appears in the caption. Renders as {series}. */
  title_local: string;
  title_en: string;
  /** Never published — it is the context the hook generator is given. */
  synopsis: string;
  /** What the hooks are drafted in. Per series, not global. */
  language: string;
  /** One real caption in your own voice, shown to the model as the house style. */
  style_example: string;
  total_parts: number | null;
  caption_template: string;
  title_template: string;
  next_teaser_template: string;
  /** Keyed by platform id. */
  hashtags: Record<string, string>;
  default_targets: Platform[];
  default_privacy: string;
  created_at: string;
  /** In episode order, never upload order. */
  parts: SeriesPart[];
  /** Gaps in the numbering: a file that was never uploaded. */
  missing_parts: number[];
  /** What `{total}` renders as. */
  effective_total: number;
}

/** Everything a series can be created or edited with. */
export type SeriesInput = Partial<
  Omit<Series, "id" | "created_at" | "parts" | "missing_parts" | "effective_total">
>;

/** One part rendered for one platform, exactly as it would publish. */
export interface CaptionPreview {
  platform: Platform;
  caption: string;
  title: string;
  caption_limit: number;
  title_limit: number;
}

export interface GenerateHooksResult {
  /** Which provider actually served — the first configured one that answered. */
  provider: string;
  hooks: Record<number, string>;
  parts_updated: number;
}

/** One posting time of day. Stored server-side, so it is editable at runtime. */
export interface Slot {
  id: string;
  label: string;
  hour: number;
  minute: number;
  timezone: string;
  enabled: boolean;
  /** Local date this slot last released on. */
  last_fired_on: string | null;
}

export type SlotInput = Omit<Slot, "id" | "last_fired_on">;

/** One upcoming release: when it fires, and what is queued for it. */
export interface PlanEntry {
  fires_at: string;
  asset_id: string | null;
  series_title: string;
  part_index: number | null;
}

export interface TickResult {
  fired: number;
  released: PublishResult[];
  idle_slots: string[];
}
