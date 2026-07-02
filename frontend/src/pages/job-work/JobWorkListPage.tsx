import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Briefcase, Eye, Plus } from "lucide-react";
import {
  DEFAULT_PAGE_LIMIT,
  jobWorkApi,
  type JobWorkOrder,
} from "../../api/client";
import { searchCustomers } from "../../lib/masterSearch";
import { formatDate, formatQtyKg } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
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

function statusTone(status: string): "primary" | "success" | "muted" | "danger" {
  if (status === "open") return "primary";
  if (status === "completed") return "success";
  if (status === "cancelled") return "danger";
  return "muted";
}

function statusLabel(status: string): string {
  if (status === "open") return "Open";
  if (status === "completed") return "Completed";
  if (status === "cancelled") return "Voided";
  return status;
}

function outstandingKg(order: JobWorkOrder): number {
  let total = 0;
  for (const ln of order.lines) {
    total += Number(ln.received_quantity_kg) - Number(ln.returned_quantity_kg);
  }
  return total;
}

export default function JobWorkListPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<JobWorkOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [customerFilter, setCustomerFilter] = useState<number | null>(null);
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    jobWorkApi
      .list({
        limit,
        offset,
        status: statusFilter ? (statusFilter as "open" | "completed" | "cancelled") : undefined,
        customer_id: customerFilter ?? undefined,
      })
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [limit, offset, statusFilter, customerFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [statusFilter, customerFilter]);

  const openCount = useMemo(() => rows.filter((r) => r.status === "open").length, [rows]);

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
      key: "job_date",
      header: "Date",
      cell: (r) => <span className="v2-mono">{formatDate(r.job_date)}</span>,
    },
    {
      key: "lines",
      header: "Lines",
      cell: (r) => String(r.lines.length),
      className: "text-right v2-mono",
      headerClassName: "text-right",
    },
    {
      key: "custody",
      header: "In custody",
      cell: (r) => formatQtyKg(outstandingKg(r)),
      className: "text-right v2-mono font-medium",
      headerClassName: "text-right",
    },
    {
      key: "status",
      header: "Status",
      cell: (r) => <Badge tone={statusTone(r.status)} size="sm">{statusLabel(r.status)}</Badge>,
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

  const hasFilters = Boolean(statusFilter || customerFilter != null);

  return (
    <>
      <PageHeader
        eyebrow="Job work"
        title="Job work orders"
        subtitle="Customer material received for processing. Track custody, receipts, and returns."
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => navigate("/job-work/new")}>
            New order
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat
          label="Orders on page"
          value={rows.length}
          icon={<Briefcase className="h-5 w-5" />}
          tone="primary"
        />
        <Stat
          label="Open on page"
          value={openCount}
          tone="info"
        />
        <Stat
          label="Total matching"
          value={total}
          tone="neutral"
        />
      </div>

      <Card>
        <CardHeader
          title="All orders"
          subtitle="Filter by customer or status."
          actions={
            hasFilters ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setStatusFilter("");
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
            <FormField label="Status">
              {({ id }) => (
                <Select id={id} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                  <option value="">All statuses</option>
                  <option value="open">Open</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Voided</option>
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
              title="No job work orders"
              description={hasFilters ? "Try clearing filters." : "Create a new order to receive customer material."}
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => navigate("/job-work/new")}>
                  New order
                </Button>
              }
            />
          ) : (
            <>
              <div className="hidden md:block">
                <Table columns={columns} rows={rows} rowKey={(r) => r.id} caption="Job work orders" />
              </div>
              <div className="space-y-3 md:hidden">
                {rows.map((r) => (
                  <div
                    key={r.id}
                    className={cn(
                      "rounded-2xl border border-line/80 p-4",
                      r.status === "open" && "border-l-4 border-l-primary-500 bg-primary-50/30 dark:bg-primary-950/20"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link to={`/job-work/${r.id}`} className="v2-mono text-lg font-bold text-primary-800 dark:text-primary-200">
                          {r.job_number}
                        </Link>
                        <p className="mt-0.5 text-base text-ink">{r.customer_name}</p>
                        <p className="mt-1 text-sm text-ink-muted">{formatDate(r.job_date)}</p>
                      </div>
                      <Badge tone={statusTone(r.status)}>{statusLabel(r.status)}</Badge>
                    </div>
                    <p className="mt-3 text-sm text-ink-muted">
                      {r.lines.length} line{r.lines.length === 1 ? "" : "s"} · In custody {formatQtyKg(outstandingKg(r))}
                    </p>
                    <Link to={`/job-work/${r.id}`} className="mt-3 block">
                      <Button className="w-full" variant="secondary" leftIcon={<Eye className="h-4 w-4" />}>
                        View order
                      </Button>
                    </Link>
                  </div>
                ))}
              </div>
              <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
            </>
          )}
        </CardBody>
      </Card>
    </>
  );
}
