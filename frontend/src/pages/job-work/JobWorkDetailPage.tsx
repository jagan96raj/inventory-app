import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Ban, Truck } from "lucide-react";
import { jobWorkApi, newIdempotencyKey, type JobWorkLine, type JobWorkOrder } from "../../api/client";
import { formatDate, formatQtyKg } from "../../lib/format";
import { jwNetReceivedQty, jwOrderedQty, jwRemainingReceiveQty, formatJwPrimaryQty } from "../../lib/jwQty";
import PageHeader from "../../components/ui/PageHeader";
import JwQtyCell from "../../components/JwQtyCell";
import JwActivityLog from "../../components/job-work/JwActivityLog";
import Button from "../../components/ui/Button";
import Banner from "../../components/ui/Banner";
import Badge from "../../components/ui/Badge";
import Stat from "../../components/ui/Stat";
import Table, { type Column } from "../../components/ui/Table";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import Skeleton from "../../components/ui/Skeleton";
import VoidConfirmDialog from "../../components/ui/VoidConfirmDialog";
import { toast } from "../../components/ui/Toaster";

const REMAINING_HELP =
  "Remaining = ordered − total receive events + total returns (returns reopen receive allowance).";

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

function lineIsLoose(ln: JobWorkLine): boolean {
  return Boolean(ln.is_loose);
}

export default function JobWorkDetailPage() {
  const { id } = useParams();
  const orderId = Number(id);
  const [order, setOrder] = useState<JobWorkOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidAuthError, setVoidAuthError] = useState("");
  const [voidBusy, setVoidBusy] = useState(false);
  const voidIdemRef = useRef<string | null>(null);

  const load = useCallback(() => {
    if (!Number.isFinite(orderId)) return;
    setLoading(true);
    jobWorkApi
      .get(orderId)
      .then(setOrder)
      .catch((e) => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [orderId]);

  useEffect(() => {
    if (!Number.isFinite(orderId)) {
      setLoading(false);
      setOrder(null);
      setError("Job work order not found");
      return;
    }
    load();
  }, [load, orderId]);

  const netReceivedKgTotal = useMemo(() => {
    if (!order) return 0;
    return order.lines.reduce((s, ln) => s + Number(ln.net_received_kg ?? ln.custody_kg ?? 0), 0);
  }, [order]);

  const orderedKg = useMemo(() => {
    if (!order) return 0;
    return order.lines.reduce((s, ln) => s + Number(ln.ordered_quantity_kg), 0);
  }, [order]);

  const remainingKg = useMemo(() => {
    if (!order) return 0;
    return order.lines.reduce((s, ln) => s + Number(ln.remaining_receive_kg ?? 0), 0);
  }, [order]);

  const canVoidOrder = order?.status === "open" && netReceivedKgTotal === 0;

  const voidOrder = async (password: string) => {
    if (!order) return;
    if (!voidIdemRef.current) voidIdemRef.current = newIdempotencyKey();
    setVoidAuthError("");
    setVoidBusy(true);
    try {
      const updated = await jobWorkApi.void(order.id, voidIdemRef.current, password);
      voidIdemRef.current = null;
      setOrder(updated);
      setVoidOpen(false);
      toast.success("Job work order voided");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not void order";
      setVoidAuthError(msg);
    } finally {
      setVoidBusy(false);
    }
  };

  const lineColumns: Column<JobWorkLine>[] = [
    {
      key: "product",
      header: "Product",
      cell: (ln) => (
        <div>
          <p className="font-semibold text-ink">{ln.product_name}</p>
          <p className="text-sm text-ink-muted">
            {ln.brand_name} · {ln.bag_type_name}
          </p>
        </div>
      ),
    },
    {
      key: "ordered",
      header: "Ordered",
      cell: (ln) => <JwQtyCell qty={jwOrderedQty({ ...ln, is_loose: lineIsLoose(ln) })} />,
      className: "text-right",
      headerClassName: "text-right",
    },
    {
      key: "received",
      header: "Received (net)",
      cell: (ln) => (
        <div className="text-right">
          <JwQtyCell qty={jwNetReceivedQty({ ...ln, is_loose: lineIsLoose(ln) })} emphasize />
          {(ln.returned_bags > 0 || Number(ln.returned_quantity_kg) > 0) && (
            <p className="mt-1 text-xs text-ink-muted">
              Returned to customer:{" "}
              {formatJwPrimaryQty({
                is_loose: lineIsLoose(ln),
                bags: ln.returned_bags,
                loose_kg: ln.returned_loose_kg,
                kg: ln.returned_quantity_kg,
              })}
            </p>
          )}
        </div>
      ),
      className: "text-right",
      headerClassName: "text-right",
    },
    ...(order?.status === "open"
      ? [
          {
            key: "remaining",
            header: "Remaining",
            cell: (ln: JobWorkLine) => (
              <JwQtyCell
                qty={jwRemainingReceiveQty({ ...ln, is_loose: lineIsLoose(ln) })}
                emphasize
              />
            ),
            className: "text-right",
            headerClassName: "text-right",
          } satisfies Column<JobWorkLine>,
        ]
      : []),
  ];

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!order) {
    return (
      <>
        <Banner tone="danger">{error || "Order not found"}</Banner>
        <Link to="/job-work">
          <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
            Back
          </Button>
        </Link>
      </>
    );
  }

  const activityItems = order.lines.flatMap((ln) =>
    ln.receipts.map((r) => ({
      ...r,
      lineLabel: `${ln.product_name} · ${ln.brand_name}`,
      is_loose: lineIsLoose(ln),
    }))
  );

  return (
    <>
      <PageHeader
        eyebrow="Job work orders"
        title={<span className="v2-mono">{order.job_number}</span>}
        subtitle={`${order.customer_name} · ${formatDate(order.job_date)}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/job-work">
              <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
                Back
              </Button>
            </Link>
            {order.status === "open" && (
              <Link to="/job-work/fulfillment">
                <Button leftIcon={<Truck className="h-4 w-4" />}>Receive / Return</Button>
              </Link>
            )}
            {canVoidOrder && (
              <Button
                variant="danger"
                leftIcon={<Ban className="h-4 w-4" />}
                onClick={() => {
                  voidIdemRef.current = null;
                  setVoidAuthError("");
                  setVoidOpen(true);
                }}
              >
                Void order
              </Button>
            )}
          </div>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge tone={statusTone(order.status)}>{statusLabel(order.status)}</Badge>
        {order.notes && <span className="text-sm text-ink-muted">{order.notes}</span>}
      </div>

      {order.status === "open" && (
        <Banner tone="info" className="mb-5">
          Receive and return material on{" "}
          <Link to="/job-work/fulfillment" className="font-semibold text-primary-700 underline dark:text-primary-300">
            Job work fulfillment
          </Link>
          — like bill fulfillment without payment.
        </Banner>
      )}

      {order.status === "open" && netReceivedKgTotal > 0 && (
        <Banner tone="warning" className="mb-5">
          Return all material to the customer before voiding this order ({formatQtyKg(netReceivedKgTotal)} still
          received).
        </Banner>
      )}

      {order.status === "cancelled" && (
        <Banner tone="danger" className="mb-5">
          This job work order has been voided. Receive, return, and fulfillment actions are disabled.
        </Banner>
      )}

      <div
        className={`mb-5 grid gap-3 ${order.status === "open" && remainingKg > 0 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}
      >
        <Stat label="Ordered (kg)" value={formatQtyKg(orderedKg)} tone="neutral" />
        <Stat label="Received (kg)" value={formatQtyKg(netReceivedKgTotal)} tone="primary" />
        {order.status === "open" && remainingKg > 0 ? (
          <Stat label="Remaining" value={formatQtyKg(remainingKg)} tone="info" />
        ) : null}
      </div>

      <Card className="mb-5">
        <CardHeader title="Lines" subtitle={order.status === "open" ? REMAINING_HELP : undefined} />
        <CardBody>
          <Table columns={lineColumns} rows={order.lines} rowKey={(ln) => ln.id} caption="Job work lines" />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Activity log" subtitle="Receive and return events. Void receive entries from fulfillment." />
        <CardBody>
          <details>
            <summary className="cursor-pointer text-sm font-semibold text-ink-muted hover:text-ink">
              Receipt history
            </summary>
            <div className="mt-3">
              <JwActivityLog items={activityItems} />
            </div>
          </details>
        </CardBody>
      </Card>

      <VoidConfirmDialog
        open={voidOpen}
        onClose={() => {
          if (voidBusy) return;
          setVoidOpen(false);
          setVoidAuthError("");
        }}
        onConfirm={voidOrder}
        title="Void job work order?"
        description={`${order.job_number} will be marked voided. This cannot be undone.`}
        confirmLabel="Void order"
        authError={voidAuthError}
      />
    </>
  );
}
