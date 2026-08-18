import { useState } from "react";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { DEFAULT_API_BASE } from "../../api/config";
import { useApi } from "../../hooks/useApi";
import { useHealth } from "../../hooks/useHealth";
import { useTheme } from "../../hooks/useTheme";
import "./TopBar.css";

const THEME_ICON = { system: "◐", light: "☀", dark: "☾" } as const;

export function TopBar() {
  const { base, setBase } = useApi();
  const { status, version, refresh } = useHealth();
  const { theme, cycle } = useTheme();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(base);

  const apply = () => {
    setBase(draft);
    setOpen(false);
    refresh();
  };

  return (
    <header className="topbar">
      <div className="topbar__inner">
        <div className="topbar__brand">
          <span className="topbar__mark" aria-hidden="true" />
          <span className="topbar__name">Socials Auto Upload</span>
          <span className="topbar__sub faint">console</span>
        </div>

        <div className="grow" />

        {status === "up" && <Badge tone="ok">api ok · v{version}</Badge>}
        {status === "checking" && <Badge tone="neutral">checking…</Badge>}
        {status === "down" && (
          <Badge tone="err" title="Is the stack up, and is this origin listed in CORS_ORIGINS?">
            api unreachable
          </Badge>
        )}

        <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          Endpoint
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={cycle}
          title={`Theme: ${theme}`}
          aria-label={`Theme: ${theme}. Click to change.`}
        >
          {THEME_ICON[theme]}
        </Button>
      </div>

      {open && (
        <div className="topbar__panel">
          <div className="topbar__panel-inner">
            <label className="topbar__label" htmlFor="api-base">
              API base URL
            </label>
            <input
              id="api-base"
              className="topbar__input mono"
              type="url"
              value={draft}
              spellCheck={false}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && apply()}
            />
            <Button variant="primary" size="sm" onClick={apply}>
              Use
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(DEFAULT_API_BASE);
                setBase(DEFAULT_API_BASE);
              }}
            >
              Reset
            </Button>
          </div>
          <p className="topbar__note faint">
            Stored in this browser only. The API must list this page's origin in{" "}
            <code>CORS_ORIGINS</code>.
          </p>
        </div>
      )}
    </header>
  );
}
