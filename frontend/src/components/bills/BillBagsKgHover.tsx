import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/cn";
import { formatBagsKgLabel } from "../../lib/billQty";

/** Hover tooltip “X bags · Y kg” for bill numbers on list (view only). */
export default function BillBagsKgHover({
  bags,
  kg,
  children,
  className,
}: {
  bags: number;
  kg: string | number;
  children: ReactNode;
  className?: string;
}) {
  const label = formatBagsKgLabel(bags, kg);
  const anchorRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const closeTimer = useRef<number | null>(null);

  const clearClose = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const placePanel = () => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const panelW = 200;
    const gap = 8;
    const placeBelow = r.bottom + 48 < window.innerHeight;
    const top = placeBelow ? r.bottom + gap : Math.max(12, r.top - gap - 36);
    const left = Math.min(Math.max(12, r.left), window.innerWidth - panelW - 12);
    setPos({ top, left });
  };

  const show = () => {
    clearClose();
    placePanel();
    setOpen(true);
  };

  const hide = () => {
    clearClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 80);
  };

  useEffect(() => () => clearClose(), []);

  return (
    <div
      ref={anchorRef}
      className={cn("relative inline-flex max-w-full items-center", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {open &&
        createPortal(
          <div
            role="tooltip"
            className="pointer-events-none fixed z-[80] whitespace-nowrap rounded-md border border-line/60 bg-surface/95 px-2.5 py-1.5 text-sm font-medium text-ink shadow-[0_8px_30px_rgb(var(--shadow-color)/0.18)] ring-1 ring-black/5 backdrop-blur-md dark:ring-white/10"
            style={{ top: pos.top, left: pos.left }}
          >
            {label}
          </div>,
          document.body
        )}
    </div>
  );
}
