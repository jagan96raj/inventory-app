import { MapPin, Package } from "lucide-react";
import { formatQtyKg } from "../lib/format";
import { deliveryStatusLabel } from "../lib/statusLabels";
import { themeForBillType } from "../lib/billTypeTheme";
import { cn } from "../lib/cn";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import { Card, CardBody, CardHeader } from "./ui/Card";
import { DeliveryPill } from "./ui/StatusPill";

export type FulfillmentLineSummary = {
  bill_number: string;
  bill_type: string;
  customer_name: string;
  product_name: string;
  brand_name: string;
  bag_type_name: string;
  is_loose: boolean;
  ordered_bags: number;
  bags_delivered: number;
  ordered_kg: string;
  fulfilled_kg: string;
  remaining_kg: string;
  remaining_bags: number;
  line_delivery_status: string;
  bill_location_name?: string | null;
  location_name?: string | null;
  stock_bags?: number;
  stock_kg?: string;
};

type QtyTone = "neutral" | "primary" | "success" | "warning";

function QtyMiniStat({
  label,
  primary,
  secondary,
  tone = "neutral",
}: {
  label: string;
  primary: string;
  secondary?: string;
  tone?: QtyTone;
}) {
  const toneClass: Record<QtyTone, string> = {
    neutral: "border-line bg-surface-subtle",
    primary: "border-primary-200/80 bg-primary-50/80 dark:border-primary-800/50 dark:bg-primary-950/35",
    success: "border-accent-200/80 bg-accent-50/80 dark:border-accent-800/50 dark:bg-accent-950/35",
    warning: "border-warning-200/80 bg-warning-50/80 dark:border-warning-800/50 dark:bg-warning-950/35",
  };
  const textClass: Record<QtyTone, string> = {
    neutral: "text-ink",
    primary: "text-primary-800 dark:text-primary-200",
    success: "text-accent-800 dark:text-accent-200",
    warning: "text-warning-800 dark:text-warning-200",
  };

  return (
    <div className={cn("rounded-xl border px-4 py-3", toneClass[tone])}>
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">{label}</p>
      <p
        className={cn(
          "mt-1 v2-mono text-lg font-bold tabular-nums whitespace-nowrap sm:text-xl",
          textClass[tone]
        )}
      >
        {primary}
      </p>
      {secondary && <p className="mt-0.5 text-sm text-ink-muted">{secondary}</p>}
    </div>
  );
}

function formatQtyPair(bags: number, kg: string, isLoose: boolean) {
  if (isLoose) return { primary: formatQtyKg(kg), secondary: undefined };
  return { primary: `${bags} bags`, secondary: formatQtyKg(kg) };
}

type ContextProps = {
  line: FulfillmentLineSummary;
  mode: "deliver" | "return";
  salesLocationName?: string;
  /** Hide duplicate location block when shown above the card (sales deliver dialog) */
  highlightBillLocation?: boolean;
  returnableKg?: string;
  returnableBags?: number;
};

export function FulfillmentContextCard({
  line,
  mode,
  salesLocationName,
  highlightBillLocation = false,
  returnableKg,
  returnableBags,
}: ContextProps) {
  const isPurchase = line.bill_type === "purchase";
  const theme = themeForBillType(line.bill_type);
  const ordered = formatQtyPair(line.ordered_bags, line.ordered_kg, line.is_loose);
  const done = formatQtyPair(line.bags_delivered, line.fulfilled_kg, line.is_loose);
  const isReturnSales = mode === "return" && !isPurchase;
  const isReturnPurchase = mode === "return" && isPurchase && returnableKg != null;

  let remainingLabel: string;
  let remainingPrimary: string;
  let remainingSecondary: string | undefined;
  let remainingTone: QtyTone;

  if (isReturnSales) {
    remainingLabel = "Can return";
    if (line.is_loose) {
      remainingPrimary = formatQtyKg(line.fulfilled_kg);
      remainingSecondary = undefined;
    } else {
      remainingPrimary = `${line.bags_delivered} bags`;
      remainingSecondary = formatQtyKg(line.fulfilled_kg);
    }
    remainingTone = Number(line.fulfilled_kg) > 0 ? "warning" : "neutral";
  } else if (isReturnPurchase) {
    remainingLabel = "Can return";
    remainingPrimary = line.is_loose
      ? formatQtyKg(returnableKg!)
      : `${returnableBags ?? 0} bags`;
    remainingSecondary = line.is_loose ? undefined : formatQtyKg(returnableKg!);
    remainingTone = Number(returnableKg) > 0 ? "warning" : "neutral";
  } else {
    remainingLabel = isPurchase ? "Still to receive" : "Still to deliver";
    if (line.is_loose) {
      remainingPrimary = formatQtyKg(line.remaining_kg);
      remainingSecondary = undefined;
    } else {
      remainingPrimary = `${line.remaining_bags} bags`;
      remainingSecondary = formatQtyKg(line.remaining_kg);
    }
    remainingTone = Number(line.remaining_kg) > 0 ? "warning" : "neutral";
  }

  return (
    <Card className={cn("overflow-hidden border-line/80", theme.filterGradient)}>
      <CardHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-2">
            <Badge tone={theme.badgeTone} size="md">
              {theme.label}
            </Badge>
            <span className={cn("v2-mono text-xl font-bold", theme.billNumber)}>{line.bill_number}</span>
          </span>
        }
        subtitle={line.customer_name}
      />
      <CardBody className="space-y-5 pt-0">
        <div className="rounded-xl border border-line/80 bg-surface/80 px-4 py-3.5">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-muted text-primary-600 dark:text-primary-300">
              <Package className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-lg font-bold text-ink">{line.product_name}</p>
              <p className="mt-0.5 text-base text-ink-muted">
                {line.brand_name} · {line.bag_type_name}
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <QtyMiniStat label="Ordered" primary={ordered.primary} secondary={ordered.secondary} />
          <QtyMiniStat
            label={isPurchase ? "Received" : "Delivered"}
            primary={done.primary}
            secondary={done.secondary}
            tone="success"
          />
          <QtyMiniStat
            label={remainingLabel}
            primary={remainingPrimary}
            secondary={remainingSecondary}
            tone={remainingTone}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm">
          <DeliveryPill status={line.line_delivery_status} />
          <span className="text-ink-muted">{deliveryStatusLabel(line.line_delivery_status)}</span>
        </div>

        {!isPurchase && salesLocationName && !highlightBillLocation && (
          <div className="rounded-xl border-2 border-primary-300/70 bg-gradient-to-r from-primary-50/90 to-primary-50/50 px-4 py-3.5 dark:border-primary-700/50 dark:from-primary-950/40 dark:to-primary-950/25">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary-700 dark:text-primary-300">
              {mode === "return" ? "Originally billed from" : "Billed from location"}
            </p>
            <p className="mt-1 flex items-center gap-2 text-lg font-bold text-primary-900 dark:text-primary-50">
              <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
              {salesLocationName}
            </p>
            {mode === "deliver" && line.stock_kg != null && (
              <p className="mt-1.5 text-sm text-ink-muted">
                On hand:{" "}
                {line.is_loose
                  ? formatQtyKg(line.stock_kg)
                  : `${line.stock_bags ?? 0} bags · ${formatQtyKg(line.stock_kg)}`}
              </p>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export type ReceiveEntry = {
  entry_id: number;
  location_name: string;
  delivered_kg: string;
  delivered_bags: number;
  returnable_kg: string;
  returnable_bags: number;
  fulfilled_at: string | null;
};

function formatEntryWhen(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function FulfillmentReceiveEntryPicker({
  isLoose,
  entries,
  onSelectEntry,
}: {
  isLoose: boolean;
  entries: ReceiveEntry[];
  onSelectEntry: (entryId: number) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">
        Pick one receive entry — stock will be subtracted only from that location.
      </p>
      {entries.map((entry) => {
          const received = isLoose
            ? formatQtyKg(entry.delivered_kg)
            : `${entry.delivered_bags} bags · ${formatQtyKg(entry.delivered_kg)}`;
          const returnable = isLoose
            ? formatQtyKg(entry.returnable_kg)
            : `${entry.returnable_bags} bags · ${formatQtyKg(entry.returnable_kg)}`;
          return (
            <div
              key={entry.entry_id}
              className="flex flex-col gap-3 rounded-2xl border border-line/80 bg-surface-subtle/50 p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <p className="flex items-center gap-2 font-semibold text-ink">
                  <MapPin className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                  {entry.location_name}
                </p>
                <p className="text-sm text-ink-muted">
                  Received <span className="v2-mono font-medium text-ink">{received}</span>
                  {" · "}
                  {formatEntryWhen(entry.fulfilled_at)}
                </p>
                <p className="text-sm text-ink-muted">
                  Returnable: <span className="v2-mono font-semibold text-warning-700 dark:text-warning-300">{returnable}</span>
                </p>
              </div>
              <Button
                type="button"
                variant="primary"
                className="from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700"
                onClick={() => onSelectEntry(entry.entry_id)}
              >
                Return from this
              </Button>
            </div>
          );
        })}
    </div>
  );
}

export function FulfillmentParentEntryCard({
  locationName,
  fulfilledAt,
  receivedLabel,
  returnableLabel,
}: {
  locationName: string;
  fulfilledAt: string | null;
  receivedLabel: string;
  returnableLabel: string;
}) {
  return (
    <Card className="border-emerald-200/80 bg-emerald-50/40 dark:border-emerald-800/40 dark:bg-emerald-950/25">
      <CardHeader title="Returning from this receive" subtitle={formatEntryWhen(fulfilledAt)} />
      <CardBody className="grid gap-3 pt-0 sm:grid-cols-3">
        <QtyMiniStat label="Location" primary={locationName} tone="success" />
        <QtyMiniStat label="Was received" primary={receivedLabel} tone="neutral" />
        <QtyMiniStat label="Can return" primary={returnableLabel} tone="warning" />
      </CardBody>
    </Card>
  );
}
