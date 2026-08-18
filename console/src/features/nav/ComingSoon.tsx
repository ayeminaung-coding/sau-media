import { Card } from "../../components/Card";
import type { NavItem } from "../../domain/navigation";
import "./ComingSoon.css";

interface ComingSoonProps {
  item: NavItem;
}

/**
 * The page every locked view renders. It states plainly that nothing here is
 * built yet — an operator should never be left guessing whether a blank panel
 * is a feature that failed to load.
 */
export function ComingSoon({ item }: ComingSoonProps) {
  return (
    <Card
      title={item.label}
      description={item.description}
      aside={<span className="soon__tag">Coming soon</span>}
    >
      <div className="soon">
        <span className="soon__mark" aria-hidden="true">
          {item.icon}
        </span>
        <p className="soon__lead">
          Not built yet. Nothing on this page reads or changes anything — the pipeline runs without
          it.
        </p>
        {item.plans && (
          <>
            <p className="soon__heading">What it will do</p>
            <ul className="soon__list">
              {item.plans.map((plan) => (
                <li key={plan}>{plan}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
}
