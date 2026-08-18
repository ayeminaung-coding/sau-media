import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import "./Badge.css";

export type BadgeTone = "neutral" | "running" | "ok" | "err" | "accent";

interface BadgeProps {
  tone?: BadgeTone;
  title?: string;
  children: ReactNode;
}

export function Badge({ tone = "neutral", title, children }: BadgeProps) {
  return (
    <span className={cx("badge", `badge--${tone}`)} title={title}>
      <span className="badge__dot" aria-hidden="true" />
      {children}
    </span>
  );
}
