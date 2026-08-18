import { useCallback, useEffect, useState } from "react";
import { DEFAULT_VIEW, findView, type ViewId } from "../domain/navigation";

const STORAGE_KEY = "sau.view";

function read(): ViewId {
  try {
    return findView(window.localStorage.getItem(STORAGE_KEY))?.id ?? DEFAULT_VIEW;
  } catch {
    return DEFAULT_VIEW;
  }
}

/**
 * Which view the sidebar has selected, remembered per browser.
 *
 * Locked views are selectable on purpose — they render their Coming soon page
 * rather than being inert, so an operator can see what is planned.
 */
export function useNav(): { view: ViewId; select: (id: ViewId) => void } {
  const [view, setView] = useState<ViewId>(read);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, view);
    } catch {
      /* the choice still applies for this session */
    }
  }, [view]);

  const select = useCallback((id: ViewId) => setView(id), []);

  return { view, select };
}
