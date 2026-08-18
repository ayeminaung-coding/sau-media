import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createClient } from "../api/client";
import type { SauClient } from "../api/client";
import { DEFAULT_API_BASE, readApiBase, writeApiBase } from "../api/config";

interface ApiContextValue {
  base: string;
  setBase: (value: string) => void;
  client: SauClient;
  isDefaultBase: boolean;
}

const ApiContext = createContext<ApiContextValue | null>(null);

/** Owns the API base URL so every hook below shares one client instance. */
export function ApiProvider({ children }: { children: ReactNode }) {
  const [base, setBaseState] = useState(readApiBase);

  const setBase = useCallback((value: string) => {
    const trimmed = value.trim().replace(/\/+$/, "");
    writeApiBase(trimmed);
    setBaseState(trimmed);
  }, []);

  const value = useMemo<ApiContextValue>(
    () => ({
      base,
      setBase,
      client: createClient(base),
      isDefaultBase: base === DEFAULT_API_BASE,
    }),
    [base, setBase],
  );

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiContextValue {
  const value = useContext(ApiContext);
  if (!value) throw new Error("useApi must be used inside <ApiProvider>");
  return value;
}
