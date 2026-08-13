import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { History, Calendar, MapPin, PackagePlus, ShoppingCart, Truck } from "lucide-react";
import { api, DEFAULT_PAGE_LIMIT, type PageOut } from "../api/client";
import { formatDate, formatQtyKg } from "../lib/format";
import { cn } from "../lib/cn";
import FulfillmentActionDialog, { type FulfillmentActionMode } from "../components/FulfillmentActionDialog";
import PageHeader from "../components/ui/PageHeader";
import Banner from "../components/ui/Banner";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { DeliveryPill } from "../components/ui/StatusPill";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import SegmentedControl from "../components/ui/SegmentedControl";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import PaginationBar from "../components/ui/PaginationBar";
import Skeleton from "../components/ui/Skeleton";
import { searchBrands, searchProducts } from "../lib/masterSearch";
import {
  deliveryStatusLabel,
  normalizeDeliveryStatus,
  type DeliveryStatusFilter,
} from "../lib/statusLabels";
import { BILL_TYPE_THEME, themeForBillType } from "../lib/billTypeTheme";

type ReturnDeliverEntry = {
  entry_id: number;
  location_id: number;
  location_name: string;
  delivered_kg: string;
  delivered_bags: number;
  returnable_kg: string;
  returnable_bags: number;
  fulfilled_at: string | null;
};

type FulfillmentLine = {
  line_id: number;
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
  return_deliver_entries?: ReturnDeliverEntry[];
};

type FulfillmentBill = {
  bill_id: number;
  bill_number: string;
  bill_date: string;
  bill_type: string;
  customer_name: string;
  location_name?: string | null;
  order_delivery_status: string;
  lines: FulfillmentLine[];
};

type BillTypeFilter = "all" | "purchase" | "sales";
type VisibilityFilter = "actionable" | "all";

const LINE_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-sm font-semibold uppercase tracking-wide text-ink-muted";
const LINE_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

function lineNeedsAction(ln: FulfillmentLine) {  return Number(ln.remaining_kg) > 0 || Number(ln.fulfilled_kg) > 0;
}

function canDeliver(ln: FulfillmentLine) {
  return Number(ln.remaining_kg) > 0;
}

function canReturn(ln: FulfillmentLine, isPurchase: boolean) {
  if (isPurchase) return (ln.return_deliver_entries?.length ?? 0) > 0;
  return Number(ln.fulfilled_kg) > 0;
}

function billNeedsAction(bill: FulfillmentBill) {
  const isPurchase = bill.bill_type === "purchase";
  return bill.lines.some((ln) => canDeliver(ln) || canReturn(ln, isPurchase));
}

function groupBillsByDate(bills: FulfillmentBill[]): { date: string; bills: FulfillmentBill[] }[] {
  const map = new Map<string, FulfillmentBill[]>();
  for (const bill of bills) {
    const key = bill.bill_date || "unknown";
    const list = map.get(key);
    if (list) list.push(bill);
    else map.set(key, [bill]);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, grouped]) => ({ date, bills: grouped }));
}

function progressPct(orderedKg: string, fulfilledKg: string): number {
  const ordered = Number(orderedKg);
  if (ordered <= 0) return 0;
  return Math.min(100, Math.round((Number(fulfilledKg) / ordered) * 100));
}

const FULFILLMENT_THEME = {
  sales: {
    ...BILL_TYPE_THEME.sales,
    progressBar: "bg-primary-500",
    actionBtn: undefined,
    fulfilledHeader: "Delivered",
    icon: ShoppingCart,
  },
  purchase: {
    ...BILL_TYPE_THEME.purchase,
    progressBar: "bg-emerald-500",
    actionBtn: "from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700",
    fulfilledHeader: "Received",
    icon: PackagePlus,
  },
};

function fulfillmentThemeFor(billType: string) {
  return billType === "purchase" ? FULFILLMENT_THEME.purchase : FULFILLMENT_THEME.sales;
}

function QtyCell({
  bags,
  kg,
  isLoose,
  tone = "default",
}: {
  bags?: number;
  kg: string;
  isLoose: boolean;
  tone?: "default" | "remaining";
}) {
  const textClass = tone === "remaining" ? "text-warning-700 dark:text-warning-300" : "text-ink";
  if (isLoose) {
    return <span className={cn("v2-mono", textClass)}>{formatQtyKg(kg)}</span>;
  }
  return (
    <div className="text-right">
      <div className={cn("v2-mono font-medium", textClass)}>{bags} bags</div>
      <div className="text-sm text-ink-subtle v2-mono">{formatQtyKg(kg)}</div>
    </div>
  );
}

function ProgressCell({ ln, billType }: { ln: FulfillmentLine; billType: string }) {
  const pct = progressPct(ln.ordered_kg, ln.fulfilled_kg);
  const theme = fulfillmentThemeFor(billType);
  return (
    <div className="min-w-[7rem] text-right">
      <QtyCell bags={ln.bags_delivered} kg={ln.fulfilled_kg} isLoose={ln.is_loose} />
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={cn("h-full rounded-full transition-all", theme.progressBar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-0.5 text-xs text-ink-subtle">{pct}%</div>
    </div>
  );
}

function LineActions({
  bill,
  line: ln,
  onDeliver,
  onReturn,
}: {
  bill: FulfillmentBill;
  line: FulfillmentLine;
  onDeliver: (lineId: number) => void;
  onReturn: (lineId: number, parentEntryId?: number | null) => void;
}) {
  const isPurchase = bill.bill_type === "purchase";
  const fTheme = fulfillmentThemeFor(bill.bill_type);
  const actionLabel = isPurchase ? "Receive" : "Deliver";

  return (
    <div className="flex w-full flex-wrap justify-stretch gap-2 sm:justify-end sm:gap-1.5">
      {canDeliver(ln) && (
        <Button
          size="sm"
          variant="primary"
          className={cn("min-h-10 flex-1 sm:flex-none", fTheme.actionBtn)}
          onClick={() => onDeliver(ln.line_id)}
        >
          {actionLabel}
        </Button>
      )}
      {canReturn(ln, isPurchase) &&
        (isPurchase && (ln.return_deliver_entries?.length ?? 0) > 1
          ? ln.return_deliver_entries!.map((entry) => (
              <Button
                key={entry.entry_id}
                size="sm"
                variant="outline"
                title={entry.location_name}
                className="min-h-10 min-w-0 flex-1 sm:flex-none"
                onClick={() => onReturn(ln.line_id, entry.entry_id)}
              >
                <span className="truncate">Return ({entry.location_name})</span>
              </Button>
            ))
          : (
            <Button
              size="sm"
              variant="outline"
              className="min-h-10 flex-1 sm:flex-none"
              onClick={() =>
                onReturn(
                  ln.line_id,
                  isPurchase && ln.return_deliver_entries?.[0]
                    ? ln.return_deliver_entries[0].entry_id
                    : null
                )
              }
            >
              Return
            </Button>
          ))}
      {!canDeliver(ln) && !canReturn(ln, isPurchase) && (
        <span className="text-sm text-ink-subtle">—</span>
      )}
    </div>
  );
}

function FulfillmentBillGroup({
  bill,
  visibilityFilter,
  onDeliver,
  onReturn,
}: {
  bill: FulfillmentBill;
  visibilityFilter: VisibilityFilter;
  onDeliver: (lineId: number) => void;
  onReturn: (lineId: number, parentEntryId?: number | null) => void;
}) {
  const theme = themeForBillType(bill.bill_type);
  const isSales = bill.bill_type === "sales";
  const fulfilledHeader = isSales ? "Delivered" : "Received";

  return (
    <section
      className={cn(
        "overflow-hidden rounded-2xl border border-line/80",
        theme.row
      )}
    >
      <header
        className={cn(
          "flex flex-col gap-3 border-b border-line/70 px-5 py-4 sm:flex-row sm:items-start sm:justify-between",
          theme.filterGradient
        )}
      >
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={theme.badgeTone} size="md">
              {theme.label}
            </Badge>
            <span className={cn("v2-mono text-xl font-bold sm:text-2xl", theme.billNumber)}>
              {bill.bill_number}
            </span>
          </div>
          <p className="text-lg font-semibold text-ink">{bill.customer_name}</p>
          {isSales && bill.location_name && (
            <p className="inline-flex items-center gap-1.5 text-sm font-medium text-primary-700 dark:text-primary-300">
              <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
              Billed from {bill.location_name}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:flex-col sm:items-end">
          <DeliveryPill status={bill.order_delivery_status} />
          <span className="text-sm text-ink-muted">
            {bill.lines.length} product line{bill.lines.length === 1 ? "" : "s"}
          </span>
        </div>
      </header>

      <div className="hidden overflow-x-auto bg-surface/50 lg:block">
        <table className="v2-data-table min-w-[48rem] w-full text-base">
          <caption className="sr-only">
            Lines for bill {bill.bill_number}, {bill.customer_name}
          </caption>
          <thead>
            <tr>
              <th scope="col" className={cn(LINE_TH, "text-left")}>
                Product
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Ordered
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                {fulfilledHeader}
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Remaining
              </th>
              <th scope="col" className={cn(LINE_TH, "text-left")}>
                Status
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {bill.lines.map((ln) => {
              const dimmed = visibilityFilter === "actionable" && !lineNeedsAction(ln);
              return (
                <tr
                  key={ln.line_id}
                  className={cn(
                    dimmed && "opacity-60",
                    "bg-surface/80 even:bg-surface-subtle/40"
                  )}
                >
                  <td className={LINE_TD}>
                    <div className="font-semibold text-ink">{ln.product_name}</div>
                    <div className="mt-0.5 text-sm text-ink-muted">
                      {ln.brand_name} · {ln.bag_type_name}
                    </div>
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <QtyCell bags={ln.ordered_bags} kg={ln.ordered_kg} isLoose={ln.is_loose} />
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <ProgressCell ln={ln} billType={bill.bill_type} />
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    {Number(ln.remaining_kg) <= 0 ? (
                      <span className="text-sm text-ink-subtle">Complete</span>
                    ) : (
                      <QtyCell
                        bags={ln.remaining_bags}
                        kg={ln.remaining_kg}
                        isLoose={ln.is_loose}
                        tone="remaining"
                      />
                    )}
                  </td>
                  <td className={LINE_TD}>
                    <DeliveryPill status={ln.line_delivery_status} />
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <LineActions
                      bill={bill}
                      line={ln}
                      onDeliver={onDeliver}
                      onReturn={onReturn}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 bg-surface/50 p-3 lg:hidden">
        {bill.lines.map((ln) => {
          const dimmed = visibilityFilter === "actionable" && !lineNeedsAction(ln);
          return (
            <div
              key={ln.line_id}
              className={cn(
                "space-y-3 rounded-2xl border border-line/80 bg-surface p-4",
                dimmed && "opacity-60"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-ink">{ln.product_name}</p>
                  <p className="mt-0.5 text-sm text-ink-muted">
                    {ln.brand_name} · {ln.bag_type_name}
                  </p>
                </div>
                <DeliveryPill status={ln.line_delivery_status} />
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <div>
                  <dt className="text-ink-subtle">Ordered</dt>
                  <dd>
                    <QtyCell bags={ln.ordered_bags} kg={ln.ordered_kg} isLoose={ln.is_loose} />
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-subtle">{fulfilledHeader}</dt>
                  <dd>
                    <ProgressCell ln={ln} billType={bill.bill_type} />
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-ink-subtle">Remaining</dt>
                  <dd>
                    {Number(ln.remaining_kg) <= 0 ? (
                      <span className="text-sm text-ink-subtle">Complete</span>
                    ) : (
                      <QtyCell
                        bags={ln.remaining_bags}
                        kg={ln.remaining_kg}
                        isLoose={ln.is_loose}
                        tone="remaining"
                      />
                    )}
                  </dd>
                </div>
              </dl>
              <div className="border-t border-line/60 pt-3">
                <LineActions bill={bill} line={ln} onDeliver={onDeliver} onReturn={onReturn} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function FulfillmentDateSection({
  date,
  bills,
  visibilityFilter,
  onDeliver,
  onReturn,
}: {
  date: string;
  bills: FulfillmentBill[];
  visibilityFilter: VisibilityFilter;
  onDeliver: (lineId: number) => void;
  onReturn: (lineId: number, parentEntryId?: number | null) => void;
}) {
  const lineCount = bills.reduce((n, b) => n + b.lines.length, 0);
  const label = date === "unknown" ? "No bill date" : formatDate(date);

  return (
    <section className="space-y-4" aria-labelledby={`fulfillment-date-${date}`}>
      <header
        id={`fulfillment-date-${date}`}
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/80 bg-surface-subtle px-4 py-3 sm:px-5"
      >
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
            <Calendar className="h-4 w-4" aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold text-ink sm:text-xl">{label}</h2>
        </div>
        <span className="text-sm font-medium text-ink-muted">
          {bills.length} bill{bills.length === 1 ? "" : "s"} · {lineCount} line{lineCount === 1 ? "" : "s"}
        </span>
      </header>
      <div className="space-y-4">
        {bills.map((bill) => (
          <FulfillmentBillGroup
            key={bill.bill_id}
            bill={bill}
            visibilityFilter={visibilityFilter}
            onDeliver={onDeliver}
            onReturn={onReturn}
          />
        ))}
      </div>
    </section>
  );
}

export default function FulfillmentPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [billTypeFilter, setBillTypeFilter] = useState<BillTypeFilter>("all");
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>("actionable");
  const [deliveryStatusFilter, setDeliveryStatusFilter] = useState<DeliveryStatusFilter>("all");
  const [productId, setProductId] = useState<number | null>(null);
  const [brandId, setBrandId] = useState<number | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [bills, setBills] = useState<FulfillmentBill[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const limit = DEFAULT_PAGE_LIMIT;
  const [dialog, setDialog] = useState<{
    mode: FulfillmentActionMode;
    lineId: number;
    parentEntryId?: number | null;
  } | null>(null);

  useEffect(() => {
    const action = searchParams.get("action");
    const line = searchParams.get("line");
    const parent = searchParams.get("parent_entry_id");
    if ((action === "deliver" || action === "return") && line) {
      setDialog({
        mode: action,
        lineId: Number(line),
        parentEntryId: parent ? Number(parent) : null,
      });
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      bill_type: billTypeFilter,
      visibility: visibilityFilter,
      tab: "deliver",
      limit: String(limit),
      offset: String(offset),
    });
    if (productId != null) params.set("product_id", String(productId));
    if (brandId != null) params.set("brand_id", String(brandId));
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    return api
      .get<PageOut<FulfillmentBill>>(`/api/fulfillment/bills?${params}`)
      .then((page) => {
        setBills(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [billTypeFilter, visibilityFilter, productId, brandId, dateFrom, dateTo, limit, offset]);

  useEffect(() => {
    setOffset(0);
  }, [billTypeFilter, visibilityFilter, deliveryStatusFilter, productId, brandId, dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  const visibleBills = useMemo(() => {
    if (deliveryStatusFilter === "all") return bills;
    return bills.filter(
      (b) => normalizeDeliveryStatus(b.order_delivery_status) === deliveryStatusFilter
    );
  }, [bills, deliveryStatusFilter]);

  const billsByDate = useMemo(() => groupBillsByDate(visibleBills), [visibleBills]);

  const lineCount = useMemo(
    () => visibleBills.reduce((n, b) => n + b.lines.length, 0),
    [visibleBills]
  );

  const salesLineCount = useMemo(
    () => visibleBills.reduce((n, b) => n + (b.bill_type === "sales" ? b.lines.length : 0), 0),
    [visibleBills]
  );

  const purchaseLineCount = useMemo(
    () => visibleBills.reduce((n, b) => n + (b.bill_type === "purchase" ? b.lines.length : 0), 0),
    [visibleBills]
  );

  const hasDateFilter = Boolean(dateFrom || dateTo);
  const hasExtraFilters =
    visibilityFilter === "actionable" ||
    deliveryStatusFilter !== "all" ||
    productId != null ||
    brandId != null ||
    hasDateFilter;

  const clearFilters = () => {
    setVisibilityFilter("all");
    setDeliveryStatusFilter("all");
    setProductId(null);
    setBrandId(null);
    setDateFrom("");
    setDateTo("");
  };

  const filterLabel = billTypeFilter === "all" ? "" : billTypeFilter === "purchase" ? "purchase " : "sales ";
  const deliveryFilterLabel =
    deliveryStatusFilter === "all" ? "" : `${deliveryStatusLabel(deliveryStatusFilter).toLowerCase()} `;
  const emptyMessage =
    visibilityFilter === "actionable"
      ? `No ${deliveryFilterLabel}${filterLabel}bills with lines awaiting receive, deliver, or return.`
      : `No ${deliveryFilterLabel}${filterLabel}bills to show.`;

  const activeFilterTheme =
    billTypeFilter === "purchase"
      ? FULFILLMENT_THEME.purchase
      : billTypeFilter === "sales"
        ? FULFILLMENT_THEME.sales
        : null;

  const openDeliver = (lineId: number) => setDialog({ mode: "deliver", lineId });
  const openReturn = (lineId: number, parentEntryId?: number | null) =>
    setDialog({ mode: "return", lineId, parentEntryId });

  return (
    <>
      <PageHeader
        title="Fulfillment"
        subtitle="Receive purchase stock and deliver sales stock. All quantities in kg."
        actions={
          <Link to="/histories/fulfillment">
            <Button variant="secondary" leftIcon={<History className="h-4 w-4" />}>
              <span className="sm:hidden">Audit</span>
              <span className="hidden sm:inline">Audit log</span>
            </Button>
          </Link>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card
        className={cn(
          "mb-4 overflow-hidden border-line/80",
          activeFilterTheme?.filterGradient ??
            "bg-gradient-to-br from-primary-50/25 via-surface to-emerald-50/25 dark:from-primary-950/15 dark:via-surface dark:to-emerald-950/15"
        )}
      >
        <CardBody className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div
              className={cn(
                "flex items-center gap-2 text-base font-semibold",
                activeFilterTheme?.filterIcon ?? "text-ink"
              )}
            >
              <Truck className="h-4 w-4" aria-hidden="true" />
              Filters
            </div>
            {billTypeFilter === "all" && !loading && visibleBills.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 text-sm font-medium">
                <span className="inline-flex items-center gap-1.5 text-primary-700 dark:text-primary-300">
                  <span className="h-2.5 w-2.5 rounded-full bg-primary-500" aria-hidden="true" />
                  {salesLineCount} sales line{salesLineCount === 1 ? "" : "s"}
                </span>
                <span className="inline-flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" aria-hidden="true" />
                  {purchaseLineCount} purchase line{purchaseLineCount === 1 ? "" : "s"}
                </span>
              </div>
            )}
          </div>

          <FormField label="Bill type">
            <SegmentedControl
              ariaLabel="Bill type"
              value={billTypeFilter}
              onChange={setBillTypeFilter}
              size="sm"
              className="flex w-full flex-wrap sm:w-auto sm:flex-nowrap [&>button]:min-w-0 [&>button]:flex-1 sm:[&>button]:flex-none"
              options={[
                { value: "all", label: "All", hint: "Both" },
                { value: "purchase", label: "Purchase", hint: "Receive" },
                { value: "sales", label: "Sales", hint: "Deliver" },
              ]}
            />
          </FormField>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Delivery status">
              {({ id }) => (
                <Select
                  id={id}
                  value={deliveryStatusFilter}
                  onChange={(e) => setDeliveryStatusFilter(e.target.value as DeliveryStatusFilter)}
                >
                  <option value="all">All statuses</option>
                  <option value="not_delivered">Not delivered</option>
                  <option value="partial">Partial</option>
                  <option value="delivered">Delivered</option>
                </Select>
              )}
            </FormField>
            <FormField label="Show">
              {({ id }) => (
                <Select
                  id={id}
                  value={visibilityFilter}
                  onChange={(e) => setVisibilityFilter(e.target.value as VisibilityFilter)}
                >
                  <option value="actionable">Bills needing action</option>
                  <option value="all">All bills</option>
                </Select>
              )}
            </FormField>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Product">
              {() => (
                <AsyncSearchCombobox
                  value={productId}
                  onChange={setProductId}
                  searchFn={searchProducts}
                  placeholder="All products"
                  emptyText="No matching product"
                />
              )}
            </FormField>
            <FormField label="Brand">
              {() => (
                <AsyncSearchCombobox
                  value={brandId}
                  onChange={setBrandId}
                  searchFn={searchBrands}
                  placeholder="All brands"
                  emptyText="No matching brand"
                />
              )}
            </FormField>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Bill date from">
              {({ id }) => (
                <Input
                  id={id}
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              )}
            </FormField>
            <FormField label="Bill date to">
              {({ id }) => (
                <Input
                  id={id}
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              )}
            </FormField>
          </div>

          {hasExtraFilters && (
            <div className="flex justify-end">
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            </div>
          )}
        </CardBody>
      </Card>

      {!loading && visibleBills.length > 0 && billTypeFilter === "all" && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Card className={cn("border-line/80", FULFILLMENT_THEME.sales.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4 sm:p-5">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                <ShoppingCart className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-medium text-primary-700/80 dark:text-primary-300/80">Sales lines</p>
                <p className="text-2xl font-bold text-primary-800 dark:text-primary-100">{salesLineCount}</p>
                <p className="text-sm text-ink-muted">Deliver to customers</p>
              </div>
            </CardBody>
          </Card>
          <Card className={cn("border-line/80", FULFILLMENT_THEME.purchase.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4 sm:p-5">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200">
                <PackagePlus className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-medium text-emerald-800/80 dark:text-emerald-300/80">Purchase lines</p>
                <p className="text-2xl font-bold text-emerald-900 dark:text-emerald-100">{purchaseLineCount}</p>
                <p className="text-sm text-ink-muted">Receive from suppliers</p>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      <Card
        className={cn(
          "overflow-hidden border-line/80",
          activeFilterTheme?.filterGradient
        )}
      >
        <CardHeader
          title="Bills"
          subtitle={
            billTypeFilter === "all"
              ? "Grouped by bill date — product lines listed under each bill."
              : billTypeFilter === "sales"
                ? "Sales bills by date — deliver stock to customers."
                : "Purchase bills by date — receive stock from suppliers."
          }
        />
        <CardBody className="space-y-5 pt-0">
          {loading ? (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-48 w-full rounded-2xl" />
              ))}
            </div>
          ) : visibleBills.length === 0 ? (
            <EmptyState
              title="No fulfillment bills"
              description={emptyMessage}
              action={
                hasExtraFilters ? (
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <>
              <div className="space-y-8">
                {billsByDate.map(({ date, bills: dateBills }) => (
                  <FulfillmentDateSection
                    key={date}
                    date={date}
                    bills={dateBills}
                    visibilityFilter={visibilityFilter}
                    onDeliver={openDeliver}
                    onReturn={openReturn}
                  />
                ))}
              </div>
              <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
              <p className="text-sm text-ink-subtle">
                {visibleBills.length} bill{visibleBills.length === 1 ? "" : "s"}, {lineCount} product line
                {lineCount === 1 ? "" : "s"}
              </p>
            </>
          )}
        </CardBody>
      </Card>
      <FulfillmentActionDialog
        open={dialog != null}
        mode={dialog?.mode ?? null}
        lineId={dialog?.lineId ?? null}
        parentEntryId={dialog?.parentEntryId}
        onClose={() => setDialog(null)}
        onSuccess={load}
      />
    </>
  );
}
