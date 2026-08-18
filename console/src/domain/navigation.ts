/**
 * What the console can show, in one table.
 *
 * Everything the sidebar renders — order, grouping, and whether a view is
 * built yet — comes from here. A feature that is planned but not written gets
 * `locked: true` and the copy its Coming soon page will show; nothing else in
 * the app needs to know it exists.
 */

export type ViewId =
  | "compose"
  | "series"
  | "backlog"
  | "jobs"
  | "calendar"
  | "approvals"
  | "library"
  | "templates"
  | "bulk"
  | "captions"
  | "analytics"
  | "inbox"
  | "accounts"
  | "automations"
  | "team";

export type NavGroup = "Publish" | "Content" | "Measure" | "Settings";

export interface NavItem {
  id: ViewId;
  label: string;
  group: NavGroup;
  /** Single glyph in the sidebar rail. Kept to text so the app ships no icon set. */
  icon: string;
  /** One line under the title, on the page and in the sidebar tooltip. */
  description: string;
  /** Absent means the view is built and reachable. */
  locked?: true;
  /** What the view will do, shown on its Coming soon page. Locked views only. */
  plans?: readonly string[];
}

export const NAV_GROUPS: readonly NavGroup[] = ["Publish", "Content", "Measure", "Settings"];

export const NAV: readonly NavItem[] = [
  {
    id: "compose",
    label: "Publish",
    group: "Publish",
    icon: "▲",
    description: "One video, one caption per platform, published or queued.",
  },
  {
    id: "series",
    label: "Series",
    group: "Publish",
    icon: "≡",
    description: "A serialised show, dripped out one episode per slot.",
  },
  {
    id: "backlog",
    label: "Backlog",
    group: "Publish",
    icon: "▤",
    description: "Assets waiting for their slot, in the order they will go out.",
  },
  {
    id: "jobs",
    label: "Jobs",
    group: "Publish",
    icon: "◈",
    description: "Live state of the last asset queued here.",
  },
  {
    id: "calendar",
    label: "Calendar",
    group: "Publish",
    icon: "▦",
    description: "A week at a time instead of one slot a day.",
    locked: true,
    plans: [
      "Drag a backlog entry onto a day to move its slot.",
      "Per-platform slots, rather than one set of times for everything.",
      "The same stored slots the Backlog view edits, laid out a week at a time.",
    ],
  },
  {
    id: "approvals",
    label: "Approvals",
    group: "Publish",
    icon: "✓",
    description: "A review step between compose and queue.",
    locked: true,
    plans: [
      "Hold an asset in `pending_review` until someone signs it off.",
      "Per-platform sign-off — the Reel can ship while TikTok is still being argued about.",
      "A rejection note that comes back to the composer with the caption intact.",
    ],
  },
  {
    id: "library",
    label: "Media library",
    group: "Content",
    icon: "◫",
    description: "Everything already uploaded to R2, reusable.",
    locked: true,
    plans: [
      "Re-publish a past asset to a platform it missed, without uploading it twice.",
      "The per-platform renditions ffmpeg produced, side by side with the source.",
      "Storage used, and what is safe to delete.",
    ],
  },
  {
    id: "templates",
    label: "Templates",
    group: "Content",
    icon: "❏",
    description: "Caption presets and hashtag sets.",
    locked: true,
    plans: [
      "Named presets that fill every platform's fields at once.",
      "Hashtag sets appended per platform, respecting each caption limit.",
      "Placeholders filled at publish time, as the Series view already does for episodes.",
    ],
  },
  {
    id: "bulk",
    label: "Bulk import",
    group: "Content",
    icon: "⇉",
    description: "Many assets in one pass.",
    locked: true,
    plans: [
      "A CSV of filenames and captions becomes one backlog entry per row.",
      "Point at a folder; every video in it is uploaded and queued in order.",
      "A dry run that shows the fan-out before anything is created.",
    ],
  },
  {
    id: "captions",
    label: "AI captions",
    group: "Content",
    icon: "✦",
    description: "Draft the per-platform text for a one-off upload.",
    locked: true,
    plans: [
      "The same drafting the Series view already does, for a video that is not part of a series.",
      "One draft per platform, written to that platform's limits and tone.",
      "Always a draft — nothing is published without an operator editing it.",
    ],
  },
  {
    id: "analytics",
    label: "Analytics",
    group: "Measure",
    icon: "◔",
    description: "What happened after the post landed.",
    locked: true,
    plans: [
      "Views, watch-through and follows per platform for each asset.",
      "The same video compared across TikTok and Reels.",
      "Publish-failure rate by platform and error code, from the job history.",
    ],
  },
  {
    id: "inbox",
    label: "Comments",
    group: "Measure",
    icon: "❝",
    description: "Replies across every platform in one list.",
    locked: true,
    plans: [
      "Comments from every connected account, newest first.",
      "Reply without leaving the console.",
      "Hide or report, with the action logged.",
    ],
  },
  {
    id: "accounts",
    label: "Accounts",
    group: "Settings",
    icon: "◎",
    description: "Connected accounts and the health of their tokens.",
    locked: true,
    plans: [
      "Which accounts are connected, and when each token expires.",
      "Re-auth in place when a refresh token is spent.",
      "More than one account per platform, chosen at compose time.",
    ],
  },
  {
    id: "automations",
    label: "Automations",
    group: "Settings",
    icon: "⚙",
    description: "The n8n side of the pipeline, visible from here.",
    locked: true,
    plans: [
      "The tick workflow's last run, and whether it fired.",
      "Outbound webhooks on publish success and failure.",
      "Which slots released what, over the past week.",
    ],
  },
  {
    id: "team",
    label: "Team",
    group: "Settings",
    icon: "◍",
    description: "Who can publish, and as whom.",
    locked: true,
    plans: [
      "Operator and reviewer roles.",
      "An audit trail of who queued or released what.",
      "Per-account access, so a contractor sees one brand only.",
    ],
  },
];

export const DEFAULT_VIEW: ViewId = "compose";

export function findView(id: string | null): NavItem | undefined {
  return NAV.find((item) => item.id === id);
}
