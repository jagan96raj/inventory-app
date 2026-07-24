import type { CashBookEntry } from "../api/client";

const LAST_CREATED_KEY = "inventory.cashbook.lastCreated";
/** Only reuse remembered create for a short window (covers Electron state loss). */
const REMEMBER_MS = 120_000;

type Stored = { entry: CashBookEntry; at: number };

/** Survive Electron dropping react-router location.state after create. */
export function rememberCashBookCreated(entry: CashBookEntry): void {
  try {
    const payload: Stored = { entry, at: Date.now() };
    sessionStorage.setItem(LAST_CREATED_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function readRememberedCashBookCreated(): CashBookEntry | null {
  try {
    const raw = sessionStorage.getItem(LAST_CREATED_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored | CashBookEntry;
    // Backward-compatible: plain entry or { entry, at }
    if (parsed && typeof parsed === "object" && "entry" in parsed) {
      const stored = parsed as Stored;
      if (!stored.entry || typeof stored.entry.id !== "number") return null;
      if (Date.now() - stored.at > REMEMBER_MS) {
        sessionStorage.removeItem(LAST_CREATED_KEY);
        return null;
      }
      return stored.entry;
    }
    const entry = parsed as CashBookEntry;
    if (!entry || typeof entry.id !== "number") return null;
    return entry;
  } catch {
    return null;
  }
}

export function clearRememberedCashBookCreated(id?: number): void {
  try {
    if (id == null) {
      sessionStorage.removeItem(LAST_CREATED_KEY);
      return;
    }
    const cur = readRememberedCashBookCreated();
    if (!cur || cur.id === id) sessionStorage.removeItem(LAST_CREATED_KEY);
  } catch {
    /* ignore */
  }
}
