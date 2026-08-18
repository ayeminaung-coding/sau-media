import { SelectField, TextField } from "../../components/Field";
import type { PlatformSpec } from "../../domain/platforms";
import type { Draft } from "../../hooks/useComposer";
import "./PlatformFields.css";

interface PlatformFieldsProps {
  spec: PlatformSpec;
  draft: Draft;
  onChange: (patch: Partial<Draft>) => void;
}

/** The composer for one platform. Which fields exist is the platform's rule. */
export function PlatformFields({ spec, draft, onChange }: PlatformFieldsProps) {
  return (
    <div className="fields" role="tabpanel">
      {spec.titleMax > 0 && (
        <TextField
          label="Title"
          value={draft.title}
          max={spec.titleMax}
          placeholder={spec.id === "tiktok" ? "Optional — the caption is used if empty" : ""}
          onChange={(title) => onChange({ title })}
        />
      )}

      <TextField
        label={spec.captionLabel}
        value={draft.caption}
        max={spec.captionMax}
        multiline
        rows={5}
        onChange={(caption) => onChange({ caption })}
      />

      {spec.privacyOptions.length > 0 && (
        <SelectField
          label="Privacy"
          value={draft.privacy}
          options={spec.privacyOptions}
          onChange={(privacy) => onChange({ privacy })}
        />
      )}

      <p className="fields__note">{spec.note}</p>
    </div>
  );
}
