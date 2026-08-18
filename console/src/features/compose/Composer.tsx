import { Tabs } from "../../components/Tabs";
import { PLATFORMS } from "../../domain/platforms";
import type { Platform } from "../../api/types";
import type { ComposerState } from "../../hooks/useComposer";
import { PlatformFields } from "./PlatformFields";

/**
 * One tab per selected platform. Deliberately not one shared caption box:
 * the platforms disagree on field names, limits and whether a title exists
 * at all, and a single box hides those differences until a post fails.
 */
export function Composer({ composer }: { composer: ComposerState }) {
  const active = composer.activeTab;
  if (!active) return null;

  const spec = PLATFORMS[active];

  return (
    <>
      <Tabs
        label="Platform"
        active={active}
        onSelect={(id) => composer.setActiveTab(id as Platform)}
        items={composer.targets.map((platform) => ({
          id: platform,
          label: PLATFORMS[platform].name,
          accent: PLATFORMS[platform].accent,
        }))}
      />
      <PlatformFields
        key={active}
        spec={spec}
        draft={composer.drafts[active]}
        onChange={(patch) => composer.updateDraft(active, patch)}
      />
    </>
  );
}
