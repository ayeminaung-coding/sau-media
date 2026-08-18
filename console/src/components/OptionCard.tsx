import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import "./OptionCard.css";

interface OptionCardProps {
  type: "checkbox" | "radio";
  name?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
  description: ReactNode;
  /** Border colour when selected; defaults to the accent. */
  accent?: string;
}

/**
 * A checkbox or radio drawn as a card. Used for both the platform picker and
 * the publish-vs-backlog choice so the two read as the same kind of decision.
 */
export function OptionCard({
  type,
  name,
  checked,
  onChange,
  title,
  description,
  accent,
}: OptionCardProps) {
  return (
    <label
      className={cx("option", checked && "option--on")}
      style={checked && accent ? { borderColor: accent } : undefined}
    >
      <input
        type={type}
        name={name}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="option__input"
      />
      <span className="option__body">
        <span className="option__title">{title}</span>
        <span className="option__desc">{description}</span>
      </span>
    </label>
  );
}
