import { cx } from "../lib/cx";
import "./Tabs.css";

export interface TabItem {
  id: string;
  label: string;
  accent?: string;
}

interface TabsProps {
  items: readonly TabItem[];
  active: string;
  onSelect: (id: string) => void;
  /** Labels the tablist for screen readers. */
  label: string;
}

export function Tabs({ items, active, onSelect, label }: TabsProps) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((item) => {
        const selected = item.id === active;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            className={cx("tabs__tab", selected && "tabs__tab--active")}
            style={selected && item.accent ? { borderBottomColor: item.accent } : undefined}
            onClick={() => onSelect(item.id)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
