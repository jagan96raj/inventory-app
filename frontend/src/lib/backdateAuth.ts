import { localIsoDate } from "./format";

/** True when the selected calendar date is before today (local). */
export function isBackdatedDate(iso: string | null | undefined): boolean {
  return Boolean(iso) && iso < localIsoDate();
}

export function isAuthPasswordError(message: string): boolean {
  const m = message.toLowerCase();
  return m.includes("authorization") || m.includes("password");
}
