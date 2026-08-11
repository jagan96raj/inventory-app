import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Briefcase, Calendar, Eye, Plus } from "lucide-react";
import {
  DEFAULT_PAGE_LIMIT,
  jobWorkApi,
  type JobWorkOrder,
} from "../../api/client";
import { searchCustomers } from "../../lib/masterSearch";
import { formatDate, formatQtyKg } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import Select from "../../components/ui/Select";
import AsyncSearchCombobox from "../../components/ui/AsyncSearchCombobox";
import PaginationBar from "../../components/ui/PaginationBar";
import Stat from "../../components/ui/Stat";
import Table, { type Column } from "../../components/ui/Table";
import Skeleton from "../../components/ui/Skeleton";
import { cn } from "../../lib/cn";

function netReceivedKg(order: JobWorkOrder): number {
  let total = 0;
  for (const ln of order.lines) {
    total += Number(ln.net_received_kg ?? ln.custody_kg ?? 0);
  }
  return total;
}

function isVoided(order: JobWorkOrder): boolean {
  return order.status === "cancelled";
}

function groupOrdersByDate(orders: JobWorkOrder[]): { date: string; orders: JobWorkOrder[] }[] {
  const map = new Map<string, JobWorkOrder[]>();
  for (const order of orders) {
    const key = order.job_date || "unknown";
    const list = map.get(key);
    if (list) list.push(order);
    else map.set(key, [order]);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, grouped]) => ({
      date,
      orders: [...grouped].sort((x, y) => y.id - x.id),
    }));
}

type ListMode = "active" | "voided";

export default function JobWorkListPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<JobWorkOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [listMode, setListMode] = useState<ListMode>("active");
  const [customerFilter, setCustomerFilter] = useState<number | null>(null);
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    jobWorkApi
      .list({
        limit,
        offset,
        // Active = omit status (API excludes voided). Voided = status=cancelled only.
        status: listMode === "voided" ? "cancelled" : undefined,
        customer_id: customerFilter ?? undefined,
      })
      .then((page) => {
        // Safety net: active list never shows voided even if API regresses.
        const items =
          listMode === "active"
            ? page.items.filter((o) => o.status !== "cancelled")
            : page.items;
        setRows(items);
        setTotal(page.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [limit, offset, listMode, customerFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [listMode, customerFilter]);

  const ordersByDate = useMemo(() => groupOrdersByDate(rows), [rows]);

  const columns: Column<JobWorkOrder>[] = [
    {
      key: "job_number",
      header: "Job #",
      cell: (r) => (
        <Link to={`/job-work/${r.id}`} className="font-semibold text-primary-700 dark:text-primary-300 v2-mono">
          {r.job_number}
        </Link>
      ),
    },
    {
      key: "customer",
      header: "Customer",
      cell: (r) => r.customer_name ?? `Customer #${r.customer_id}`,
    },
    {
      key: "lines",
      header: "Lines",
      cell: (r) => String(r.lines.length),
      className: "text-right v2-mono",
      headerClassName: "text-right",
    },
    {
      key: "received",
      header: "Received",
      cell: (r) => formatQtyKg(netReceivedKg(r)),
      className: "text-right v2-mono font-medium",
      headerClassName: "text-right",
    },
    {
      key: "actions",
      header: "",
      cell: (r) => (
        <div className="text-right">
          <Link to={`/job-work/${r.id}`}>
            <Button variant="ghost" size="sm" leftIcon={<Eye className="h-4 w-4" />}>
              View
            </Button>
          </Link>
        </div>
      ),
      className: "text-right",
      headerClassName: "text-right",
    },
  ];

  const hasFilters = Boolean(listMode === "voided" || customerFilter != null);

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        eyebrow="Job work"
        title="Job work orders"
        subtitle="Customer material orders for processing — like bills without payment."
        actions={
          <Button
            leftIcon={<Plus className="h-4 w-4" />}
            onClick={() => navigate("/job-work/new")}
            className="hidden sm:inline-flex"
          >
            New order
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <Stat
          label="Orders on page"
          value={rows.length}
          icon={<Briefcase className="h-5 w-5" />}
          tone="primary"
        />
        <Stat label="Total matching" value={total} tone="neutral" />
      </div>

      <Card>
        <CardHeader
          title={listMode === "voided" ? "Voided orders" : "Orders"}
          subtitle={
            listMode === "voided"
              ? "Voided orders only — switch back to Active for normal work."
              : "Grouped by date. Voided orders are hidden unless you select Voided."
          }
          actions={
            hasFilters ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setListMode("active");
                  setCustomerFilter(null);
                }}
              >
                Clear filters
              </Button>
            ) : undefined
          }
        />
        <CardBody className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label="Customer">
              {() => (
                <AsyncSearchCombobox
                  value={customerFilter}
                  onChange={(id) => setCustomerFilter(id)}
                  searchFn={searchCustomers}
                  placeholder="All customers"
                  emptyText="No matching customer"
                />
              )}
            </FormField>
            <FormField label="Show">
              {({ id }) => (
                <Select
                  id={id}
                  value={listMode}
                  onChange={(e) => setListMode(e.target.value as ListMode)}
                >
                  <option value="active">Active</option>
                  <option value="voided">Voided</option>
                </Select>
              )}
            </FormField>
          </div>

          {loading ? (
            <div className="space-y-3" aria-busy="true">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full rounded-xl" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<Briefcase className="h-8 w-8" />}
              title={listMode === "voided" ? "No voided orders" : "No job work orders"}
              description={
                hasFilters
                  ? listMode === "voided"
                    ? "No voided orders match."
                    : "Try clearing filters."
                  : "Create a new order to receive customer material."
              }
              action={
                listMode === "active" ? (
                  <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => navigate("/job-work/new")}>
                    New order
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <>
              <div className="hidden space-y-5 lg:block">
                {ordersByDate.map(({ date, orders: dayOrders }) => {
                  const label = date === "unknown" ? "No job date" : formatDate(date);
                  return (
                    <section key={date} className="space-y-3" aria-labelledby={`jw-date-${date}`}>
                      <header
                        id={`jw-date-${date}`}
                        className="sticky top-0 z-[1] flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/80 bg-surface/95 px-4 py-3 shadow-soft backdrop-blur-sm"
                      >
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                            <Calendar className="h-4 w-4" aria-hidden="true" />
                          </div>
                          <h2 className="text-lg font-bold text-ink">{label}</h2>
                        </div>
                        <span className="text-sm font-medium text-ink-muted">
                          {dayOrders.length} order{dayOrders.length === 1 ? "" : "s"}
                        </span>
                      </header>
                      <Table
                        columns={columns}
                        rows={dayOrders}
                        rowKey={(r) => r.id}
                        caption={`Job work orders · ${label}`}
                      />
                    </section>
                  );
                })}
              </div>
              <div className="space-y-5 lg:hidden">
                {ordersByDate.map(({ date, orders: dayOrders }) => {
                  const label = date === "unknown" ? "No job date" : formatDate(date);
                  return (
                    <section key={date} className="space-y-3" aria-labelledby={`jw-date-m-${date}`}>
                      <header
                        id={`jw-date-m-${date}`}
                        className="sticky top-0 z-[1] flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/80 bg-surface/95 px-4 py-3 shadow-soft backdrop-blur-sm"
                      >
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                            <Calendar className="h-4 w-4" aria-hidden="true" />
                          </div>
                          <h2 className="text-lg font-bold text-ink">{label}</h2>
                        </div>
                        <span className="text-sm font-medium text-ink-muted">
                          {dayOrders.length} order{dayOrders.length === 1 ? "" : "s"}
                        </span>
                      </header>
                      {dayOrders.map((r) => (
                        <div
                          key={r.id}
                          className={cn(
                            "rounded-2xl border border-line/80 p-4",
                            !isVoided(r) && "border-l-4 border-l-primary-500 bg-primary-50/30 dark:bg-primary-950/20",
                            isVoided(r) && "border-l-4 border-l-danger-500 opacity-80"
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <Link
                                to={`/job-work/${r.id}`}
                                className="v2-mono text-lg font-bold text-primary-800 dark:text-primary-200"
                              >
                                {r.job_number}
                              </Link>
                              <p className="mt-0.5 text-base text-ink">{r.customer_name}</p>
                            </div>
                          </div>
                          <p className="mt-3 text-sm text-ink-muted">
                            {r.lines.length} line{r.lines.length === 1 ? "" : "s"} · Received{" "}
                            {formatQtyKg(netReceivedKg(r))}
                          </p>
                          <Link to={`/job-work/${r.id}`} className="mt-3 block">
                            <Button className="w-full" variant="secondary" leftIcon={<Eye className="h-4 w-4" />}>
                              View order
                            </Button>
                          </Link>
                        </div>
                      ))}
                    </section>
                  );
                })}
              </div>
              <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
            </>
          )}
        </CardBody>
      </Card>
      <button
        type="button"
        onClick={() => navigate("/job-work/new")}
        className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
        aria-label="New job work order"
      >
        <Plus className="h-6 w-6" />
      </button>
    </div>
  );
}
