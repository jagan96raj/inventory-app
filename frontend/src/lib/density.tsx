import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Density = "comfortable" | "compact";

type DensityCtx = {
  density: Density;
  setDensity: (d: Density) => void;
  toggle: () => void;
};

const STORAGE_KEY = "v13.density";
const Ctx = createContext<DensityCtx | null>(null);

function read(): Density {
  if (typeof window === "undefined") return "comfortable";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "compact" ? "compact" : "comfortable";
}

function apply(d: Density) {
  if (typeof document === "undefined") return;
  if (d === "compact") document.documentElement.dataset.density = "compact";
  else delete document.documentElement.dataset.density;
}

export function DensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensityState] = useState<Density>(() => read());

  useEffect(() => apply(density), [density]);

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    try {
      window.localStorage.setItem(STORAGE_KEY, d);
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(() => {
    setDensity(density === "compact" ? "comfortable" : "compact");
  }, [density, setDensity]);

  const value = useMemo<DensityCtx>(
    () => ({ density, setDensity, toggle }),
    [density, setDensity, toggle]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDensity(): DensityCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useDensity must be inside DensityProvider");
  return ctx;
}
