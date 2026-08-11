import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, History, Search, Trash2, Truck } from "lucide-react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  EXPECTED_BILL_VERSION_HEADER,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type FulfillmentAuditEntry,
  type PageOut,
} from "../api/client";
import PageHeader from "../components/ui/PageHeader";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import FormField from "../components/ui/FormField";
import IconButton from "../components/ui/IconButton";
import Input from "../components/ui/Input";
import PaginationBar from "../components/ui/PaginationBar";
import SegmentedControl from "../components/ui/SegmentedControl";
import Select from "../components/ui/Select";
import Table, { type Column } from "../components/ui/Table";
import VoidConfirmDialog from "../components/ui/VoidConfirmDialog";
import { VoidPill } from "../components/ui/StatusPill";
import { toast } from "../components/ui/Toaster";
import { BILL_TYPE_THEME, themeForBillType } from "../lib/billTypeTheme";
import { cn } from "../lib/cn";
import { formatDateTime } from "../lib/format";
import { fulfillmentEntryLabel, fulfillmentQtyLabel } from "../lib/fulfillmentLabels";

type BillTypeFilter = "all" | "purchase" | "sales";
type EntryTypeFilter = "all" | "deliver" | "return";
type StatusFilter = "all" | "active" | "voided";

const AUDIT_THEME = {
  sales: BILL_TYPE_THEME.sales,
  purchase: BILL_TYPE_THEME.purchase,
};

function billDetailPath(row: FulfillmentAuditEntry): string {
  return row.bill_type === "sales" ? `/sales-bills/${row.bill_id}` : `/purchase-bills/${row.bill_id}`;
}

function eventTone(row: FulfillmentAuditEntry): "primary" | "success" | "warning" {
  if (row.entry_type === "return") return "warning";
  return row.bill_type === "sales" ? "primary" : "success";
}

function productMeta(row: FulfillmentAuditEntry): string {
  const parts = [row.brand_name, row.bag_type_name].filter(Boolean);
  if (row.parent_entry_id) parts.push(`Parent #${row.parent_entry_id}`);
  if (row.vehicle_no) parts.push(`Vehicle ${row.vehicle_no}`);
  if (row.notes) parts.push(row.notes);
  if (row.stock_source === "job_work") parts.push("Job work stock");
  return parts.join(" · ");
}

export default function FulfillmentHistoryPage() {
  const [rows, setRows] = useState<FulfillmentAuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [billTypeFilter, setBillTypeFilter] = useState<BillTypeFilter>("all");
  const [entryTypeFilter, setEntryTypeFilter] = useState<EntryTypeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [billNumberQuery, setBillNumberQuery] = useState("");
  const [voidTarget, setVoidTarget] = useState<FulfillmentAuditEntry | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      bill_type: billTypeFilter,
      entry_type: entryTypeFilter,
      status: statusFilter,
    });
    const q = billNumberQuery.trim();
    if (q) params.set("bill_number", q);
    return params.toString();
  }, [limit, offset, billTypeFilter, entryTypeFilter, statusFilter, billNumberQuery]);

  const hasActiveFilters =
    billTypeFilter !== "all" ||
    entryTypeFilter !== "all" ||
    statusFilter !== "all" ||
    Boolean(billNumberQuery.trim());

  const activeFilterTheme =
    billTypeFilter === "purchase"
      ? AUDIT_THEME.purchase
      : billTypeFilter === "sales"
        ? AUDIT_THEME.sales
        : null;

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<FulfillmentAuditEntry>>(`/api/fulfillment/audit?${queryString}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch(() => {
        setRows([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [queryString]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [billTypeFilter, entryTypeFilter, statusFilter, billNumberQuery]);

  const clearFilters = () => {
    setBillTypeFilter("all");
    setEntryTypeFilter("all");
    setStatusFilter("all");
    setBillNumberQuery("");
  };

  const confirmVoid = async (authorizationPassword: string) => {
    if (!voidTarget) return;
    setVoidAuthError("");
    try {
      await api.post(
        `/api/fulfillment/${voidTarget.id}/void`,
        {},
        {
          headers: {
            ...idempotencyVoidAuthHeaders(newIdempotencyKey(), authorizationPassword),
            [EXPECTED_BILL_VERSION_HEADER]: String(voidTarget.bill_version),
          },
        }
      );
      toast.success("Fulfillment entry voided — stock reversed");
      setVoidTarget(null);
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Void failed";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidAuthError(msg);
      } else {
        toast.error(msg);
      }
      throw e;
    }
  };

  const columns: Column<FulfillmentAuditEntry>[] = useMemo(
    () => [
      {
        key: "when",
        header: "Date / time",
        width: "11%",
        cell: (row) => (
          <span
            className={cn(
              "v2-mono whitespace-nowrap text-sm text-ink-muted",
              row.voided_at && "line-through"
            )}
          >
            {formatDateTime(row.fulfilled_at)}
          </span>
        ),
      },
      {
        key: "event",
        header: "Event",
        width: "10%",
        cell: (row) => (
          <Badge tone={eventTone(row)} size="sm">
            {fulfillmentEntryLabel(row.entry_type, row.bill_type)}
          </Badge>
        ),
      },
      {
        key: "bill",
        header: "Bill / party",
        width: "18%",
        cell: (row) => {
          const theme = themeForBillType(row.bill_type);
          return (
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <Badge tone={theme.badgeTone} size="sm" className="shrink-0">
                  {theme.label}
                </Badge>
                <Link
                  to={billDetailPath(row)}
                  className={cn("truncate v2-mono text-sm font-semibold hover:underline", theme.billLink)}
                  title={row.bill_number}
                >
                  {row.bill_number}
                </Link>
              </div>
              <p className="mt-0.5 truncate text-xs text-ink-muted" title={row.customer_name ?? undefined}>
                {row.customer_name ?? "—"}
              </p>
            </div>
          );
        },
      },
      {
        key: "product",
        header: "Product",
        width: "22%",
        cell: (row) => {
          const meta = productMeta(row);
          return (
            <div className="min-w-0">
              <p className="truncate font-medium text-ink" title={row.product_name ?? undefined}>
                {row.product_name ?? "—"}
              </p>
              {meta ? (
                <p className="mt-0.5 truncate text-xs text-ink-muted" title={meta}>
                  {meta}
                </p>
              ) : null}
            </div>
          );
        },
      },
      {
        key: "location",
        header: "Location",
        width: "14%",
        cell: (row) => (
          <span
            className="block truncate text-sm text-ink"
            title={row.location_name ?? row.bill_location_name ?? undefined}
          >
            {row.location_name ?? row.bill_location_name ?? "—"}
          </span>
        ),
      },
      {
        key: "qty",
        header: "Quantity",
        width: "12%",
        numeric: true,
        cell: (row) => (
          <span className={cn("font-semibold", row.voided_at && "line-through")}>
            {fulfillmentQtyLabel(row, row.is_loose)}
          </span>
        ),
      },
      {
        key: "status",
        header: "Status",
        width: "9%",
        cell: (row) =>
          row.voided_at ? (
            <VoidPill when={row.voided_at} />
          ) : (
            <Badge tone="success" size="sm" dot>
              Active
            </Badge>
          ),
      },
      {
        key: "actions",
        header: "",
        align: "right",
        width: "8%",
        cell: (row) =>
          row.voided_at ? (
            <div className="flex justify-end">
              <Link
                to={billDetailPath(row)}
                aria-label="View bill"
                title="View bill"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line-strong text-ink hover:bg-surface-muted"
              >
                <ExternalLink className="h-4 w-4" />
              </Link>
            </div>
          ) : (
            <div className="inline-flex items-center justify-end gap-1">
              <Link
                to={billDetailPath(row)}
                aria-label="View bill"
                title="View bill"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line-strong text-ink hover:bg-surface-muted"
              >
                <ExternalLink className="h-4 w-4" />
              </Link>
              <IconButton
                label="Void entry"
                size="sm"
                onClick={() => setVoidTarget(row)}
                className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:text-rose-400 dark:hover:bg-rose-950/40"
              >
                <Trash2 className="h-4 w-4" />
              </IconButton>
            </div>
          ),
      },
    ],
    []
  );

  return (
    <>
      <PageHeader
        eyebrow="History"
        title="Fulfillment audit log"
        subtitle="Every deliver, receive, and return on sales and purchase bills — including voided entries."
        actions={
          <Link to="/fulfillment">
            <Button variant="secondary" leftIcon={<Truck className="h-4 w-4" />}>
              Open fulfillment
            </Button>
          </Link>
        }
      />

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
              <History className="h-4 w-4" aria-hidden="true" />
              Filters
            </div>
            {hasActiveFilters && (
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
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
                { value: "sales", label: "Sales", hint: "Deliver" },
                { value: "purchase", label: "Purchase", hint: "Receive" },
              ]}
            />
          </FormField>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <FormField label="Event type">
              {({ id }) => (
                <Select
                  id={id}
                  value={entryTypeFilter}
                  onChange={(e) => setEntryTypeFilter(e.target.value as EntryTypeFilter)}
                >
                  <option value="all">All events</option>
                  <option value="deliver">Deliver / Receive</option>
                  <option value="return">Return</option>
                </Select>
              )}
            </FormField>
            <FormField label="Status">
              {({ id }) => (
                <Select id={id} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}>
                  <option value="all">All statuses</option>
                  <option value="active">Active only</option>
                  <option value="voided">Voided only</option>
                </Select>
              )}
            </FormField>
            <FormField label="Bill number" className="sm:col-span-2 lg:col-span-1">
              {({ id }) => (
                <Input
                  id={id}
                  placeholder="e.g. S-000006"
                  value={billNumberQuery}
                  onChange={(e) => setBillNumberQuery(e.target.value)}
                  leftIcon={<Search className="h-4 w-4" />}
                />
              )}
            </FormField>
          </div>
        </CardBody>
      </Card>

      {!loading && rows.length === 0 && total === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              icon={<Truck className="h-8 w-8" />}
              title="No fulfillment events yet"
              description={
                hasActiveFilters
                  ? "No events match the current filters. Try clearing filters or widening the search."
                  : "Deliver sales stock or receive purchase stock to build the audit log."
              }
              action={
                hasActiveFilters ? (
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                ) : (
                  <Link to="/fulfillment">
                    <Button leftIcon={<Truck className="h-4 w-4" />}>Go to fulfillment</Button>
                  </Link>
                )
              }
            />
          </CardBody>
        </Card>
      ) : (
        <>
          <div className="hidden lg:block">
            <Table
              columns={columns}
              rows={rows}
              rowKey={(row) => row.id}
              caption="Fulfillment audit log"
              loading={loading}
              compact
              zebra
              rowClassName={(row) =>
                cn(
                  row.voided_at && "opacity-60",
                  row.bill_type === "sales"
                    ? "border-l-[3px] border-l-primary-400"
                    : "border-l-[3px] border-l-emerald-500"
                )
              }
            />
          </div>

          <div className="space-y-3 lg:hidden">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-28 animate-pulse rounded-2xl bg-surface-muted" />
                ))
              : rows.map((row) => {
                  const theme = themeForBillType(row.bill_type);
                  const meta = productMeta(row);
                  const voided = Boolean(row.voided_at);
                  return (
                    <div
                      key={row.id}
                      className={cn(
                        "rounded-2xl border border-line/80 bg-surface p-4",
                        row.bill_type === "sales"
                          ? "border-l-[3px] border-l-primary-400"
                          : "border-l-[3px] border-l-emerald-500",
                        voided && "opacity-60"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone={eventTone(row)} size="sm">
                              {fulfillmentEntryLabel(row.entry_type, row.bill_type)}
                            </Badge>
                            <Badge tone={theme.badgeTone} size="sm">
                              {theme.label}
                            </Badge>
                          </div>
                          <Link
                            to={billDetailPath(row)}
                            className={cn("mt-2 block truncate v2-mono text-lg font-bold", theme.billLink)}
                          >
                            {row.bill_number}
                          </Link>
                          <p className="truncate text-sm text-ink-muted">{row.customer_name ?? "—"}</p>
                        </div>
                        {voided ? (
                          <VoidPill when={row.voided_at} />
                        ) : (
                          <Badge tone="success" size="sm" dot>
                            Active
                          </Badge>
                        )}
                      </div>
                      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                        <div className="col-span-2">
                          <dt className="text-ink-subtle">Product</dt>
                          <dd className="truncate font-medium text-ink">{row.product_name ?? "—"}</dd>
                          {meta ? <dd className="truncate text-xs text-ink-muted">{meta}</dd> : null}
                        </div>
                        <div>
                          <dt className="text-ink-subtle">When</dt>
                          <dd className={cn("v2-mono text-ink", voided && "line-through")}>
                            {formatDateTime(row.fulfilled_at)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Quantity</dt>
                          <dd className={cn("v2-mono font-semibold text-ink", voided && "line-through")}>
                            {fulfillmentQtyLabel(row, row.is_loose)}
                          </dd>
                        </div>
                        <div className="col-span-2">
                          <dt className="text-ink-subtle">Location</dt>
                          <dd className="truncate text-ink">
                            {row.location_name ?? row.bill_location_name ?? "—"}
                          </dd>
                        </div>
                      </dl>
                      <div className="mt-3 flex gap-2">
                        <Link to={billDetailPath(row)} className="flex-1">
                          <Button className="w-full" variant="secondary" size="sm">
                            View bill
                          </Button>
                        </Link>
                        {!voided ? (
                          <Button className="flex-1" variant="danger" size="sm" onClick={() => setVoidTarget(row)}>
                            Void
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
          </div>

          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="mt-4" />
          <p className="mt-2 text-sm text-ink-subtle">
            {loading
              ? "Loading…"
              : `Showing ${rows.length} of ${total.toLocaleString("en-IN")} event${total === 1 ? "" : "s"} — newest first`}
          </p>
        </>
      )}

      <VoidConfirmDialog
        open={!!voidTarget}
        onClose={() => {
          setVoidTarget(null);
          setVoidAuthError("");
        }}
        title="Void this fulfillment entry?"
        description={
          voidTarget
            ? `Void ${fulfillmentEntryLabel(voidTarget.entry_type, voidTarget.bill_type).toLowerCase()} of ${fulfillmentQtyLabel(voidTarget, voidTarget.is_loose)} on ${voidTarget.bill_number}? Stock will be reversed.`
            : ""
        }
        authError={voidAuthError}
        onConfirm={confirmVoid}
      />
    </>
  );
}
