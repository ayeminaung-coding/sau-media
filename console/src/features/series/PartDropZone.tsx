import { useRef, useState } from "react";
import { cx } from "../../lib/cx";
import { parsePart } from "../../domain/series";
import "../upload/DropZone.css";
import "./PartDropZone.css";

interface PartDropZoneProps {
  onSelect: (files: File[]) => void;
  disabled?: boolean;
}

/**
 * Many files at once, unlike the single-file zone the composer uses.
 *
 * The episode number is parsed and shown in the drop hint before anything is
 * sent, so a misnamed file is caught on the operator's disk rather than by a
 * 422 halfway through an eight-part upload.
 */
export function PartDropZone({ onSelect, disabled = false }: PartDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [hot, setHot] = useState(false);

  const pick = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (files.length > 0) onSelect(files);
  };

  return (
    <div
      className={cx("dropzone", hot && "dropzone--hot", disabled && "dropzone--disabled")}
      role="button"
      tabIndex={0}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if (!disabled && (event.key === "Enter" || event.key === " ")) inputRef.current?.click();
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setHot(true);
      }}
      onDragLeave={() => setHot(false)}
      onDrop={(event) => {
        event.preventDefault();
        setHot(false);
        if (!disabled) pick(event.dataTransfer.files);
      }}
    >
      <p className="dropzone__title">Drop the episodes here</p>
      <p className="dropzone__hint faint">
        <code>part1_name.mp4</code>, <code>part2_name.mp4</code>… — the number in the name is the
        episode order. Files upload straight to R2, one at a time.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        multiple
        hidden
        onChange={(event) => pick(event.target.files)}
      />
    </div>
  );
}

interface NamePreviewProps {
  files: readonly File[];
}

/** What the names parsed to, before any of it is uploaded. */
export function NamePreview({ files }: NamePreviewProps) {
  if (files.length === 0) return null;
  return (
    <ul className="namecheck">
      {files.map((file) => {
        const parsed = parsePart(file.name);
        return (
          <li key={file.name} className={cx("namecheck__row", !parsed && "namecheck__row--bad")}>
            <span className="namecheck__index mono">{parsed ? `part ${parsed.index}` : "?"}</span>
            <span className="truncate">{file.name}</span>
          </li>
        );
      })}
    </ul>
  );
}
