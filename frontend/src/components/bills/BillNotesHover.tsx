import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { StickyNote } from "lucide-react";
import { cn } from "../../lib/cn";

/** Hover-only notes panel for bills list (view only). */
export default function BillNotesHover({
  notes,
  children,
  className,
}: {
  notes?: string | null;
  children: ReactNode;
  className?: string;
}) {
  const trimmed = notes?.trim() ?? "";
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
    if (!el || !trimmed) return;
    const r = el.getBoundingClientRect();
    const panelW = 280;
    const gap = 10;
    const placeBelow = r.bottom + 160 < window.innerHeight;
    const top = placeBelow
      ? r.bottom + gap
      : Math.max(12, r.top - gap - 120);
    const left = Math.min(Math.max(12, r.left), window.innerWidth - panelW - 12);
    setPos({ top, left });
  };

  const show = () => {
    clearClose();
    if (!trimmed) return;
    placePanel();
    setOpen(true);
  };

  const hide = () => {
    clearClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 80);
  };

  useEffect(() => () => clearClose(), []);

  if (!trimmed) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      ref={anchorRef}
      className={cn("relative inline-flex max-w-full items-center gap-1.5", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      <StickyNote
        className="h-3.5 w-3.5 shrink-0 text-amber-600/80 dark:text-amber-400/80"
        aria-hidden="true"
      />
      {open &&
        createPortal(
          <div
            role="tooltip"
            className="pointer-events-none fixed z-[80] w-[280px] overflow-hidden rounded-lg border border-line/60 bg-surface/95 shadow-[0_8px_30px_rgb(var(--shadow-color)/0.18)] ring-1 ring-black/5 backdrop-blur-md dark:ring-white/10"
            style={{ top: pos.top, left: pos.left }}
          >
            <div className="flex items-center gap-1.5 border-b border-line/50 bg-surface-muted/50 px-3 py-1.5">
              <StickyNote className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" aria-hidden="true" />
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Notes</p>
            </div>
            <div className="max-h-40 overflow-y-auto px-3 py-2.5">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{trimmed}</p>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
