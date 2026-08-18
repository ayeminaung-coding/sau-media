/**
 * Where the API lives, resolved once per session.
 *
 * Build-time `VITE_API_BASE_URL` is the default so a deployed console works
 * with no setup; a runtime override is kept in localStorage so one static
 * build can be pointed at staging or a laptop without rebuilding.
 */

const STORAGE_KEY = "sau.apiBase";

export const DEFAULT_API_BASE: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8001";

export function readApiBase(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? DEFAULT_API_BASE;
  } catch {
    // Private-mode Safari and some embedded webviews throw on access.
    return DEFAULT_API_BASE;
  }
}

export function writeApiBase(value: string): void {
  try {
    if (value === DEFAULT_API_BASE) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* not persisting is survivable; the value still applies this session */
  }
}
