import { useCallback, useMemo, useState } from "react";
import type { Platform, PublishTarget } from "../api/types";
import { PLATFORMS } from "../domain/platforms";

export interface Draft {
  title: string;
  caption: string;
  privacy: string;
}

export type PublishMode = "now" | "schedule";

const emptyDrafts = (): Record<Platform, Draft> => ({
  tiktok: { title: "", caption: "", privacy: PLATFORMS.tiktok.privacyOptions[0] ?? "" },
  facebook_reel: { title: "", caption: "", privacy: "" },
  facebook_video: { title: "", caption: "", privacy: "" },
});

export interface ComposerState {
  file: File | null;
  setFile: (file: File | null) => void;
  targets: Platform[];
  toggleTarget: (platform: Platform) => void;
  drafts: Record<Platform, Draft>;
  updateDraft: (platform: Platform, patch: Partial<Draft>) => void;
  mode: PublishMode;
  setMode: (mode: PublishMode) => void;
  activeTab: Platform | null;
  setActiveTab: (platform: Platform) => void;
  /** Empty when the form is ready; otherwise what is missing, in reading order. */
  issues: string[];
  toPublishTargets: () => PublishTarget[];
  reset: () => void;
}

/**
 * Everything the operator is composing, before anything is sent.
 *
 * Drafts are kept for every platform, not just the selected ones, so
 * unticking a target and re-ticking it does not lose what was typed.
 */
export function useComposer(): ComposerState {
  const [file, setFile] = useState<File | null>(null);
  const [targets, setTargets] = useState<Platform[]>([]);
  const [drafts, setDrafts] = useState<Record<Platform, Draft>>(emptyDrafts);
  const [mode, setMode] = useState<PublishMode>("now");
  const [activeTab, setActiveTab] = useState<Platform | null>(null);

  const toggleTarget = useCallback((platform: Platform) => {
    setTargets((current) => {
      const next = current.includes(platform)
        ? current.filter((id) => id !== platform)
        : [...current, platform];
      setActiveTab((tab) => (tab && next.includes(tab) ? tab : (next[0] ?? null)));
      return next;
    });
  }, []);

  const updateDraft = useCallback((platform: Platform, patch: Partial<Draft>) => {
    setDrafts((current) => ({ ...current, [platform]: { ...current[platform], ...patch } }));
  }, []);

  const issues = useMemo(() => {
    const found: string[] = [];
    if (!file) found.push("Choose a source video.");
    if (targets.length === 0) found.push("Pick at least one platform.");
    for (const platform of targets) {
      const spec = PLATFORMS[platform];
      const draft = drafts[platform];
      // TikTok's single text field is filled by the title *or* the caption, so
      // "has some text" is the real requirement rather than "has a caption".
      if (!draft.caption.trim() && !draft.title.trim()) {
        found.push(`${spec.name} has no ${spec.captionLabel.toLowerCase()}.`);
      }
    }
    return found;
  }, [file, targets, drafts]);

  const toPublishTargets = useCallback(
    (): PublishTarget[] =>
      targets.map((platform) => {
        const spec = PLATFORMS[platform];
        const draft = drafts[platform];
        return {
          platform,
          caption: draft.caption,
          // A platform with no title field gets an empty one, never a stray value.
          title: spec.titleMax > 0 ? draft.title : "",
          ...(spec.privacyOptions.length > 0 ? { privacy: draft.privacy } : {}),
        };
      }),
    [targets, drafts],
  );

  // Clears the composed post but keeps the publish mode: an operator filling
  // a backlog does several in a row and should not have to re-pick it.
  const reset = useCallback(() => {
    setFile(null);
    setTargets([]);
    setDrafts(emptyDrafts());
    setActiveTab(null);
  }, []);

  return {
    file,
    setFile,
    targets,
    toggleTarget,
    drafts,
    updateDraft,
    mode,
    setMode,
    activeTab,
    setActiveTab,
    issues,
    toPublishTargets,
    reset,
  };
}
