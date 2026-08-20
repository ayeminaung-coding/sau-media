import { useEffect, useState } from "react";
import { Button } from "../../components/Button";
import { TextField } from "../../components/Field";
import { PLATFORM_LIST } from "../../domain/platforms";
import { TEMPLATE_FIELDS } from "../../domain/series";
import type { Series, SeriesInput } from "../../api/types";
import "./SeriesForm.css";

interface SeriesFormProps {
  series: Series;
  busy: boolean;
  onSave: (patch: SeriesInput) => void;
}

/**
 * The caption material, which is where nearly all of a series' text lives.
 *
 * The point of the split is that these fields are written once and the hook is
 * written per episode. Nothing here is Chinese copy baked into the app — the
 * templates are stored, so the wording is the operator's.
 */
export function SeriesForm({ series, busy, onSave }: SeriesFormProps) {
  const [draft, setDraft] = useState<SeriesInput>(series);

  // Re-seed when the operator switches series, or after a save round-trips.
  useEffect(() => setDraft(series), [series]);

  const set = (patch: SeriesInput) => setDraft((current) => ({ ...current, ...patch }));
  const setHashtag = (platform: string, value: string) =>
    setDraft((current) => ({
      ...current,
      hashtags: { ...(current.hashtags ?? {}), [platform]: value },
    }));

  return (
    <div className="sform">
      <div className="sform__grid">
        <TextField
          label="Title"
          value={draft.title_local ?? ""}
          max={255}
          onChange={(value) => set({ title_local: value })}
          hint="As it reads in the caption. Renders as {series}."
        />
        <TextField
          label="English title"
          value={draft.title_en ?? ""}
          max={255}
          onChange={(value) => set({ title_en: value })}
          hint="Renders as {series_en}."
        />
      </div>

      <TextField
        label="Synopsis"
        value={draft.synopsis ?? ""}
        max={8000}
        multiline
        rows={4}
        onChange={(value) => set({ synopsis: value })}
        hint="Never published. This is the context the hook generator is given — the better it is, the better the drafted hooks."
      />

      <TextField
        label="Caption language"
        value={draft.language ?? ""}
        max={64}
        onChange={(value) => set({ language: value })}
        hint="What the hooks are drafted in — the audience's language, which is usually not the animation's."
      />

      <TextField
        label="House style — one real caption"
        value={draft.style_example ?? ""}
        max={4000}
        multiline
        rows={5}
        onChange={(value) => set({ style_example: value })}
        hint="Paste one caption you have already written, hook paragraph and all. The model is shown it as the voice to match — this does more for the output than any other field here."
      />

      <TextField
        label="Total episodes"
        value={draft.total_parts === null || draft.total_parts === undefined ? "" : String(draft.total_parts)}
        onChange={(value) => {
          const parsed = Number.parseInt(value, 10);
          set({ total_parts: Number.isFinite(parsed) && parsed > 0 ? parsed : null });
        }}
        hint="What {total} renders as. Leave empty for an open-ended series and the count of uploaded parts stands in."
      />

      <TextField
        label="Caption template"
        value={draft.caption_template ?? ""}
        max={5000}
        multiline
        rows={6}
        onChange={(value) => set({ caption_template: value })}
        hint="An empty placeholder closes its own line, so the same template works with or without a hook."
      />

      <div className="sform__grid">
        <TextField
          label="Title template"
          value={draft.title_template ?? ""}
          max={512}
          onChange={(value) => set({ title_template: value })}
          hint="Ignored by Reels, which have no title field."
        />
        <TextField
          label="Next-episode teaser"
          value={draft.next_teaser_template ?? ""}
          max={512}
          onChange={(value) => set({ next_teaser_template: value })}
          hint="Renders into {next_teaser}, and is left empty on the final episode."
        />
      </div>

      <fieldset className="sform__fieldset">
        <legend className="sform__legend">Hashtags, per platform</legend>
        <p className="sform__note faint">
          Separate because the tags that work on TikTok are not the ones that work on a Facebook
          feed video — and the caption limits differ too.
        </p>
        {PLATFORM_LIST.map((platform) => (
          <TextField
            key={platform.id}
            label={platform.name}
            value={draft.hashtags?.[platform.id] ?? ""}
            max={platform.captionMax}
            onChange={(value) => setHashtag(platform.id, value)}
          />
        ))}
      </fieldset>

      <details className="sform__help">
        <summary>Placeholders</summary>
        <dl className="sform__fields">
          {TEMPLATE_FIELDS.map((field) => (
            <div key={field.name} className="sform__field">
              <dt className="mono">{field.name}</dt>
              <dd className="faint">{field.description}</dd>
            </div>
          ))}
        </dl>
      </details>

      <div className="sform__actions">
        <Button variant="primary" loading={busy} onClick={() => onSave(draft)}>
          Save series
        </Button>
      </div>
    </div>
  );
}
