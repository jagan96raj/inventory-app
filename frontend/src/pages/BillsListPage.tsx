import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Calendar,
  Eye,
  FileText,
  Filter,
  IndianRupee,
  PackagePlus,
  Pencil,
  Plus,
  Search,
  ShoppingCart,
  Truck,
  UserPlus,
  X,
} from "lucide-react";
import { api, DEFAULT_PAGE_LIMIT, type BillListItem, type BillsPage } from "../api/client";
import { billDueAmount } from "../lib/billAmounts";
import { formatDate, formatInr } from "../lib/format";
import { searchProducts } from "../lib/masterSearch";
import {
  deliveryStatusLabel,
  normalizeDeliveryStatus,
  normalizePaymentStatus,
  type DeliveryStatusFilter,
  type PaymentStatusFilter,
} from "../lib/statusLabels";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import IconButton from "../components/ui/IconButton";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import FormField from "../components/ui/FormField";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import Table, { type Column } from "../components/ui/Table";
import Badge from "../components/ui/Badge";
import { PaymentPill } from "../components/ui/StatusPill";
import EmptyState from "../components/ui/EmptyState";
import Banner from "../components/ui/Banner";
import SegmentedControl from "../components/ui/SegmentedControl";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import AddCustomerDialog from "../components/AddCustomerDialog";
import BillNotesHover from "../components/bills/BillNotesHover";
import PaginationBar from "../components/ui/PaginationBar";
import { cn } from "../lib/cn";

function groupBillsByDate(bills: BillListItem[]): { date: string; bills: BillListItem[] }[] {
  const map = new Map<string, BillListItem[]>();
  for (const bill of bills) {
    const key = bill.bill_date || "unknown";
    const list = map.get(key);
    if (list) list.push(bill);
    else map.set(key, [bill]);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, grouped]) => ({
      date,
      bills: [...grouped].sort((x, y) => y.id - x.id),
    }));
}

function fulfillmentLabel(status: string, isSales: boolean): string {
  const norm = normalizeDeliveryStatus(status);
  if (isSales) return deliveryStatusLabel(norm);
  if (norm === "not_delivered") return "Not received";
  if (norm === "delivered") return "Received";
  if (norm === "partial") return "Partial";
  return status;
}

function fulfillmentTone(status: string): "success" | "warning" | "muted" {
  const norm = normalizeDeliveryStatus(status);
  if (norm === "delivered") return "success";
  if (norm === "partial") return "warning";
  return "muted";
}

const PAGE_THEME = {
  sales: {
    filterGradient:
      "bg-gradient-to-br from-primary-50/50 via-surface to-violet-50/35 dark:from-primary-950/30 dark:via-surface dark:to-violet-950/20",
    filterIcon: "text-primary-600 dark:text-primary-300",
    tableHeader: "text-indigo-700/90 dark:text-indigo-200/90",
    billLink: "text-primary-700 dark:text-primary-300",
    fab: "from-primary-500 to-primary-700",
    partyLabel: "Customer",
    fulfillmentLabel: "Delivery",
    fulfillmentFilterLabel: "Delivery status",
    fulfillmentAll: "All deliveries",
    fulfillmentNot: "Not delivered",
    fulfillmentDone: "Delivered",
    emptyIcon: ShoppingCart,
    statTone: "primary" as const,
  },
  purchase: {
    filterGradient:
      "bg-gradient-to-br from-emerald-50/55 via-surface to-teal-50/40 dark:from-emerald-950/30 dark:via-surface dark:to-teal-950/25",
    filterIcon: "text-emerald-600 dark:text-emerald-300",
    tableHeader: "text-emerald-800/90 dark:text-emerald-200/90",
    billLink: "text-emerald-800 dark:text-emerald-300",
    fab: "from-emerald-500 to-teal-600",
    partyLabel: "Supplier",
    fulfillmentLabel: "Receiving",
    fulfillmentFilterLabel: "Receiving status",
    fulfillmentAll: "All receiving",
    fulfillmentNot: "Not received",
    fulfillmentDone: "Received",
    emptyIcon: PackagePlus,
    statTone: "success" as const,
  },
};

function BillActions({
  due,
  onView,
  onEdit,
  onPay,
}: {
  due: number;
  onView: () => void;
  onEdit: () => void;
  onPay: () => void;
}) {
  return (
    <div className="inline-flex items-center justify-end gap-0.5">
      <IconButton label="View bill" size="sm" onClick={onView}>
        <Eye />
      </IconButton>
      <IconButton label="Edit bill" size="sm" variant="outline" onClick={onEdit}>
        <Pencil />
      </IconButton>
      {due > 0 && (
        <IconButton label="Record payment" size="sm" variant="primary" onClick={onPay}>
          <IndianRupee />
        </IconButton>
      )}
    </div>
  );
}

function BillMobileCard({
  bill,
  base,
  theme,
  isSales,
  onView,
  onEdit,
  onPay,
}: {
  bill: BillListItem;
  base: string;
  theme: (typeof PAGE_THEME)["sales"];
  isSales: boolean;
  onView: () => void;
  onEdit: () => void;
  onPay: () => void;
}) {
  const due = billDueAmount(bill);
  const final = bill.final_payable ?? bill.grand_total;

  return (
    <Card className="overflow-hidden border-line/80 transition-shadow hover:shadow-soft">
      <CardBody className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <BillNotesHover notes={bill.notes}>
              <Link
                to={`${base}/${bill.id}`}
                className={cn("text-lg font-bold v2-mono hover:underline", theme.billLink)}
              >
                {bill.bill_number}
              </Link>
            </BillNotesHover>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold v2-mono text-ink">{formatInr(final)}</p>
            {due > 0 && (
              <p className="text-sm font-semibold text-danger-600 dark:text-danger-300 v2-mono">
                Due {formatInr(due)}
              </p>
            )}
          </div>
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">{theme.partyLabel}</p>
          <p className="truncate font-medium text-ink">{bill.customer_name ?? "—"}</p>
          {isSales && bill.location_name && (
            <p className="truncate text-sm text-ink-muted">{bill.location_name}</p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <PaymentPill status={bill.payment_status} />
          <Badge tone={fulfillmentTone(bill.order_delivery_status)} dot size="sm">
            {fulfillmentLabel(bill.order_delivery_status, isSales)}
          </Badge>
        </div>

        <div className="flex items-center justify-end gap-1 border-t border-line/70 pt-3">
          <BillActions due={due} onView={onView} onEdit={onEdit} onPay={onPay} />
        </div>
      </CardBody>
    </Card>
  );
}

export default function BillsListPage({ billType }: { billType: "sales" | "purchase" }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<BillListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [summary, setSummary] = useState<BillsPage["summary"] | null>(null);
  const [paymentStatusFilter, setPaymentStatusFilter] = useState<PaymentStatusFilter>("all");
  const [deliveryStatusFilter, setDeliveryStatusFilter] = useState<DeliveryStatusFilter>("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [productId, setProductId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [addCustomerOpen, setAddCustomerOpen] = useState(false);
  const limit = DEFAULT_PAGE_LIMIT;
  const base = billType === "sales" ? "/sales-bills" : "/purchase-bills";
  const isSales = billType === "sales";
  const theme = PAGE_THEME[billType];
  const EmptyIcon = theme.emptyIcon;

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(t);
  }, [search]);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      bill_type: billType,
      limit: String(limit),
      offset: String(offset),
    });
    if (paymentStatusFilter !== "all") params.set("payment_status", paymentStatusFilter);
    if (deliveryStatusFilter !== "all") params.set("delivery_status", deliveryStatusFilter);
    if (debouncedSearch) params.set("search", debouncedSearch);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (productId != null) params.set("product_id", String(productId));
    api
      .get<BillsPage>(`/api/bills?${params}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
        setSummary(page.summary);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [billType, limit, offset, paymentStatusFilter, deliveryStatusFilter, debouncedSearch, dateFrom, dateTo, productId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [billType, paymentStatusFilter, deliveryStatusFilter, debouncedSearch, dateFrom, dateTo, productId]);

  const finalPayable = (b: BillListItem) => b.final_payable ?? b.grand_total;

  const stats = useMemo(() => {
    if (!summary) return { total: 0, unpaid: 0, totalDue: 0, pendingReceive: 0 };
    return {
      total: summary.total_count,
      unpaid: summary.unpaid_count,
      totalDue: Number(summary.total_due),
      pendingReceive: summary.pending_delivery_count,
    };
  }, [summary]);

  const hasActiveFilters =
    paymentStatusFilter !== "all" ||
    deliveryStatusFilter !== "all" ||
    search.trim() !== "" ||
    dateFrom !== "" ||
    dateTo !== "" ||
    productId != null;

  const clearFilters = () => {
    setPaymentStatusFilter("all");
    setDeliveryStatusFilter("all");
    setSearch("");
    setDebouncedSearch("");
    setDateFrom("");
    setDateTo("");
    setProductId(null);
  };

  const columns: Column<BillListItem>[] = [
    {
      key: "bill",
      header: "Bill",
      width: "11rem",
      cell: (b) => (
        <BillNotesHover notes={b.notes}>
          <Link
            to={`${base}/${b.id}`}
            className={cn("font-semibold v2-mono hover:underline", theme.billLink)}
          >
            {b.bill_number}
          </Link>
        </BillNotesHover>
      ),
    },
    {
      key: "party",
      header: theme.partyLabel,
      width: "14rem",
      cell: (b) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{b.customer_name ?? "—"}</p>
          {isSales && b.location_name && (
            <p className="truncate text-sm text-ink-subtle">{b.location_name}</p>
          )}
        </div>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      width: "9rem",
      align: "right",
      numeric: true,
      cell: (b) => {
        const due = billDueAmount(b);
        return (
          <div className="text-right">
            <p className="font-semibold v2-mono text-ink">{formatInr(finalPayable(b))}</p>
            {due > 0 ? (
              <p className="mt-0.5 text-sm font-medium text-danger-600 dark:text-danger-300 v2-mono">
                Due {formatInr(due)}
              </p>
            ) : (
              <p className="mt-0.5 text-sm text-ink-subtle">Paid</p>
            )}
          </div>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      width: "11rem",
      cell: (b) => (
        <div className="flex flex-col items-start gap-1.5">
          <PaymentPill status={b.payment_status} />
          <Badge tone={fulfillmentTone(b.order_delivery_status)} dot size="sm">
            {fulfillmentLabel(b.order_delivery_status, isSales)}
          </Badge>
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      width: "7.5rem",
      align: "right",
      cell: (b) => {
        const due = billDueAmount(b);
        return (
          <BillActions
            due={due}
            onView={() => navigate(`${base}/${b.id}`)}
            onEdit={() => navigate(`${base}/${b.id}/edit`)}
            onPay={() => navigate(`${base}/${b.id}/payment`)}
          />
        );
      },
    },
  ];

  const billsByDate = useMemo(() => groupBillsByDate(rows), [rows]);

  const showToolbar = !loading;

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        eyebrow={isSales ? "Outbound" : "Inbound"}
        title={`${isSales ? "Sales" : "Purchase"} bills`}
        subtitle={
          isSales
            ? "Track outbound sales to customers — payments and delivery in one place."
            : "Track inbound purchases from suppliers — payments and receiving in one place."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              leftIcon={<UserPlus className="h-4 w-4" />}
              onClick={() => setAddCustomerOpen(true)}
            >
              {isSales ? "Add customer" : "Add supplier"}
            </Button>
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => navigate(`${base}/new`)}>
              New bill
            </Button>
          </div>
        }
      />

      {error && (
        <Banner tone="danger" title="Couldn’t load bills" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {showToolbar && (total > 0 || hasActiveFilters) && (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Card className={cn("border-line/80", theme.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4">
              <div
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-surface/80 shadow-sm",
                  theme.filterIcon
                )}
              >
                <FileText className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">Total bills</p>
                <p className="text-2xl font-bold tabular-nums text-ink">{stats.total}</p>
              </div>
            </CardBody>
          </Card>
          <Card className={cn("border-line/80", theme.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-warning-100 text-warning-700 dark:bg-warning-950/50 dark:text-warning-300">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">Unpaid / partial</p>
                <p className="text-2xl font-bold tabular-nums text-ink">{stats.unpaid}</p>
              </div>
            </CardBody>
          </Card>
          <Card className={cn("border-line/80", theme.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-danger-100 text-danger-700 dark:bg-danger-950/50 dark:text-danger-300">
                <IndianRupee className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">Total due</p>
                <p className="text-xl font-bold v2-mono text-ink sm:text-2xl">{formatInr(stats.totalDue)}</p>
              </div>
            </CardBody>
          </Card>
          <Card className={cn("border-line/80", theme.filterGradient)}>
            <CardBody className="flex items-center gap-3 p-4">
              <div
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-surface/80",
                  isSales ? "text-violet-600 dark:text-violet-300" : "text-teal-600 dark:text-teal-300"
                )}
              >
                <Truck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">
                  Pending {isSales ? "delivery" : "receiving"}
                </p>
                <p className="text-2xl font-bold tabular-nums text-ink">{stats.pendingReceive}</p>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {showToolbar && (
        <Card className={cn("mb-5 overflow-hidden border-line/80", theme.filterGradient)}>
          <CardBody className="space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className={cn("flex items-center gap-2 text-sm font-semibold", theme.filterIcon)}>
                <Filter className="h-4 w-4" aria-hidden="true" />
                Search &amp; filters
              </div>
              {total > 0 && (
                <p className="text-sm text-ink-muted">
                  Showing <span className="font-semibold text-ink">{rows.length}</span> of{" "}
                  <span className="font-semibold text-ink">{total}</span>
                </p>
              )}
            </div>
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)] lg:items-end">
              <FormField label="Search" htmlFor="bills-search">
                {({ id }) => (
                  <Input
                    id={id}
                    placeholder={
                      isSales
                        ? "Bill number or customer…"
                        : "Bill number or supplier…"
                    }
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    leftIcon={<Search />}
                  />
                )}
              </FormField>
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
                <div className="min-w-0 w-full flex-1 space-y-1.5">
                  <p className="text-sm font-medium text-ink-muted">Payment</p>
                  <SegmentedControl
                    ariaLabel="Payment status"
                    value={paymentStatusFilter}
                    onChange={(v) => setPaymentStatusFilter(v)}
                    size="sm"
                    className="flex w-full flex-wrap sm:w-auto sm:flex-nowrap [&>button]:min-w-0 [&>button]:flex-1 sm:[&>button]:flex-none"
                    options={[
                      { value: "all", label: "All" },
                      { value: "unpaid", label: "Unpaid" },
                      { value: "partial", label: "Partial" },
                      { value: "paid", label: "Paid" },
                    ]}
                  />
                </div>
                <FormField label={theme.fulfillmentFilterLabel} htmlFor="bills-fulfillment" className="min-w-0 w-full sm:min-w-[12rem] sm:w-auto">
                  {({ id }) => (
                    <Select
                      id={id}
                      value={deliveryStatusFilter}
                      onChange={(e) => setDeliveryStatusFilter(e.target.value as DeliveryStatusFilter)}
                    >
                      <option value="all">{theme.fulfillmentAll}</option>
                      <option value="not_delivered">{theme.fulfillmentNot}</option>
                      <option value="partial">Partial</option>
                      <option value="delivered">{theme.fulfillmentDone}</option>
                    </Select>
                  )}
                </FormField>
                {hasActiveFilters && (
                  <Button
                    size="md"
                    variant="ghost"
                    leftIcon={<X className="h-4 w-4" />}
                    onClick={clearFilters}
                    className="sm:mb-0.5"
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <FormField label="Product">
                {() => (
                  <AsyncSearchCombobox
                    value={productId}
                    onChange={(id) => setProductId(id)}
                    searchFn={searchProducts}
                    placeholder="All products"
                    emptyText="No matching product"
                  />
                )}
              </FormField>
              <FormField label="Date from" htmlFor="bills-date-from">
                {({ id }) => (
                  <Input
                    id={id}
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                )}
              </FormField>
              <FormField label="Date to" htmlFor="bills-date-to">
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
          </CardBody>
        </Card>
      )}

      {loading || total > 0 ? (
        rows.length === 0 && !loading ? (
          <EmptyState
            icon={<EmptyIcon />}
            title="No bills match your filters"
            description="Try clearing the filters to see all bills."
            action={
              <Button variant="secondary" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <>
            <div className="space-y-5 lg:hidden">
              {loading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <Card key={i} className="h-36 animate-pulse border-line/80 bg-surface-muted/50" />
                  ))
                : billsByDate.map(({ date, bills: dayBills }) => {
                    const label = date === "unknown" ? "No bill date" : formatDate(date);
                    return (
                      <section key={date} className="space-y-3" aria-labelledby={`bills-date-m-${date}`}>
                        <header
                          id={`bills-date-m-${date}`}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/80 bg-surface-muted/80 px-4 py-3"
                        >
                          <div className="flex items-center gap-2.5">
                            <div
                              className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-lg",
                                isSales
                                  ? "bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200"
                                  : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200"
                              )}
                            >
                              <Calendar className="h-4 w-4" aria-hidden="true" />
                            </div>
                            <h2 className="text-lg font-bold text-ink">{label}</h2>
                          </div>
                          <span className="text-sm font-medium text-ink-muted">
                            {dayBills.length} bill{dayBills.length === 1 ? "" : "s"}
                          </span>
                        </header>
                        {dayBills.map((b) => (
                          <BillMobileCard
                            key={b.id}
                            bill={b}
                            base={base}
                            theme={theme}
                            isSales={isSales}
                            onView={() => navigate(`${base}/${b.id}`)}
                            onEdit={() => navigate(`${base}/${b.id}/edit`)}
                            onPay={() => navigate(`${base}/${b.id}/payment`)}
                          />
                        ))}
                      </section>
                    );
                  })}
            </div>
            <PaginationBar
              className="px-1 lg:hidden"
              total={total}
              limit={limit}
              offset={offset}
              onPageChange={setOffset}
            />

            <Card className={cn("hidden border-line/80 lg:block", theme.filterGradient)}>
              <CardHeader
                title={isSales ? "Sales bills" : "Purchase bills"}
                subtitle={
                  loading
                    ? "Loading…"
                    : `${rows.length} bill${rows.length === 1 ? "" : "s"} on this page · grouped by date`
                }
              />
              <CardBody className="space-y-8 p-4 pt-0 sm:p-5">
                {loading ? (
                  <Table
                    columns={columns}
                    rows={[]}
                    rowKey={(b) => b.id}
                    loading
                    zebra
                    stickyHeader={false}
                    headerClassName={theme.tableHeader}
                    className="rounded-2xl border-line/80"
                    caption={`${isSales ? "Sales" : "Purchase"} bills`}
                  />
                ) : (
                  billsByDate.map(({ date, bills: dayBills }) => {
                    const label = date === "unknown" ? "No bill date" : formatDate(date);
                    return (
                      <section key={date} className="space-y-3" aria-labelledby={`bills-date-${date}`}>
                        <header
                          id={`bills-date-${date}`}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/80 bg-surface-muted/80 px-4 py-3 sm:px-5"
                        >
                          <div className="flex items-center gap-2.5">
                            <div
                              className={cn(
                                "flex h-9 w-9 items-center justify-center rounded-lg",
                                isSales
                                  ? "bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200"
                                  : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200"
                              )}
                            >
                              <Calendar className="h-4 w-4" aria-hidden="true" />
                            </div>
                            <h2 className="text-lg font-bold text-ink sm:text-xl">{label}</h2>
                          </div>
                          <span className="text-sm font-medium text-ink-muted">
                            {dayBills.length} bill{dayBills.length === 1 ? "" : "s"}
                          </span>
                        </header>
                        <Table
                          columns={columns}
                          rows={dayBills}
                          rowKey={(b) => b.id}
                          zebra
                          stickyHeader={false}
                          headerClassName={theme.tableHeader}
                          className="rounded-2xl border-line/80 bg-surface/60"
                          caption={`${isSales ? "Sales" : "Purchase"} bills for ${label}`}
                        />
                      </section>
                    );
                  })
                )}
                <div className="border-t border-line/70 px-1">
                  <PaginationBar
                    total={total}
                    limit={limit}
                    offset={offset}
                    onPageChange={setOffset}
                  />
                </div>
              </CardBody>
            </Card>
          </>
        )
      ) : (
        <EmptyState
          icon={<EmptyIcon />}
          title={`No ${isSales ? "sales" : "purchase"} bills yet`}
          description={
            isSales
              ? "Add a customer or create your first bill — stock moves on fulfillment, not on submit."
              : "Add a supplier or create your first purchase bill — stock is added when you receive on fulfillment."
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                variant="secondary"
                leftIcon={<UserPlus className="h-4 w-4" />}
                onClick={() => setAddCustomerOpen(true)}
              >
                {isSales ? "Add customer" : "Add supplier"}
              </Button>
              <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => navigate(`${base}/new`)}>
                Create first bill
              </Button>
            </div>
          }
        />
      )}

      <AddCustomerDialog open={addCustomerOpen} onClose={() => setAddCustomerOpen(false)} onCreated={() => undefined} />

      <Link
        to={`${base}/new`}
        className={cn(
          "fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden",
          theme.fab
        )}
        aria-label="Create new bill"
      >
        <Plus className="h-6 w-6" />
      </Link>
    </div>
  );
}
