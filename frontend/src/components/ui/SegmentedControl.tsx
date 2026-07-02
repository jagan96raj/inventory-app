import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type SegmentOption<T extends string> = {
  value: T;
  label: ReactNode;
  hint?: ReactNode;
};

type Props<T extends string> = {
  value: T;
  onChange: (v: T) => void;
  options: SegmentOption<T>[];
  size?: "sm" | "md" | "lg";
  ariaLabel?: string;
  className?: string;
};

export default function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  size = "lg",
  ariaLabel,
  className,
}: Props<T>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-stretch gap-2 rounded-2xl border border-line/80 bg-surface-muted/80 p-2",
        size === "sm" && "gap-1.5 rounded-xl p-1.5",
        size === "md" && "gap-1.5 p-1.5",
        className
      )}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex flex-col items-center justify-center gap-0.5 rounded-xl transition-colors",
              "outline-none focus:outline-none focus-visible:outline-none",
              "focus-visible:ring-2 focus-visible:ring-primary-500/35 focus-visible:ring-offset-1 focus-visible:ring-offset-surface-muted",
              size === "sm"
                ? "min-h-[2.5rem] min-w-[4rem] px-4 text-base"
                : size === "md"
                  ? "min-h-[2.75rem] min-w-[4.5rem] px-4 text-base"
                  : "min-h-[3.25rem] min-w-[5rem] px-5 text-lg",
              active
                ? "bg-surface font-semibold text-ink shadow-soft ring-1 ring-line/70"
                : "font-medium text-ink-muted hover:bg-surface/60 hover:text-ink"
            )}
          >
            <span>{o.label}</span>
            {o.hint && size === "lg" && (
              <span className={cn("text-xs uppercase tracking-wider", active ? "text-ink-subtle" : "text-ink-subtle/80")}>
                {o.hint}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
