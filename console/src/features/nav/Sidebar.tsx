import { NAV, NAV_GROUPS, type ViewId } from "../../domain/navigation";
import { cx } from "../../lib/cx";
import "./Sidebar.css";

interface SidebarProps {
  view: ViewId;
  onSelect: (id: ViewId) => void;
}

/**
 * The one navigation surface: a rail on the desktop, a scrolling tab strip
 * below the header on narrow screens. Both render the same list, so a view
 * that appears in `domain/navigation.ts` needs no change here.
 *
 * Marked up as navigation with `aria-current`, not as an ARIA tablist: it
 * swaps the whole view and survives reloads, so it behaves like page
 * navigation, and a tablist would owe the reader arrow-key roving it does not
 * have.
 */
export function Sidebar({ view, onSelect }: SidebarProps) {
  return (
    <nav className="sidebar" aria-label="Console sections">
      {NAV_GROUPS.map((group) => {
        const items = NAV.filter((item) => item.group === group);
        if (items.length === 0) return null;
        return (
          <div className="sidebar__group" key={group}>
            <p className="sidebar__group-label">{group}</p>
            {items.map((item) => {
              const active = item.id === view;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "sidebar__item",
                    active && "sidebar__item--active",
                    item.locked && "sidebar__item--locked",
                  )}
                  title={item.description}
                  onClick={() => onSelect(item.id)}
                >
                  <span className="sidebar__icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span className="sidebar__label truncate">{item.label}</span>
                  {item.locked && (
                    <span className="sidebar__lock" title="Coming soon">
                      <span aria-hidden="true">🔒</span>
                      <span className="visually-hidden">Coming soon</span>
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
