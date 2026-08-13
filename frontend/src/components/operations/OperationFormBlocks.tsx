import type { ReactNode } from "react";
import { ArrowRight, Scale } from "lucide-react";
import Banner from "../ui/Banner";
import { cn } from "../../lib/cn";
import { formatQtyKg } from "../../lib/format";

const sectionTone = {
  primary:
    "border-primary-200/70 bg-primary-50/40 dark:border-primary-800/50 dark:bg-primary-950/25",
  violet: "border-primary-200/70 bg-primary-50/40 dark:border-primary-800/50 dark:bg-primary-950/20",
  emerald:
    "border-emerald-200/70 bg-emerald-50/40 dark:border-emerald-800/50 dark:bg-emerald-950/25",
  warning:
    "border-warning-200/70 bg-warning-50/40 dark:border-warning-800/50 dark:bg-warning-950/20",
  danger: "border-danger-200/70 bg-danger-50/35 dark:border-danger-800/50 dark:bg-danger-950/20",
  neutral: "border-line/80 bg-surface-subtle/30",
};

export function OperationSection({
  title,
  subtitle,
  children,
  tone = "neutral",
  step,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  tone?: keyof typeof sectionTone;
  step?: number;
}) {
  return (
    <section className={cn("space-y-4 rounded-2xl border p-5", sectionTone[tone])}>
      <div className="flex items-start gap-3">
        {step != null && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface text-sm font-bold text-ink shadow-sm ring-1 ring-line">
            {step}
          </span>
        )}
        <div className="min-w-0">
          <h3 className="truncate whitespace-nowrap text-base font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export function OperationLineCard({
  lineLabel,
  children,
  footer,
}: {
  lineLabel?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line/70 bg-surface p-4 shadow-sm">
      {lineLabel && (
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">{lineLabel}</p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{children}</div>
      {footer}
    </div>
  );
}

export function OperationBalanceBar({
  fromKg,
  toKg,
  lossKg,
  balanced,
}: {
  fromKg: number;
  toKg: number;
  lossKg: number;
  balanced: boolean;
}) {
  const gap = fromKg - toKg - lossKg;
  return (
    <div
      className={cn(
        "rounded-2xl border p-5",
        balanced
          ? "border-accent-200/70 bg-accent-50/40 dark:border-accent-800/50 dark:bg-accent-950/20"
          : "border-warning-200/70 bg-warning-50/40 dark:border-warning-800/50 dark:bg-warning-950/20"
      )}
    >
      <div className="mb-4 flex items-center gap-2">
        <Scale className="h-5 w-5 text-primary-600 dark:text-primary-300" aria-hidden="true" />
        <h4 className="text-lg font-semibold text-ink">Mass balance</h4>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-line/70 bg-surface/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">From kg</p>
          <p className="mt-2 v2-mono text-2xl font-bold text-ink">{fromKg.toFixed(3)}</p>
        </div>
        <div className="rounded-xl border border-line/70 bg-surface/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Sum to kg</p>
          <p className="mt-2 v2-mono text-2xl font-bold text-ink">{toKg.toFixed(3)}</p>
        </div>
        <div className="rounded-xl border border-line/70 bg-surface/80 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Loss kg</p>
          <p className="mt-2 v2-mono text-2xl font-bold text-warning-700 dark:text-warning-300">
            {lossKg.toFixed(3)}
          </p>
        </div>
      </div>
      <p
        className={cn(
          "mt-4 text-sm font-semibold",
          balanced ? "text-accent-700 dark:text-accent-300" : "text-warning-700 dark:text-warning-300"
        )}
      >
        {balanced ? "Balanced — ready to submit" : `Need ${gap.toFixed(3)} kg to balance`}
      </p>
    </div>
  );
}

export function StockAvailabilityHint({
  available,
  warning,
}: {
  available?: string;
  warning?: string | null;
}) {
  return (
    <div className="space-y-2">
      {available && (
        <p className="text-sm text-ink-muted">
          Available: <span className="font-medium text-ink">{available}</span>
        </p>
      )}
      {warning && <Banner tone="warning">{warning}</Banner>}
    </div>
  );
}

export function LocationFlowHint({
  fromName,
  toName,
  valid,
}: {
  fromName?: string;
  toName?: string;
  valid: boolean;
}) {
  if (!fromName || !toName) return null;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-xl border px-4 py-3 text-sm",
        valid
          ? "border-emerald-200/70 bg-emerald-50/50 text-emerald-900 dark:border-emerald-800/50 dark:bg-emerald-950/25 dark:text-emerald-100"
          : "border-warning-200/70 bg-warning-50/50 text-warning-900 dark:border-warning-800/50 dark:bg-warning-950/25 dark:text-warning-100"
      )}
    >
      <span className="font-semibold">{fromName}</span>
      <ArrowRight className="h-4 w-4 shrink-0 opacity-70" aria-hidden="true" />
      <span className="font-semibold">{toName}</span>
      {!valid && <span className="text-warning-700 dark:text-warning-300">— locations must differ</span>}
    </div>
  );
}

export function QtyPreview({ kg }: { kg: number }) {
  return (
    <div className="rounded-xl bg-surface-muted px-4 py-3">
      <p className="text-xs text-ink-subtle">Quantity</p>
      <p className="v2-mono text-xl font-bold text-ink">{formatQtyKg(kg)}</p>
    </div>
  );
}
