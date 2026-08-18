import type { ReactNode } from "react";
import { cx } from "../lib/cx";
import "./Card.css";

interface CardProps {
  /** Small uppercase eyebrow, e.g. the step number. */
  step?: string;
  title: string;
  /** Right-hand slot in the header: counts, hints, small actions. */
  aside?: ReactNode;
  description?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ step, title, aside, description, className, children }: CardProps) {
  return (
    <section className={cx("card", className)}>
      <header className="card__head">
        <div className="grow">
          <h2 className="card__title">
            {step && <span className="card__step">{step}</span>}
            {title}
          </h2>
          {description && <p className="card__desc">{description}</p>}
        </div>
        {aside && <div className="card__aside">{aside}</div>}
      </header>
      {children}
    </section>
  );
}
