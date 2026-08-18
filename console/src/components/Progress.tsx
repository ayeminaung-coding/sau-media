import { cx } from "../lib/cx";
import "./Progress.css";

interface ProgressProps {
  /** 0–1. */
  value: number;
  tone?: "accent" | "ok" | "err" | "warn";
  label?: string;
}

export function Progress({ value, tone = "accent", label }: ProgressProps) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      className={cx("progress", `progress--${tone}`)}
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className="progress__fill" style={{ width: `${pct}%` }} />
    </div>
  );
}
