import { useCallback, useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "sau.theme";
const ORDER: readonly Theme[] = ["system", "light", "dark"];

function read(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return ORDER.includes(stored as Theme) ? (stored as Theme) : "system";
  } catch {
    return "system";
  }
}

/** Theme choice, applied as `data-theme` on <html>. "system" sets no attribute. */
export function useTheme(): { theme: Theme; cycle: () => void } {
  const [theme, setTheme] = useState<Theme>(read);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* the choice still applies for this session */
    }
  }, [theme]);

  const cycle = useCallback(
    () => setTheme((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length] ?? "system"),
    [],
  );

  return { theme, cycle };
}
