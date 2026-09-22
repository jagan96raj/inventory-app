import { useEffect, useState } from "react";
import { api } from "../api/client";

export type BotProtectionStatus = {
  enabled: boolean;
  provider: "turnstile" | null;
  site_key: string | null;
};

export function useBotProtectionStatus() {
  const [status, setStatus] = useState<BotProtectionStatus>({
    enabled: false,
    provider: null,
    site_key: null,
  });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<BotProtectionStatus>("/api/auth/bot-protection-status", {
          skipAuthRedirect: true,
        });
        if (!cancelled) setStatus(data);
      } catch {
        if (!cancelled) {
          setStatus({ enabled: false, provider: null, site_key: null });
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, loaded };
}
