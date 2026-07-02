import { useCallback, useRef, useState } from "react";

/**
 * Spec v15.8 — disable Save/Submit while a mutation request is in flight.
 * Reuse the same idempotency key until success via caller's idemKeyRef.
 */
export function useSubmitGuard() {
  const [submitting, setSubmitting] = useState(false);
  const inFlightRef = useRef(false);

  const guardedSubmit = useCallback(
    async (fn: () => Promise<void>) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setSubmitting(true);
      try {
        await fn();
      } finally {
        inFlightRef.current = false;
        setSubmitting(false);
      }
    },
    []
  );

  return { submitting, guardedSubmit, submitDisabled: submitting };
}
