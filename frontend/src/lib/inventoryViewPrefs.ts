export type InventoryViewMode = "summary" | "detail";

const VIEW_KEY = "v14.inventory.view";
const COLLAPSED_LOCATIONS_KEY = "v14.inventory.collapsedLocations";

export function readInventoryViewMode(): InventoryViewMode {
  try {
    const v = localStorage.getItem(VIEW_KEY);
    return v === "detail" ? "detail" : "summary";
  } catch {
    return "summary";
  }
}

export function writeInventoryViewMode(mode: InventoryViewMode): void {
  try {
    localStorage.setItem(VIEW_KEY, mode);
  } catch {
    /* ignore */
  }
}

/** Location IDs that are collapsed in summary view (default: all collapsed). */
export function readCollapsedLocationIds(): Set<number> {
  try {
    const raw = localStorage.getItem(COLLAPSED_LOCATIONS_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((x): x is number => typeof x === "number"));
  } catch {
    return new Set();
  }
}

export function writeCollapsedLocationIds(ids: Set<number>): void {
  try {
    localStorage.setItem(COLLAPSED_LOCATIONS_KEY, JSON.stringify([...ids]));
  } catch {
    /* ignore */
  }
}
