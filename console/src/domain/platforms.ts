/**
 * What each platform accepts, in one table.
 *
 * The limits and the quirks are the interesting part: they are why the
 * composer is per-platform tabs and not one shared caption box. Adding a
 * platform to `sau/platforms/` means adding a row here.
 */

import type { Platform } from "../api/types";

export interface PlatformSpec {
  id: Platform;
  name: string;
  /** One line under the name in the target picker. */
  summary: string;
  /** The rule an operator will otherwise learn from a failed post. */
  note: string;
  /** 0 means the platform has no title field at all. */
  titleMax: number;
  captionMax: number;
  /** What the caption box is called on that platform's own composer. */
  captionLabel: string;
  privacyOptions: readonly string[];
  accent: string;
}

export const PLATFORMS: Record<Platform, PlatformSpec> = {
  tiktok: {
    id: "tiktok",
    name: "TikTok",
    summary: "One text field — the caption; title is ignored",
    note:
      "TikTok has a single text field, and the Caption fills it. Anything typed as a Title is dropped. " +
      "Until the app passes audit every post is forced to SELF_ONLY regardless of what is chosen here.",
    titleMax: 150,
    captionMax: 2200,
    captionLabel: "Caption",
    privacyOptions: [
      "PUBLIC_TO_EVERYONE",
      "MUTUAL_FOLLOW_FRIENDS",
      "FOLLOWER_OF_CREATOR",
      "SELF_ONLY",
    ],
    accent: "var(--brand-tiktok)",
  },
  facebook_reel: {
    id: "facebook_reel",
    name: "Facebook Reel",
    summary: "Description only — title is ignored",
    note: "Reels have no title field. Only the description is sent, so anything typed as a title is dropped.",
    titleMax: 0,
    captionMax: 2200,
    captionLabel: "Description",
    privacyOptions: [],
    accent: "var(--brand-facebook)",
  },
  facebook_video: {
    id: "facebook_video",
    name: "Facebook Feed Video",
    summary: "Separate title and description",
    note: "Feed videos carry a real title alongside the description; both are sent.",
    titleMax: 255,
    captionMax: 5000,
    captionLabel: "Description",
    privacyOptions: [],
    accent: "var(--brand-facebook)",
  },
};

export const PLATFORM_LIST: readonly PlatformSpec[] = Object.values(PLATFORMS);

export function platformName(id: Platform | string): string {
  return PLATFORMS[id as Platform]?.name ?? id;
}
