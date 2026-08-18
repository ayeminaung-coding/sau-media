import type { ReactNode } from "react";
import "./EmptyState.css";

interface EmptyStateProps {
  title: string;
  hint?: ReactNode;
}

export function EmptyState({ title, hint }: EmptyStateProps) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {hint && <p className="empty__hint">{hint}</p>}
    </div>
  );
}
