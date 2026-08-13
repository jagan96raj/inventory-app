import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import type { Tone } from "./Badge";

type Props = {
  label: ReactNode;
  value: string | number;
  unit?: ReactNode;
  delta?: { value: number; label?: string } | null;
  icon?: ReactNode;
  tone?: Tone;
  sparkline?: ReactNode;
  animateValue?: boolean;
  className?: string;
  footer?: ReactNode;
};

const toneRing: Record<Tone, string> = {
  neutral: "from-zinc-100 to-zinc-50 dark:from-zinc-800 dark:to-zinc-900 text-zinc-600 dark:text-zinc-300",
  primary: "from-primary-100 to-primary-50 dark:from-primary-900/40 dark:to-primary-900/10 text-primary-600 dark:text-primary-300",
  success: "from-accent-100 to-accent-50 dark:from-accent-900/40 dark:to-accent-900/10 text-accent-700 dark:text-accent-300",
  warning: "from-warning-100 to-warning-50 dark:from-warning-900/40 dark:to-warning-900/10 text-warning-700 dark:text-warning-300",
  danger: "from-danger-100 to-danger-50 dark:from-danger-900/40 dark:to-danger-900/10 text-danger-700 dark:text-danger-300",
  info: "from-sky-100 to-sky-50 dark:from-sky-900/40 dark:to-sky-900/10 text-sky-700 dark:text-sky-300",
  muted: "from-zinc-100 to-zinc-50 dark:from-zinc-800 dark:to-zinc-900 text-zinc-500 dark:text-zinc-400",
};

function useAnimatedNumber(target: number, enabled: boolean) {
  const [value, setValue] = useState(enabled ? 0 : target);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(0);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      setValue(target);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    let raf = 0;
    startRef.current = null;
    fromRef.current = value;
    const dur = 700;
    const step = (ts: number) => {
      if (startRef.current == null) startRef.current = ts;
      const t = Math.min(1, (ts - startRef.current) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(fromRef.current + (target - fromRef.current) * eased);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, enabled]);

  return value;
}

export default function Stat({
  label,
  value,
  unit,
  delta,
  icon,
  tone = "primary",
  sparkline,
  animateValue,
  className,
  footer,
}: Props) {
  const numeric = typeof value === "number";
  const display = useAnimatedNumber(numeric ? (value as number) : 0, !!animateValue && numeric);
  const deltaTone =
    delta == null ? null : delta.value > 0 ? "success" : delta.value < 0 ? "danger" : "muted";
  return (
    <div
      className={cn(
        "v2-card relative overflow-hidden p-5 transition-shadow hover:shadow-lg",
        className
      )}
    >
      <div
        className={cn(
          "absolute right-0 top-0 h-24 w-24 rounded-full bg-gradient-to-br opacity-50 blur-2xl",
          toneRing[tone]
        )}
        aria-hidden="true"
      />
      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium uppercase tracking-wider text-ink-subtle">{label}</p>
          <p className="mt-2 flex min-w-0 flex-wrap items-baseline gap-1.5 text-xl font-semibold tracking-tight text-ink sm:text-2xl">
            <span className="v2-mono min-w-0 break-words tabular-nums">
              {numeric
                ? display.toLocaleString("en-IN", { maximumFractionDigits: 0 })
                : value}
            </span>
            {unit && <span className="text-sm font-medium text-ink-muted">{unit}</span>}
          </p>
          {delta && (
            <p className="mt-2 inline-flex items-center gap-1 text-sm font-medium">
              <span
                className={cn(
                  "inline-flex h-5 items-center rounded-full px-1.5 v2-mono",
                  deltaTone === "success" && "bg-accent-50 text-accent-700 dark:bg-accent-900/30 dark:text-accent-200",
                  deltaTone === "danger" && "bg-danger-50 text-danger-700 dark:bg-danger-900/30 dark:text-danger-200",
                  deltaTone === "muted" && "bg-surface-muted text-ink-muted"
                )}
              >
                {delta.value > 0 ? "▲" : delta.value < 0 ? "▼" : "•"} {Math.abs(delta.value).toFixed(1)}%
              </span>
              {delta.label && <span className="text-ink-subtle">{delta.label}</span>}
            </p>
          )}
        </div>
        {icon && (
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br [&>svg]:h-5 [&>svg]:w-5", toneRing[tone])}>
            {icon}
          </div>
        )}
      </div>
      {sparkline && <div className="relative mt-4 h-12">{sparkline}</div>}
      {footer && <div className="relative mt-3 text-sm text-ink-subtle">{footer}</div>}
    </div>
  );
}
