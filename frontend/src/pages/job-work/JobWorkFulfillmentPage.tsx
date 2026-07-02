import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Briefcase, PackagePlus, Undo2 } from "lucide-react";
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
import { CardBody } from "../../components/ui/Card";
import { formatDate } from "../../lib/format";
import {
  jwCustodyQty,
  jwOrderedQty,
  jwRemainingReceiveQty,
} from "../../lib/jwQty";
import { cn } from "../../lib/cn";
import { toast } from "../../components/ui/Toaster";

type Tab = "receive" | "return";
type Visibility = "actionable" | "all";

const REMAINING_HELP =
  "Remaining = ordered − total receive events + total returns (returns reopen receive allowance).";

const LINE_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-sm font-semibold uppercase tracking-wide text-ink-muted";
const LINE_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

function tabFromPath(pathname: string): Tab {
  return pathname.endsWith("/return") ? "return" : "receive";
}

export default function JobWorkFulfillmentPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const tab = tabFromPath(pathname);
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
      .listOrders({ tab, visibility, limit: DEFAULT_PAGE_LIMIT, offset })
      .then((page) => {
        setOrders(page.items ?? []);
        setTotal(page.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [tab, visibility, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
    setActiveLine(null);
    setPendingReceipt(null);
    setError("");
  }, [tab]);

  const setTab = (next: Tab) => {
    navigate(next === "return" ? "/job-work/fulfillment/return" : "/job-work/fulfillment/receive", {
      replace: true,
    });
  };

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

  const isReceive = tab === "receive";

  return (
    <>
      <PageHeader
        eyebrow="Job work"
        title="Job work fulfillment"
        subtitle={
          isReceive
            ? `Receive material into custody. ${REMAINING_HELP}`
            : "Return material from custody to the customer."
        }
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

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          options={[
            { value: "receive", label: "Receive" },
            { value: "return", label: "Return" },
          ]}
        />
        <SegmentedControl
          value={visibility}
          onChange={(v) => {
            setOffset(0);
            setVisibility(v as Visibility);
          }}
          options={[
            { value: "actionable", label: "Needs action" },
            { value: "all", label: "All open" },
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
          icon={isReceive ? <PackagePlus className="h-6 w-6" /> : <Undo2 className="h-6 w-6" />}
          title={isReceive ? "Nothing to receive" : "Nothing to return"}
          description="Open job work orders with pending quantities will appear here."
          action={
            <Link to="/job-work/new">
              <Button>Create job work order</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-5">
          {orders.map((order) => (
            <section
              key={order.order_id}
              className="overflow-hidden rounded-2xl border border-line/80 bg-gradient-to-br from-violet-50/80 to-surface dark:from-violet-950/30 dark:to-surface"
            >
              <header className="flex flex-col gap-2 border-b border-line/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="primary" size="md">
                      Job work
                    </Badge>
                    <Link
                      to={`/job-work/${order.order_id}`}
                      className="v2-mono text-xl font-bold text-violet-800 dark:text-violet-200"
                    >
                      {order.job_number}
                    </Link>
                  </div>
                  <p className="text-lg font-semibold text-ink">{order.customer_name}</p>
                  <p className="text-sm text-ink-muted">{formatDate(order.job_date)}</p>
                </div>
                <Badge tone="primary">Open</Badge>
              </header>

              <div className="overflow-x-auto bg-surface/50">
                <table className="v2-data-table min-w-[44rem] w-full text-base">
                  <thead>
                    <tr>
                      <th scope="col" className={cn(LINE_TH, "text-left")}>
                        Product
                      </th>
                      <th scope="col" className={cn(LINE_TH, "text-right")}>
                        Ordered
                      </th>
                      <th scope="col" className={cn(LINE_TH, "text-right")} title={isReceive ? REMAINING_HELP : undefined}>
                        {isReceive ? "Remaining" : "In custody"}
                      </th>
                      <th scope="col" className={cn(LINE_TH, "text-right")}>
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(order.lines ?? []).map((ln) => (
                      <tr key={ln.line_id} className="bg-surface/80 even:bg-surface-subtle/40">
                        <td className={LINE_TD}>
                          <div className="font-semibold text-ink">{ln.product_name}</div>
                          <div className="mt-0.5 text-sm text-ink-muted">
                            {ln.brand_name} · {ln.bag_type_name}
                          </div>
                        </td>
                        <td className={LINE_TD}>
                          <JwQtyCell qty={jwOrderedQty(ln)} />
                        </td>
                        <td className={LINE_TD}>
                          <JwQtyCell
                            qty={isReceive ? jwRemainingReceiveQty(ln) : jwCustodyQty(ln)}
                            emphasize
                          />
                        </td>
                        <td className={cn(LINE_TD, "text-right")}>
                          <Button
                            size="sm"
                            variant="secondary"
                            leftIcon={isReceive ? <PackagePlus className="h-4 w-4" /> : <Undo2 className="h-4 w-4" />}
                            onClick={() => openAction(tab, ln)}
                          >
                            {isReceive ? "Receive" : "Return"}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {(order.lines ?? []).some((ln) => (ln.receipts ?? []).length > 0) && (
                  <CardBody className="border-t border-line/70 bg-surface/40 px-5 py-4">
                    <p className="mb-3 text-sm font-semibold text-ink-muted">Activity log</p>
                    <JwActivityLog
                      items={(order.lines ?? []).flatMap((ln) =>
                        (ln.receipts ?? []).map((r) => ({
                          ...r,
                          lineLabel: `${ln.product_name} · ${ln.brand_name}`,
                          is_loose: ln.is_loose,
                        }))
                      )}
                      onVoidReceive={
                        isReceive
                          ? (r) => {
                              voidIdemRef.current = null;
                              setVoidAuthError("");
                              setPendingReceipt(
                                (order.lines ?? [])
                                  .flatMap((ln) => ln.receipts ?? [])
                                  .find((x) => x.id === r.id) ?? null
                              );
                            }
                          : undefined
                      }
                    />
                  </CardBody>
                )}
            </section>
          ))}
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
