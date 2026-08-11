import { useEffect, useRef } from "react";

/** Auto-logout after this much wall-clock time with no user activity. */
export const IDLE_LOGOUT_MS = 10 * 60 * 1000;

const CHECK_INTERVAL_MS = 15_000;

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
  const onIdleRef = useRef(onIdle);
  const loggingOutRef = useRef(false);

  useEffect(() => {
    onIdleRef.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!enabled) return;

    lastActiveRef.current = Date.now();
    loggingOutRef.current = false;

    const bump = () => {
      lastActiveRef.current = Date.now();
    };

    const check = () => {
      if (loggingOutRef.current) return;
      if (Date.now() - lastActiveRef.current < IDLE_LOGOUT_MS) return;
      loggingOutRef.current = true;
      void Promise.resolve(onIdleRef.current()).catch(() => {
        // Keep locked out of loops if logout fails mid-flight.
      });
    };

    for (const evt of ACTIVITY_EVENTS) {
      window.addEventListener(evt, bump, { capture: true, passive: true });
    }
    document.addEventListener("visibilitychange", check);
    const intervalId = window.setInterval(check, CHECK_INTERVAL_MS);

    return () => {
      for (const evt of ACTIVITY_EVENTS) {
        window.removeEventListener(evt, bump, { capture: true });
      }
      document.removeEventListener("visibilitychange", check);
      window.clearInterval(intervalId);
    };
  }, [enabled]);
}
