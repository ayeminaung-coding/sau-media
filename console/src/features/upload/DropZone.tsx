import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { formatBytes } from "../../lib/format";
import { cx } from "../../lib/cx";
import "./DropZone.css";

interface DropZoneProps {
  file: File | null;
  onSelect: (file: File | null) => void;
  disabled?: boolean;
}

export function DropZone({ file, onSelect, disabled = false }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [hot, setHot] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // An object URL is a document-lifetime handle on the file; revoke it when
  // the selection changes or the component goes away.
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pick = (list: FileList | null) => {
    const chosen = list?.[0];
    if (chosen) onSelect(chosen);
  };

  if (file) {
    return (
      <div className="picked">
        {previewUrl && (
          <video className="picked__preview" src={previewUrl} muted playsInline preload="metadata" />
        )}
        <div className="grow">
          <p className="picked__name truncate" title={file.name}>
            {file.name}
          </p>
          <p className="picked__meta mono faint">
            {formatBytes(file.size)} · {file.type || "video/mp4"}
          </p>
        </div>
        <Button variant="ghost" size="sm" disabled={disabled} onClick={() => onSelect(null)}>
          Remove
        </Button>
      </div>
    );
  }

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
      <p className="dropzone__title">Drop a video here</p>
      <p className="dropzone__hint faint">
        or click to choose — it uploads straight to R2, never through the API
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        onChange={(event) => pick(event.target.files)}
      />
    </div>
  );
}
