import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Briefcase, Calendar, PackagePlus, Undo2 } from "lucide-react";
import {
  DEFAULT_PAGE_LIMIT,
  jobWorkApi,
  jobWorkFulfillmentApi,
  newIdempotencyKey,
  type JobWorkFulfillmentLine,
  type JobWorkFulfillmentOrder,
  type JobWorkFulfillmentReceipt,
} from "../../api/client";
import JobWorkFulfillmentActionDialog, {
  type JobWorkFulfillmentMode,
} from "../../components/JobWorkFulfillmentActionDialog";
import JwActivityLog from "../../components/job-work/JwActivityLog";
import JwQtyCell from "../../components/JwQtyCell";
import PageHeader from "../../components/ui/PageHeader";
import Banner from "../../components/ui/Banner";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import SegmentedControl from "../../components/ui/SegmentedControl";
import EmptyState from "../../components/ui/EmptyState";
import PaginationBar from "../../components/ui/PaginationBar";
import Skeleton from "../../components/ui/Skeleton";
import VoidConfirmDialog from "../../components/ui/VoidConfirmDialog";
import { formatDate } from "../../lib/format";
import {
  jwNetReceivedQty,
  jwOrderedQty,
  jwRemainingReceiveQty,
} from "../../lib/jwQty";
import { cn } from "../../lib/cn";
import { toast } from "../../components/ui/Toaster";

type Visibility = "actionable" | "all";

const REMAINING_HELP =
  "Remaining = ordered − total receive events + total returns (returns reopen receive allowance).";

const LINE_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-sm font-semibold uppercase tracking-wide text-ink-muted";
const LINE_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

function groupOrdersByDate(
  orders: JobWorkFulfillmentOrder[]
): { date: string; orders: JobWorkFulfillmentOrder[] }[] {
  const map = new Map<string, JobWorkFulfillmentOrder[]>();
  for (const order of orders) {
    const key = order.job_date || "unknown";
    const list = map.get(key);
    if (list) list.push(order);
    else map.set(key, [order]);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, grouped]) => ({ date, orders: grouped }));
}

function canReceive(ln: JobWorkFulfillmentLine): boolean {
  const remaining = jwRemainingReceiveQty(ln);
  if (ln.is_loose) return Number(remaining.loose_kg ?? remaining.kg ?? 0) > 0;
  return (remaining.bags ?? 0) > 0 || Number(remaining.kg ?? 0) > 0;
}

function canReturn(ln: JobWorkFulfillmentLine): boolean {
  const net = jwNetReceivedQty(ln);
  if (ln.is_loose) return Number(net.loose_kg ?? net.kg ?? 0) > 0;
  return (net.bags ?? 0) > 0 || Number(net.kg ?? 0) > 0;
}

function lineNeedsAction(ln: JobWorkFulfillmentLine): boolean {
  return canReceive(ln) || canReturn(ln);
}

function remainingIsZero(ln: JobWorkFulfillmentLine): boolean {
  return !canReceive(ln);
}

function LineActions({
  ln,
  onReceive,
  onReturn,
}: {
  ln: JobWorkFulfillmentLine;
  onReceive: () => void;
  onReturn: () => void;
}) {
  return (
    <div className="flex w-full flex-wrap justify-stretch gap-2 sm:justify-end sm:gap-1.5">
      {canReceive(ln) && (
        <Button
          size="sm"
          variant="primary"
          className="min-h-10 flex-1 sm:flex-none"
          leftIcon={<PackagePlus className="h-4 w-4" />}
          onClick={onReceive}
        >
          Receive
        </Button>
      )}
      {canReturn(ln) && (
        <Button
          size="sm"
          variant="outline"
          className="min-h-10 flex-1 sm:flex-none"
          leftIcon={<Undo2 className="h-4 w-4" />}
          onClick={onReturn}
        >
          Return
        </Button>
      )}
      {!canReceive(ln) && !canReturn(ln) && <span className="text-sm text-ink-subtle">—</span>}
    </div>
  );
}

function OrderCard({
  order,
  visibility,
  onReceive,
  onReturn,
  onVoidReceive,
}: {
  order: JobWorkFulfillmentOrder;
  visibility: Visibility;
  onReceive: (ln: JobWorkFulfillmentLine) => void;
  onReturn: (ln: JobWorkFulfillmentLine) => void;
  onVoidReceive: (r: JobWorkFulfillmentReceipt) => void;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-line/80 bg-gradient-to-br from-primary-50/80 to-surface dark:from-primary-950/30 dark:to-surface">
      <header className="flex flex-col gap-2 border-b border-line/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="primary" size="md">
              Job work
            </Badge>
            <Link
              to={`/job-work/${order.order_id}`}
              className="v2-mono text-xl font-bold text-primary-800 dark:text-primary-200"
            >
              {order.job_number}
            </Link>
          </div>
          <p className="text-lg font-semibold text-ink">{order.customer_name}</p>
        </div>
      </header>

      <div className="hidden overflow-x-auto bg-surface/50 lg:block">
        <table className="v2-data-table min-w-[52rem] w-full text-base">
          <thead>
            <tr>
              <th scope="col" className={cn(LINE_TH, "text-left")}>
                Product
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Ordered
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Received
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")} title={REMAINING_HELP}>
                Remaining
              </th>
              <th scope="col" className={cn(LINE_TH, "text-right")}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {(order.lines ?? []).map((ln) => {
              const dimmed = visibility === "actionable" && !lineNeedsAction(ln);
              return (
                <tr
                  key={ln.line_id}
                  className={cn("bg-surface/80 even:bg-surface-subtle/40", dimmed && "opacity-60")}
                >
                  <td className={LINE_TD}>
                    <div className="font-semibold text-ink">{ln.product_name}</div>
                    <div className="mt-0.5 text-sm text-ink-muted">
                      {ln.brand_name} · {ln.bag_type_name}
                    </div>
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <JwQtyCell qty={jwOrderedQty(ln)} />
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <JwQtyCell qty={jwNetReceivedQty(ln)} />
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    {remainingIsZero(ln) ? (
                      <span className="text-sm text-ink-subtle">Complete</span>
                    ) : (
                      <JwQtyCell qty={jwRemainingReceiveQty(ln)} emphasize />
                    )}
                  </td>
                  <td className={cn(LINE_TD, "text-right")}>
                    <LineActions
                      ln={ln}
                      onReceive={() => onReceive(ln)}
                      onReturn={() => onReturn(ln)}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 bg-surface/50 p-3 lg:hidden">
        {(order.lines ?? []).map((ln) => {
          const dimmed = visibility === "actionable" && !lineNeedsAction(ln);
          return (
            <div
              key={ln.line_id}
              className={cn(
                "space-y-3 rounded-2xl border border-line/80 bg-surface p-4",
                dimmed && "opacity-60"
              )}
            >
              <div className="min-w-0">
                <p className="font-semibold text-ink">{ln.product_name}</p>
                <p className="mt-0.5 text-sm text-ink-muted">
                  {ln.brand_name} · {ln.bag_type_name}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <div>
                  <dt className="text-ink-subtle">Ordered</dt>
                  <dd>
                    <JwQtyCell qty={jwOrderedQty(ln)} />
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-subtle">Received</dt>
                  <dd>
                    <JwQtyCell qty={jwNetReceivedQty(ln)} />
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-ink-subtle">Remaining</dt>
                  <dd>
                    {remainingIsZero(ln) ? (
                      <span className="text-sm text-ink-subtle">Complete</span>
                    ) : (
                      <JwQtyCell qty={jwRemainingReceiveQty(ln)} emphasize />
                    )}
                  </dd>
                </div>
              </dl>
              <div className="border-t border-line/60 pt-3">
                <LineActions ln={ln} onReceive={() => onReceive(ln)} onReturn={() => onReturn(ln)} />
              </div>
            </div>
          );
        })}
      </div>

      {(order.lines ?? []).some((ln) => (ln.receipts ?? []).length > 0) && (
        <details className="border-t border-line/70 bg-surface/40 px-5 py-3">
          <summary className="cursor-pointer text-sm font-semibold text-ink-muted hover:text-ink">
            Receipt history
          </summary>
          <div className="mt-3">
            <JwActivityLog
              items={(order.lines ?? []).flatMap((ln) =>
                (ln.receipts ?? []).map((r) => ({
                  ...r,
                  lineLabel: `${ln.product_name} · ${ln.brand_name}`,
                  is_loose: ln.is_loose,
                }))
              )}
              onVoidReceive={onVoidReceive}
            />
          </div>
        </details>
      )}
    </section>
  );
}

export default function JobWorkFulfillmentPage() {
  const [visibility, setVisibility] = useState<Visibility>("actionable");
  const [orders, setOrders] = useState<JobWorkFulfillmentOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogMode, setDialogMode] = useState<JobWorkFulfillmentMode>("receive");
  const [activeLine, setActiveLine] = useState<JobWorkFulfillmentLine | null>(null);
  const [pendingReceipt, setPendingReceipt] = useState<JobWorkFulfillmentReceipt | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const [voidBusy, setVoidBusy] = useState(false);
  const voidIdemRef = useRef<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    jobWorkFulfillmentApi
      .listOrders({ tab: "all", visibility, limit: DEFAULT_PAGE_LIMIT, offset })
      .then((page) => {
        setOrders(page.items ?? []);
        setTotal(page.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [visibility, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
    setActiveLine(null);
    setPendingReceipt(null);
    setError("");
  }, [visibility]);

  const ordersByDate = useMemo(() => groupOrdersByDate(orders), [orders]);

  const openAction = (mode: JobWorkFulfillmentMode, line: JobWorkFulfillmentLine) => {
    setDialogMode(mode);
    setActiveLine(line);
  };

  const voidReceipt = async (password: string) => {
    if (!pendingReceipt) return;
    if (!voidIdemRef.current) voidIdemRef.current = newIdempotencyKey();
    setVoidBusy(true);
    setVoidAuthError("");
    try {
      await jobWorkApi.voidReceipt(pendingReceipt.id, voidIdemRef.current, password);
      voidIdemRef.current = null;
      toast.success("Receipt voided");
      setPendingReceipt(null);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not void";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidAuthError(msg);
      } else {
        toast.error(msg);
      }
      throw err;
    } finally {
      setVoidBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Job work"
        title="Job work fulfillment"
        subtitle="Receive material from customer and return unused stock — like bill fulfillment without payment."
        actions={
          <Link to="/job-work">
            <Button variant="secondary" leftIcon={<Briefcase className="h-4 w-4" />}>
              Orders
            </Button>
          </Link>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
        <SegmentedControl
          value={visibility}
          onChange={(v) => {
            setOffset(0);
            setVisibility(v as Visibility);
          }}
          size="sm"
          className="flex w-full flex-wrap sm:w-auto sm:flex-nowrap [&>button]:min-w-0 [&>button]:flex-1 sm:[&>button]:flex-none"
          options={[
            { value: "actionable", label: "Needs action" },
            { value: "all", label: "All" },
          ]}
        />
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : orders.length === 0 ? (
        <EmptyState
          icon={<PackagePlus className="h-6 w-6" />}
          title="Nothing to fulfill"
          description="Open job work orders with lines needing receive or return will appear here."
          action={
            <Link to="/job-work/new">
              <Button>Create job work order</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-8">
          {ordersByDate.map(({ date, orders: dayOrders }) => {
            const label = date === "unknown" ? "No job date" : formatDate(date);
            const lineCount = dayOrders.reduce((n, o) => n + (o.lines?.length ?? 0), 0);
            return (
              <section key={date} className="space-y-4" aria-labelledby={`jw-fulfill-date-${date}`}>
                <header
                  id={`jw-fulfill-date-${date}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/80 bg-surface-subtle px-4 py-3 sm:px-5"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                      <Calendar className="h-4 w-4" aria-hidden="true" />
                    </div>
                    <h2 className="text-lg font-bold text-ink sm:text-xl">{label}</h2>
                  </div>
                  <span className="text-sm font-medium text-ink-muted">
                    {dayOrders.length} order{dayOrders.length === 1 ? "" : "s"} · {lineCount} line
                    {lineCount === 1 ? "" : "s"}
                  </span>
                </header>
                <div className="space-y-5">
                  {dayOrders.map((order) => (
                    <OrderCard
                      key={order.order_id}
                      order={order}
                      visibility={visibility}
                      onReceive={(ln) => openAction("receive", ln)}
                      onReturn={(ln) => openAction("return", ln)}
                      onVoidReceive={(r) => {
                        voidIdemRef.current = null;
                        setVoidAuthError("");
                        setPendingReceipt(
                          (order.lines ?? [])
                            .flatMap((ln) => ln.receipts ?? [])
                            .find((x) => x.id === r.id) ?? null
                        );
                      }}
                    />
                  ))}
                </div>
              </section>
            );
          })}
          <PaginationBar total={total} limit={DEFAULT_PAGE_LIMIT} offset={offset} onPageChange={setOffset} />
        </div>
      )}

      <JobWorkFulfillmentActionDialog
        open={!!activeLine}
        mode={dialogMode}
        line={activeLine}
        onClose={() => setActiveLine(null)}
        onSuccess={load}
      />

      <VoidConfirmDialog
        open={!!pendingReceipt}
        onClose={() => {
          if (voidBusy) return;
          setPendingReceipt(null);
          setVoidAuthError("");
        }}
        onConfirm={voidReceipt}
        title="Void receipt?"
        description="This reverses the stock added by this receipt."
        confirmLabel="Void receipt"
        authError={voidAuthError}
      />
    </>
  );
}
