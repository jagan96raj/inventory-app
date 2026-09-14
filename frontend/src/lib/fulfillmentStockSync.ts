/** Cross-tab / same-tab notify so open fulfillment dialogs refetch physical stock. */

const EVENT = "fulfillment-stock-changed";
const CHANNEL = "graintrack-fulfillment-stock";

function channel(): BroadcastChannel | null {
  try {
    return typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(CHANNEL) : null;
  } catch {
    return null;
  }
}

export function notifyFulfillmentStockChanged(): void {
  window.dispatchEvent(new Event(EVENT));
  const ch = channel();
  ch?.postMessage({ t: Date.now() });
  ch?.close();
  try {
    localStorage.setItem(CHANNEL, String(Date.now()));
  } catch {
    /* ignore quota / private mode */
  }
}

export function subscribeFulfillmentStockChanged(onChange: () => void): () => void {
  const onWindow = () => onChange();
  window.addEventListener(EVENT, onWindow);
  const ch = channel();
  const onMessage = () => onChange();
  ch?.addEventListener("message", onMessage);
  const onStorage = (e: StorageEvent) => {
    if (e.key === CHANNEL) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EVENT, onWindow);
    window.removeEventListener("storage", onStorage);
    ch?.removeEventListener("message", onMessage);
    ch?.close();
  };
}
