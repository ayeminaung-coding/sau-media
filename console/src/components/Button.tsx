import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/cx";
import "./Button.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cx("btn", `btn--${variant}`, `btn--${size}`, loading && "btn--loading", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className="btn__spinner" aria-hidden="true" />}
      <span className="btn__label">{children}</span>
    </button>
  );
}
