import { useEffect, useRef } from "react";

/** Auto-logout after this much wall-clock time with no user activity. */
export const IDLE_LOGOUT_MS = 10 * 60 * 1000;

const CHECK_INTERVAL_MS = 15_000;
const PERSIST_THROTTLE_MS = 1000;
const LAST_ACTIVITY_KEY = "idle:lastActivity";

function readLastActivity(): number | null {
  try {
    const raw = localStorage.getItem(LAST_ACTIVITY_KEY);
    if (!raw) return null;
    const ts = Number(raw);
    return Number.isFinite(ts) ? ts : null;
  } catch {
    return null;
  }
}

function writeLastActivity(ts: number): void {
  try {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(ts));
  } catch {
    // Storage can be unavailable (private mode, quota).
  }
}

/** Stamp user activity so a later reload still counts idle time. */
export function recordIdleActivity(ts: number = Date.now()): void {
  writeLastActivity(ts);
}

const ACTIVITY_EVENTS: Array<keyof WindowEventMap> = [
  "mousemove",
  "mousedown",
  "keydown",
  "click",
  "touchstart",
  "scroll",
];

/**
 * Calls `onIdle` after {@link IDLE_LOGOUT_MS} with no pointer/keyboard/touch/scroll activity.
 * Hidden / minimized time counts toward the same limit (wall clock) — does not log out
 * immediately on minimize.
 */
export function useIdleLogout(enabled: boolean, onIdle: () => void | Promise<void>): void {
  const lastActiveRef = useRef(Date.now());
  const lastPersistedRef = useRef(0);
  const onIdleRef = useRef(onIdle);
  const loggingOutRef = useRef(false);

  useEffect(() => {
    onIdleRef.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!enabled) return;

    loggingOutRef.current = false;
    const stored = readLastActivity();
    const now = Date.now();
    lastActiveRef.current = stored ?? now;
    lastPersistedRef.current = stored ?? 0;
    if (stored == null) {
      lastPersistedRef.current = now;
      writeLastActivity(now);
    }

    const persist = (ts: number) => {
      lastPersistedRef.current = ts;
      writeLastActivity(ts);
    };

    const bump = () => {
      const ts = Date.now();
      lastActiveRef.current = ts;
      if (ts - lastPersistedRef.current >= PERSIST_THROTTLE_MS) persist(ts);
    };

    const flush = () => {
      if (lastActiveRef.current !== lastPersistedRef.current) persist(lastActiveRef.current);
    };

    const check = () => {
      if (loggingOutRef.current) return;
      if (Date.now() - lastActiveRef.current < IDLE_LOGOUT_MS) return;
      loggingOutRef.current = true;
      void Promise.resolve(onIdleRef.current()).catch(() => {
        // Keep locked out of loops if logout fails mid-flight.
      });
    };

    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
      check();
    };

    check();

    for (const evt of ACTIVITY_EVENTS) {
      window.addEventListener(evt, bump, { capture: true, passive: true });
    }
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", flush);
    const intervalId = window.setInterval(check, CHECK_INTERVAL_MS);

    return () => {
      flush();
      for (const evt of ACTIVITY_EVENTS) {
        window.removeEventListener(evt, bump, { capture: true });
      }
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", flush);
      window.clearInterval(intervalId);
    };
  }, [enabled]);
}
