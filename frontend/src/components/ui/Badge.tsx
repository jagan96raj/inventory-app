import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type Tone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "muted";

const toneClass: Record<Tone, string> = {
  neutral:
    "bg-surface-muted text-ink-muted border border-line",
  primary:
    "bg-primary-50 text-primary-700 border border-primary-200 dark:bg-primary-900/30 dark:text-primary-200 dark:border-primary-800/50",
  success:
    "bg-accent-50 text-accent-700 border border-accent-200 dark:bg-accent-900/30 dark:text-accent-200 dark:border-accent-800/50",
  warning:
    "bg-warning-50 text-warning-700 border border-warning-200 dark:bg-warning-900/30 dark:text-warning-200 dark:border-warning-800/50",
  danger:
    "bg-danger-50 text-danger-700 border border-danger-200 dark:bg-danger-900/30 dark:text-danger-200 dark:border-danger-800/50",
  info:
    "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-900/30 dark:text-sky-200 dark:border-sky-800/50",
  muted:
    "bg-zinc-100 text-zinc-600 border border-zinc-200 dark:bg-zinc-800/60 dark:text-zinc-300 dark:border-zinc-700",
};

type Props = {
  tone?: Tone;
  size?: "sm" | "md";
  dot?: boolean;
  className?: string;
  children: ReactNode;
};

export default function Badge({
  tone = "neutral",
  size = "md",
  dot,
  className,
  children,
}: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium leading-none",
        toneClass[tone],
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full bg-current opacity-70")} aria-hidden="true" />}
      {children}
    </span>
  );
}
