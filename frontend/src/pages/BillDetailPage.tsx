import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Ban,
  Download,
  IndianRupee,
  MapPin,
  Pencil,
  Plus,
  Printer,
  Receipt,
  ReceiptText,
  Truck,
} from "lucide-react";
import {
  api,
  billsApi,
  EXPECTED_BILL_VERSION_HEADER,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type Bill,
  type BillLine,
  type BillVoidLinkedInfo,
  type CashBookEntry,
  type FulfillmentEntry,
  type PageOut,
  type Payment,
} from "../api/client";
import { billDueAmount } from "../lib/billAmounts";
import {
  clearRememberedPaymentCreated,
  mergePaymentIntoBill,
  readRememberedPaymentCreated,
} from "../lib/paymentCreated";
import { formatInr, formatDateTime, formatQtyKg } from "../lib/format";
import { fulfillmentEntryLabel, fulfillmentQtyLabel } from "../lib/fulfillmentLabels";
import { paymentModeLabel } from "../lib/statusLabels";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import Tabs, { Tab } from "../components/ui/Tabs";
import Banner from "../components/ui/Banner";
import EmptyState from "../components/ui/EmptyState";
import VoidConfirmDialog from "../components/ui/VoidConfirmDialog";
import Badge from "../components/ui/Badge";
import { DeliveryPill, PaymentPill, VoidPill } from "../components/ui/StatusPill";
import { toast } from "../components/ui/Toaster";
import { cn } from "../lib/cn";

function orderedQty(line: BillLine) {
  if (line.is_loose) return formatQtyKg(line.ordered_quantity_kg);
  const bags = line.bags_purchased ?? line.bags_sold ?? line.ordered_bags;
  return `${bags} bags · ${formatQtyKg(line.ordered_quantity_kg)}`;
}

function deliveredQty(line: BillLine) {
  const kg = line.delivered_quantity_kg ?? "0";
  if (line.is_loose) return formatQtyKg(kg);
  const bags = line.bags_delivered ?? 0;
  return `${bags} bags · ${formatQtyKg(kg)}`;
}

function lineStockMeta(line: BillLine): string | null {
  if (line.stock_source === "job_work") return "Job work stock";
  return null;
}

function remainingQty(line: BillLine) {
  const remaining = line.remaining_kg ?? "0";
  if (Number(remaining) <= 0) return "—";
  if (line.is_loose) return formatQtyKg(remaining);
  const orderedBags = line.bags_purchased ?? line.bags_sold ?? line.ordered_bags;
  const deliveredBags = line.bags_delivered ?? 0;
  const remBags = Math.max(orderedBags - deliveredBags, 0);
  return `${remBags} bags · ${formatQtyKg(remaining)}`;
}

const detailTh =
  "border-b border-line bg-surface-muted/70 px-5 py-4 text-left text-base font-semibold uppercase tracking-wide text-ink-muted";
const detailTd = "border-b border-line/70 px-5 py-4 align-middle text-lg text-ink";

type VoidTarget =
  | { kind: "payment"; payment: Payment; linkedCount: number }
  | { kind: "fulfillment"; entry: FulfillmentEntry; lineLabel: string; isSales: boolean }
  | { kind: "bill" }
  | null;

export default function BillDetailPage({ billType }: { billType: "sales" | "purchase" }) {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const createdParam = searchParams.get("created");
  const createdId =
    createdParam && Number.isFinite(Number(createdParam)) ? Number(createdParam) : null;
  const initialTab = searchParams.get("tab") === "payments" || createdId != null ? "payments" : "overview";

  const [bill, setBill] = useState<Bill | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [entriesByLine, setEntriesByLine] = useState<Record<number, FulfillmentEntry[]>>({});
  const [linkedExpenses, setLinkedExpenses] = useState<CashBookEntry[]>([]);
  const [voidPrecheck, setVoidPrecheck] = useState<BillVoidLinkedInfo | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<VoidTarget>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const [highlightedPaymentId, setHighlightedPaymentId] = useState<number | null>(createdId);
  const confirmIdemRef = useRef<string | null>(null);
  const loadRequestIdRef = useRef(0);

  const base = billType === "sales" ? "/sales-bills" : "/purchase-bills";
  const isSales = billType === "sales";
  const qtyLabel = isSales ? "Qty sold" : "Qty purchased";
  const deliveredLabel = isSales ? "Delivered" : "Received";

  const loadBill = useCallback(() => {
    if (!id) return;
    const requestId = ++loadRequestIdRef.current;
    setLoading(true);
    setBill(null);
    setEntriesByLine({});
    setLinkedExpenses([]);
    setVoidPrecheck(null);
    setError("");

    const remembered =
      createdId != null
        ? (() => {
            const p = readRememberedPaymentCreated();
            return p && Number(p.id) === createdId && Number(p.bill_id) === Number(id) ? p : null;
          })()
        : null;

    (async () => {
      let seedPayment = remembered;
      if (createdId != null) {
        try {
          seedPayment = await api.get<Payment>(`/api/payments/${createdId}?_=${Date.now()}`);
          if (loadRequestIdRef.current !== requestId) return;
          setHighlightedPaymentId(seedPayment.id);
        } catch {
          /* keep remembered seed if GET fails */
        }
      }

      try {
        const b = await api.get<Bill>(`/api/bills/${id}?_=${Date.now()}`);
        if (loadRequestIdRef.current !== requestId) return;
        if (b.bill_type !== billType) {
          setBill(null);
          setEntriesByLine({});
          setLinkedExpenses([]);
          setVoidPrecheck(null);
          setError("Bill type mismatch");
          return;
        }
        const merged =
          seedPayment && Number(seedPayment.bill_id) === Number(b.id)
            ? mergePaymentIntoBill(b, seedPayment)
            : b;
        setBill(merged);
        setError("");
        if (
          seedPayment &&
          (merged.payments ?? []).some((p) => Number(p.id) === Number(seedPayment!.id))
        ) {
          clearRememberedPaymentCreated(seedPayment.id);
        }

        const entryResults = await Promise.all(
          b.lines.map((line) =>
            api.get<PageOut<FulfillmentEntry>>(
              `/api/fulfillment/entries?bill_line_id=${line.id}&limit=50&offset=0&_=${Date.now()}`
            )
          )
        );
        if (loadRequestIdRef.current !== requestId) return;
        const map: Record<number, FulfillmentEntry[]> = {};
        b.lines.forEach((line, index) => {
          map[line.id] = entryResults[index]?.items ?? [];
        });
        setEntriesByLine(map);
        try {
          const linkedPage = await billsApi.linkedEntries(b.id, { limit: 100 });
          if (loadRequestIdRef.current !== requestId) return;
          setLinkedExpenses(linkedPage.items.filter((e) => !e.voided_at));
        } catch {
          if (loadRequestIdRef.current !== requestId) return;
          setLinkedExpenses([]);
        }
        try {
          if (loadRequestIdRef.current !== requestId) return;
          setVoidPrecheck(await billsApi.voidPrecheck(b.id));
        } catch {
          if (loadRequestIdRef.current !== requestId) return;
          setVoidPrecheck(null);
        }
      } catch (e) {
        if (loadRequestIdRef.current !== requestId) return;
        setBill(null);
        setEntriesByLine({});
        setLinkedExpenses([]);
        setVoidPrecheck(null);
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (loadRequestIdRef.current === requestId) setLoading(false);
      }
    })();
  }, [id, billType, createdId]);

  useEffect(() => {
    loadBill();
  }, [loadBill]);

  const setoffCountFor = (paymentId: number, payments: Payment[]) =>
    payments.filter((p) => p.linked_payment_id === paymentId && !p.voided_at).length;

  const askVoidPayment = (payment: Payment) => {
    if (!bill || bill.status === "voided") return;
    const isSetoff = payment.payment_mode === "setoff" || payment.linked_payment_id != null;
    if (isSetoff || payment.voided_at) return;
    confirmIdemRef.current = null;
    setConfirmTarget({
      kind: "payment",
      payment,
      linkedCount: setoffCountFor(payment.id, bill.payments ?? []),
    });
  };
  const askVoidFulfillment = (entry: FulfillmentEntry, lineLabel: string) => {
    if (bill?.status === "voided") return;
    if (entry.voided_at) return;
    confirmIdemRef.current = null;
    setConfirmTarget({ kind: "fulfillment", entry, lineLabel, isSales });
  };

  const askVoidBill = () => {
    if (!voidPrecheck?.can_void) return;
    confirmIdemRef.current = null;
    setConfirmTarget({ kind: "bill" });
  };

  const runConfirm = async (authorizationPassword: string) => {
    if (!confirmTarget || !bill) return;
    if (!confirmIdemRef.current) confirmIdemRef.current = newIdempotencyKey();
    setVoidAuthError("");
    if (confirmTarget.kind === "bill") {
      setBusyId(bill.id);
      try {
        await billsApi.void(bill.id, confirmIdemRef.current, authorizationPassword, bill.version);
        confirmIdemRef.current = null;
        toast.success("Bill voided");
        setConfirmTarget(null);
        loadBill();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not void bill";
        if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
          setVoidAuthError(msg);
        } else {
          setError(msg);
          toast.error(msg);
        }
        throw err;
      } finally {
        setBusyId(null);
      }
      return;
    }
    if (confirmTarget.kind === "payment") {
      const { payment } = confirmTarget;
      setBusyId(payment.id);
      try {
        await api.post(
          `/api/payments/${payment.id}/void`,
          {},
          {
            headers: idempotencyVoidAuthHeaders(confirmIdemRef.current, authorizationPassword, {
              [EXPECTED_BILL_VERSION_HEADER]: String(bill.version),
            }),
          }
        );
        confirmIdemRef.current = null;
        toast.success("Payment voided");
        setConfirmTarget(null);
        loadBill();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not void payment";
        if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
          setVoidAuthError(msg);
        } else {
          setError(msg);
          toast.error(msg);
        }
        throw err;
      } finally {
        setBusyId(null);
      }
    } else {
      const { entry } = confirmTarget;
      setBusyId(entry.id);
      try {
        await api.post(
          `/api/fulfillment/${entry.id}/void`,
          {},
          {
            headers: idempotencyVoidAuthHeaders(confirmIdemRef.current, authorizationPassword, {
              [EXPECTED_BILL_VERSION_HEADER]: String(bill.version),
            }),
          }
        );
        confirmIdemRef.current = null;
        toast.success("Fulfillment entry voided — stock reversed");
        setConfirmTarget(null);
        loadBill();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not void entry";
        if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
          setVoidAuthError(msg);
        } else {
          setError(msg);
          toast.error(msg);
        }
        throw err;
      } finally {
        setBusyId(null);
      }
    }
  };

  const due = useMemo(() => (bill ? billDueAmount(bill) : 0), [bill]);
  const finalPayable = bill?.final_payable ?? bill?.grand_total ?? "0";

  /** Newest first so a just-recorded payment is at the top, like cash book. */
  const paymentsNewestFirst = useMemo(() => {
    const rows = bill?.payments ?? [];
    return [...rows].sort((a, b) => {
      const byDate = String(b.paid_at).localeCompare(String(a.paid_at));
      return byDate !== 0 ? byDate : Number(b.id) - Number(a.id);
    });
  }, [bill]);

  if (loading) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-ink-muted">Loading bill…</p>
        </CardBody>
      </Card>
    );
  }

  if (error || !bill) {
    return (
      <>
        <Banner tone="danger" className="mb-4">
          {error || "Bill not found"}
        </Banner>
        <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(base)}>
          Back to list
        </Button>
      </>
    );
  }

  const paymentsTab = (
    <Card className="border-line/80">
      <CardHeader
        title="Payments"
        subtitle="Cash, bank, balance and set-off payments recorded against this bill."
      />
      <CardBody className="space-y-4 pt-0">
        {!bill.payments?.length ? (
          <EmptyState
            icon={<IndianRupee />}
            title="No payments yet"
            description="Record cash, bank, or balance-mode payments against this bill."
            action={
              due > 0 ? (
                <Button leftIcon={<IndianRupee className="h-4 w-4" />} onClick={() => navigate(`${base}/${bill.id}/payment`)}>
                  Record payment
                </Button>
              ) : null
            }
          />
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-2xl border border-line/80 bg-surface lg:block">
              <table className="v2-data-table min-w-full">
                <caption className="sr-only">Bill payments</caption>
                <thead>
                  <tr>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      Amount
                    </th>
                    <th scope="col" className={detailTh}>
                      Mode
                    </th>
                    <th scope="col" className={detailTh}>
                      Paid at
                    </th>
                    <th scope="col" className={detailTh}>
                      Status
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {paymentsNewestFirst.map((p) => {
                    const voided = Boolean(p.voided_at);
                    const isSetoff = p.payment_mode === "setoff" || p.linked_payment_id != null;
                    const justRecorded = highlightedPaymentId != null && Number(p.id) === highlightedPaymentId;
                    return (
                      <tr
                        key={p.id}
                        className={cn(
                          voided && "opacity-65",
                          justRecorded && "bg-emerald-50/90 dark:bg-emerald-950/40"
                        )}
                      >
                        <td className={cn(detailTd, "text-right v2-mono text-lg font-bold tabular-nums")}>
                          {formatInr(p.amount)}
                        </td>
                        <td className={detailTd}>
                          <Badge tone={isSetoff ? "info" : "primary"} size="md">
                            {paymentModeLabel(p.payment_mode)}
                          </Badge>
                          {p.payment_mode === "bank" && p.bank_account_name && (
                            <p className="mt-1 text-xs text-ink-subtle">{p.bank_account_name}</p>
                          )}
                        </td>
                        <td className={cn(detailTd, "v2-mono text-ink-muted", voided && "line-through")}>
                          {formatDateTime(p.paid_at)}
                        </td>
                        <td className={detailTd}>
                          {voided ? (
                            <VoidPill when={p.voided_at} />
                          ) : (
                            <Badge tone="success" size="md" dot>
                              Active
                            </Badge>
                          )}
                        </td>
                        <td className={cn(detailTd, "text-right")}>
                          {!voided && !isSetoff ? (
                            <Button
                              size="md"
                              variant="danger"
                              loading={busyId === p.id}
                              onClick={() => askVoidPayment(p)}
                            >
                              Void
                            </Button>
                          ) : isSetoff ? (
                            <span className="text-sm text-ink-muted" title="Void the primary payment instead">
                              Linked set-off
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="space-y-3 lg:hidden">
              {paymentsNewestFirst.map((p) => {
                const voided = Boolean(p.voided_at);
                const isSetoff = p.payment_mode === "setoff" || p.linked_payment_id != null;
                const justRecorded = highlightedPaymentId != null && Number(p.id) === highlightedPaymentId;
                return (
                  <div
                    key={p.id}
                    className={cn(
                      "rounded-2xl border border-line/80 bg-surface-subtle/50 p-4 space-y-3",
                      voided && "opacity-65",
                      justRecorded && "border-emerald-300/80 bg-emerald-50/70 dark:border-emerald-800 dark:bg-emerald-950/40"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="v2-mono text-2xl font-bold tabular-nums text-ink">{formatInr(p.amount)}</p>
                      {voided ? (
                        <VoidPill when={p.voided_at} />
                      ) : (
                        <Badge tone="success" size="md" dot>
                          Active
                        </Badge>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={isSetoff ? "info" : "primary"} size="md">
                        {paymentModeLabel(p.payment_mode)}
                      </Badge>
                      <span className={cn("text-base v2-mono text-ink-muted", voided && "line-through")}>
                        {formatDateTime(p.paid_at)}
                      </span>
                    </div>
                    {!voided && !isSetoff ? (
                      <Button
                        size="md"
                        variant="danger"
                        className="w-full sm:w-auto"
                        loading={busyId === p.id}
                        onClick={() => askVoidPayment(p)}
                      >
                        Void payment
                      </Button>
                    ) : isSetoff ? (
                      <p className="text-sm text-ink-muted">Linked set-off — void the primary payment instead.</p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );

  const fulfillmentTab = (
    <Card className="border-line/80">
      <CardHeader
        title={isSales ? "Delivery history" : "Receiving history"}
        subtitle={
          isSales
            ? "Deliver and return entries for each product line. Void to reverse stock."
            : "Receive and return entries for each product line. Void to reverse stock."
        }
      />
      <CardBody className="space-y-6 pt-0">
        {bill.lines.length === 0 ? (
          <p className="text-base text-ink-muted">No products on this bill.</p>
        ) : bill.lines.every((line) => !(entriesByLine[line.id]?.length ?? 0)) ? (
          <EmptyState
            icon={<Truck />}
            title={isSales ? "No delivery entries yet" : "No receiving entries yet"}
            description="Use the fulfillment page to deliver sales or receive purchases."
            action={
              <Button leftIcon={<Truck className="h-4 w-4" />} onClick={() => navigate("/fulfillment")}>
                Open fulfillment
              </Button>
            }
          />
        ) : (
          bill.lines.map((line) => {
            const entries = entriesByLine[line.id] ?? [];
            if (entries.length === 0) return null;
            const lineLabel = line.product_name ?? `Product #${line.product_id}`;
            const lineMeta = [line.brand_name, line.bag_type_name].filter(Boolean).join(" · ");
            return (
              <section key={line.id} className="space-y-4">
                <header className="rounded-xl border border-line/80 bg-gradient-to-r from-surface-muted/80 to-surface-subtle px-4 py-3 sm:px-5 sm:py-4">
                  <p className="text-lg font-semibold text-ink">{lineLabel}</p>
                  {lineMeta && <p className="mt-0.5 text-base text-ink-muted">{lineMeta}</p>}
                </header>

                <div className="hidden overflow-x-auto rounded-2xl border border-line/80 bg-surface lg:block">
                  <table className="v2-data-table min-w-full">
                    <caption className="sr-only">Fulfillment for {lineLabel}</caption>
                    <thead>
                      <tr>
                        <th scope="col" className={detailTh}>
                          Date
                        </th>
                        <th scope="col" className={detailTh}>
                          Type
                        </th>
                        <th scope="col" className={detailTh}>
                          Location
                        </th>
                        <th scope="col" className={cn(detailTh, "text-right")}>
                          Quantity
                        </th>
                        <th scope="col" className={detailTh}>
                          Vehicle
                        </th>
                        <th scope="col" className={detailTh}>
                          Status
                        </th>
                        <th scope="col" className={cn(detailTh, "text-right")}>
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((entry) => {
                        const voided = Boolean(entry.voided_at);
                        const isReturn = entry.entry_type === "return";
                        return (
                          <tr key={entry.id} className={cn(voided && "opacity-65")}>
                            <td className={cn(detailTd, "v2-mono text-ink-muted", voided && "line-through")}>
                              {formatDateTime(entry.fulfilled_at)}
                            </td>
                            <td className={detailTd}>
                              <Badge tone={isReturn ? "warning" : "primary"} size="md">
                                {fulfillmentEntryLabel(entry.entry_type, isSales ? "sales" : "purchase")}
                              </Badge>
                            </td>
                            <td className={cn(detailTd, "font-medium")}>{entry.location_name ?? "—"}</td>
                            <td
                              className={cn(
                                detailTd,
                                "text-right v2-mono font-semibold tabular-nums",
                                voided && "line-through"
                              )}
                            >
                              {fulfillmentQtyLabel(entry, Boolean(line.is_loose))}
                            </td>
                            <td className={cn(detailTd, "text-ink-muted")}>{entry.vehicle_no ?? "—"}</td>
                            <td className={detailTd}>
                              {voided ? (
                                <VoidPill when={entry.voided_at} />
                              ) : (
                                <Badge tone="success" size="md" dot>
                                  Active
                                </Badge>
                              )}
                            </td>
                            <td className={cn(detailTd, "text-right")}>
                              {!voided ? (
                                <Button
                                  size="md"
                                  variant="danger"
                                  loading={busyId === entry.id}
                                  onClick={() => askVoidFulfillment(entry, `${lineLabel} · ${line.brand_name}`)}
                                >
                                  Void
                                </Button>
                              ) : null}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="space-y-3 lg:hidden">
                  {entries.map((entry) => {
                    const voided = Boolean(entry.voided_at);
                    const isReturn = entry.entry_type === "return";
                    return (
                      <div
                        key={entry.id}
                        className={cn(
                          "rounded-2xl border border-line/80 bg-surface-subtle/50 p-4 space-y-4",
                          voided && "opacity-65"
                        )}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Badge tone={isReturn ? "warning" : "primary"} size="md">
                            {fulfillmentEntryLabel(entry.entry_type, isSales ? "sales" : "purchase")}
                          </Badge>
                          {voided ? (
                            <VoidPill when={entry.voided_at} />
                          ) : (
                            <Badge tone="success" size="md" dot>
                              Active
                            </Badge>
                          )}
                        </div>
                        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <div>
                            <dt className="text-sm font-medium text-ink-subtle">Date</dt>
                            <dd className={cn("mt-1 text-base v2-mono text-ink", voided && "line-through")}>
                              {formatDateTime(entry.fulfilled_at)}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-sm font-medium text-ink-subtle">Location</dt>
                            <dd className="mt-1 text-base font-medium text-ink">{entry.location_name ?? "—"}</dd>
                          </div>
                          <div>
                            <dt className="text-sm font-medium text-ink-subtle">Quantity</dt>
                            <dd
                              className={cn(
                                "mt-1 text-base v2-mono font-semibold tabular-nums text-ink",
                                voided && "line-through"
                              )}
                            >
                              {fulfillmentQtyLabel(entry, Boolean(line.is_loose))}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-sm font-medium text-ink-subtle">Vehicle</dt>
                            <dd className="mt-1 text-base text-ink-muted">{entry.vehicle_no ?? "—"}</dd>
                          </div>
                        </dl>
                        {!voided ? (
                          <Button
                            size="md"
                            variant="danger"
                            className="w-full sm:w-auto"
                            loading={busyId === entry.id}
                            onClick={() => askVoidFulfillment(entry, `${lineLabel} · ${line.brand_name}`)}
                          >
                            Void entry
                          </Button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })
        )}
      </CardBody>
    </Card>
  );

  const productLinesSection = (
    <Card className="border-line/80">
      <CardHeader
        title="Products"
        subtitle={`${bill.lines.length} line${bill.lines.length === 1 ? "" : "s"} — ordered, ${deliveredLabel.toLowerCase()}, remaining and rates.`}
      />
      <CardBody className="space-y-6 pt-0">
        {bill.lines.length === 0 ? (
          <p className="text-sm text-ink-muted">No products on this bill.</p>
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-2xl border border-line/80 bg-surface lg:block">
              <table className="v2-data-table min-w-full text-base">
                <caption className="sr-only">Bill line items</caption>
                <thead>
                  <tr>
                    <th scope="col" className={detailTh}>
                      Product
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      {qtyLabel}
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      {deliveredLabel}
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      Remaining
                    </th>
                    <th scope="col" className={detailTh}>
                      Status
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      Rate/kg
                    </th>
                    <th scope="col" className={cn(detailTh, "text-right")}>
                      Line total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {bill.lines.map((line) => (
                    <tr key={line.id}>
                      <td className={detailTd}>
                        <p className="font-semibold text-ink">
                          {line.product_name ?? `Product #${line.product_id}`}
                        </p>
                        <p className="mt-0.5 text-sm text-ink-muted">
                          {line.brand_name} · {line.bag_type_name}
                        </p>
                        {isSales && lineStockMeta(line) && (
                          <p className="mt-1">
                            <Badge tone="info" size="sm">
                              {lineStockMeta(line)}
                            </Badge>
                          </p>
                        )}
                      </td>
                      <td className={cn(detailTd, "text-right v2-mono tabular-nums")}>{orderedQty(line)}</td>
                      <td className={cn(detailTd, "text-right v2-mono tabular-nums")}>{deliveredQty(line)}</td>
                      <td className={cn(detailTd, "text-right v2-mono tabular-nums")}>{remainingQty(line)}</td>
                      <td className={detailTd}>
                        <DeliveryPill status={line.line_delivery_status} />
                      </td>
                      <td className={cn(detailTd, "text-right v2-mono tabular-nums")}>
                        {formatInr(line.rate_per_kg)}
                      </td>
                      <td className={cn(detailTd, "text-right v2-mono text-lg font-bold tabular-nums")}>
                        {formatInr(line.line_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="space-y-3 lg:hidden">
              {bill.lines.map((line) => (
                <div
                  key={line.id}
                  className="space-y-3 rounded-2xl border border-line/80 bg-surface-subtle/50 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">
                        {line.product_name ?? `Product #${line.product_id}`}
                      </p>
                      <p className="mt-0.5 text-sm text-ink-muted">
                        {line.brand_name} · {line.bag_type_name}
                      </p>
                      {isSales && lineStockMeta(line) && (
                        <p className="mt-1">
                          <Badge tone="info" size="sm">
                            {lineStockMeta(line)}
                          </Badge>
                        </p>
                      )}
                    </div>
                    <DeliveryPill status={line.line_delivery_status} />
                  </div>
                  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                    <div>
                      <dt className="text-ink-subtle">{qtyLabel}</dt>
                      <dd className="v2-mono font-medium tabular-nums text-ink">{orderedQty(line)}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-subtle">{deliveredLabel}</dt>
                      <dd className="v2-mono font-medium tabular-nums text-ink">{deliveredQty(line)}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-subtle">Remaining</dt>
                      <dd className="v2-mono font-medium tabular-nums text-ink">{remainingQty(line)}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-subtle">Rate/kg</dt>
                      <dd className="v2-mono font-medium tabular-nums text-ink">{formatInr(line.rate_per_kg)}</dd>
                    </div>
                  </dl>
                  <div className="flex items-center justify-between border-t border-line/60 pt-3">
                    <span className="text-sm text-ink-muted">Line total</span>
                    <span className="v2-mono text-lg font-bold tabular-nums text-ink">
                      {formatInr(line.line_total)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-6 flex flex-col items-end gap-2 border-t border-line/70 pt-5 text-base">
              <div className="flex w-full max-w-xs justify-between gap-4 text-ink-muted">
                <span>Subtotal</span>
                <span className="v2-mono text-ink">{formatInr(bill.total_amount ?? bill.subtotal)}</span>
              </div>
              {Number(bill.discount_percent) > 0 && (
                <div className="flex w-full max-w-xs justify-between gap-4 text-ink-muted">
                  <span>Discount ({bill.discount_percent}%)</span>
                  <span className="v2-mono text-ink">−{formatInr(bill.discount_amount)}</span>
                </div>
              )}
              {Number(bill.adjustment) > 0 && (
                <div className="flex w-full max-w-xs justify-between gap-4 text-ink-muted">
                  <span>Adjustment</span>
                  <span className="v2-mono text-ink">−{formatInr(bill.adjustment)}</span>
                </div>
              )}
              <div className="flex w-full max-w-xs justify-between gap-4 font-semibold text-ink">
                <span>Final payable</span>
                <span className="v2-mono text-base">{formatInr(finalPayable)}</span>
              </div>
            </div>
            {bill.notes?.trim() && (
              <div className="rounded-xl border border-line/70 bg-surface-muted/40 px-4 py-3">
                <p className="text-sm font-medium text-ink-subtle">Notes</p>
                <p className="mt-1 whitespace-pre-wrap text-base text-ink">{bill.notes.trim()}</p>
              </div>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );

  const linkedExpensesTotal = linkedExpenses.reduce((s, e) => s + Number(e.amount), 0);
  const linkedExpensesSection = (
    <Card className="border-line/80">
      <CardHeader
        title="Linked expenses"
        subtitle="Non-bill expenses (e.g. freight) recorded against this bill in the Cash Book."
        actions={
          <Link to={`/accounts/cashbook/new?bill_id=${bill.id}&category=Freight%20Charges`}>
            <Button size="sm" variant="secondary" leftIcon={<Plus className="h-4 w-4" />}>
              Add linked expense
            </Button>
          </Link>
        }
      />
      <CardBody className="pt-0">
        {linkedExpenses.length === 0 ? (
          <EmptyState
            icon={<ReceiptText />}
            title="No linked expenses"
            description="Record freight or other non-bill expenses paid for this bill."
            action={
              <Link to={`/accounts/cashbook/new?bill_id=${bill.id}&category=Freight%20Charges`}>
                <Button leftIcon={<Plus className="h-4 w-4" />}>Add linked expense</Button>
              </Link>
            }
          />
        ) : (
          <>
            <div className="hidden overflow-x-auto rounded-2xl border border-line/80 bg-surface lg:block">
              <table className="v2-data-table min-w-full">
                <caption className="sr-only">Linked cash book expenses</caption>
                <thead>
                  <tr>
                    <th className={detailTh}>Date</th>
                    <th className={detailTh}>Category</th>
                    <th className={cn(detailTh, "text-right")}>Amount</th>
                    <th className={detailTh}>Mode / Bank</th>
                    <th className={detailTh}>Description</th>
                    <th className={cn(detailTh, "text-right")}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {linkedExpenses.map((e) => (
                    <tr key={e.id}>
                      <td className={cn(detailTd, "v2-mono text-ink-muted")}>{e.entry_date}</td>
                      <td className={cn(detailTd, "font-medium")}>{e.category_name ?? "—"}</td>
                      <td className={cn(detailTd, "text-right v2-mono font-semibold")}>{formatInr(e.amount)}</td>
                      <td className={detailTd}>
                        {e.source_payment_mode === "bank" ? e.source_bank_account_name ?? "Bank" : "Cash"}
                      </td>
                      <td className={cn(detailTd, "text-ink-muted")}>
                        <p className="truncate text-sm">{e.description ?? "—"}</p>
                        {e.reference_no && <p className="text-xs text-ink-subtle">Ref: {e.reference_no}</p>}
                      </td>
                      <td className={cn(detailTd, "text-right")}>
                        <Link to={`/accounts/cashbook/${e.id}/edit`}>
                          <Button size="sm" variant="ghost">
                            Open
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2} className={cn(detailTd, "text-right font-semibold text-ink-muted")}>
                      Total linked expenses
                    </td>
                    <td className={cn(detailTd, "text-right v2-mono font-bold")}>
                      {formatInr(linkedExpensesTotal)}
                    </td>
                    <td colSpan={3} className={detailTd} />
                  </tr>
                </tfoot>
              </table>
            </div>

            <div className="space-y-3 lg:hidden">
              {linkedExpenses.map((e) => (
                <div
                  key={e.id}
                  className="space-y-3 rounded-2xl border border-line/80 bg-surface-subtle/50 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">{e.category_name ?? "—"}</p>
                      <p className="mt-0.5 v2-mono text-sm text-ink-muted">{e.entry_date}</p>
                    </div>
                    <p className="v2-mono shrink-0 text-lg font-bold tabular-nums text-ink">
                      {formatInr(e.amount)}
                    </p>
                  </div>
                  <p className="text-sm text-ink-muted">
                    {e.source_payment_mode === "bank" ? e.source_bank_account_name ?? "Bank" : "Cash"}
                    {e.description ? ` · ${e.description}` : ""}
                  </p>
                  {e.reference_no && (
                    <p className="text-xs text-ink-subtle">Ref: {e.reference_no}</p>
                  )}
                  <Link to={`/accounts/cashbook/${e.id}/edit`} className="block">
                    <Button size="md" variant="secondary" className="w-full sm:w-auto">
                      Open
                    </Button>
                  </Link>
                </div>
              ))}
              <div className="flex items-center justify-between rounded-xl border border-line/70 bg-surface px-4 py-3">
                <span className="text-sm font-semibold text-ink-muted">Total linked expenses</span>
                <span className="v2-mono text-base font-bold tabular-nums text-ink">
                  {formatInr(linkedExpensesTotal)}
                </span>
              </div>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );

  const overviewTab = (
    <div className="space-y-6">
      {productLinesSection}
      {linkedExpensesSection}
    </div>
  );

  const activePaymentCount = bill.payments?.filter((p) => !p.voided_at).length ?? 0;
  const activeEntryCount = Object.values(entriesByLine)
    .flat()
    .filter((e) => !e.voided_at).length;
  const isVoided = bill.status === "voided";
  const canVoidBill = Boolean(voidPrecheck?.can_void) && !isVoided;

  return (
    <>
      <PageHeader
        eyebrow={isSales ? "Sales bill" : "Purchase bill"}
        title={
          <span className="flex items-center gap-2">
            <Receipt className="h-6 w-6 text-primary-500" />
            <span className="v2-mono">{bill.bill_number}</span>
          </span>
        }
        subtitle={`${bill.customer_name ?? "—"} · ${bill.bill_date}`}
        actions={
          <>
            {!isVoided && due > 0 && (
              <Link to={`${base}/${bill.id}/payment`} className="order-first w-full sm:w-auto">
                <Button leftIcon={<IndianRupee className="h-4 w-4" />} className="w-full sm:w-auto">
                  Record payment
                </Button>
              </Link>
            )}
            <Link to={`${base}/${bill.id}/edit`}>
              <Button variant="secondary" leftIcon={<Pencil className="h-4 w-4" />} disabled={isVoided}>
                Edit
              </Button>
            </Link>
            <Link to={`${base}/${bill.id}/print`} target="_blank" rel="noopener noreferrer">
              <Button variant="secondary" leftIcon={<Printer className="h-4 w-4" />}>
                Print
              </Button>
            </Link>
            <Link to={`${base}/${bill.id}/print?download=1`} target="_blank" rel="noopener noreferrer">
              <Button variant="secondary" leftIcon={<Download className="h-4 w-4" />}>
                <span className="sm:hidden">PDF</span>
                <span className="hidden sm:inline">Download PDF</span>
              </Button>
            </Link>
            {canVoidBill && (
              <Button variant="danger" leftIcon={<Ban className="h-4 w-4" />} onClick={askVoidBill}>
                Void bill
              </Button>
            )}
            <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(base)}>
              Back
            </Button>
          </>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {!isVoided && voidPrecheck && !voidPrecheck.can_void && voidPrecheck.block_reasons.length > 0 && (
        <Banner tone="warning" className="mb-4">
          Void bill unavailable: {voidPrecheck.block_reasons.join(" ")}
        </Banner>
      )}

      <Card className="mb-5 border-line/80">
        <CardBody className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <PaymentPill status={bill.payment_status} />
            <DeliveryPill status={bill.order_delivery_status} />
            <Badge tone="neutral" size="sm">
              {bill.status}
            </Badge>
            {isVoided && (
              <Badge tone="danger" size="sm">
                Voided
              </Badge>
            )}
            <Badge tone="info" size="sm">
              {isSales ? "Sales" : "Purchase"}
            </Badge>
            {isSales && bill.location_name && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-subtle px-2.5 py-1 text-sm text-ink-muted">
                <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {bill.location_name}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 lg:justify-end">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Final payable</p>
              <p className="v2-mono text-xl font-bold text-ink">{formatInr(finalPayable)}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Paid</p>
              <p className="v2-mono text-base font-semibold text-ink">{formatInr(bill.amount_paid)}</p>
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">
                {due > 0 ? "Due" : "Balance"}
              </p>
              <p
                className={cn(
                  "v2-mono text-base font-semibold",
                  due > 0 ? "text-danger-700 dark:text-danger-300" : "text-accent-700 dark:text-accent-300"
                )}
              >
                {due > 0 ? formatInr(due) : "Settled"}
              </p>
            </div>
          </div>
        </CardBody>
      </Card>

      {highlightedPaymentId != null &&
        bill.payments?.some((p) => Number(p.id) === highlightedPaymentId) && (
          <Card className="mb-4 border-emerald-300/80 bg-emerald-50/60 dark:border-emerald-800 dark:bg-emerald-950/40">
            <CardBody className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-200">
                  Just recorded
                </p>
                {(() => {
                  const p = bill.payments!.find((row) => Number(row.id) === highlightedPaymentId)!;
                  return (
                    <>
                      <p className="text-2xl font-bold tabular-nums text-ink">
                        {formatInr(p.amount)}
                        <span className="ml-2 text-base font-medium text-ink-muted">
                          {paymentModeLabel(p.payment_mode)}
                        </span>
                      </p>
                      <p className="text-sm text-ink-muted">
                        #{p.id} · {formatDateTime(p.paid_at)}
                      </p>
                    </>
                  );
                })()}
              </div>
            </CardBody>
          </Card>
        )}

      <Tabs defaultId={initialTab} variant="pill" size="lg" className="mb-2 [&_[role=tabpanel]]:mt-6">
        <Tab
          id="overview"
          label={
            <span className="inline-flex items-center gap-1.5">
              <Receipt className="h-4 w-4" /> Overview
            </span>
          }
          badge={bill.lines.length}
        >
          {overviewTab}
        </Tab>
        <Tab
          id="payments"
          label={<span className="inline-flex items-center gap-1.5"><IndianRupee className="h-4 w-4" /> Payments</span>}
          badge={activePaymentCount}
        >
          {paymentsTab}
        </Tab>
        <Tab
          id="fulfillment"
          label={<span className="inline-flex items-center gap-1.5"><Truck className="h-4 w-4" /> Fulfillment</span>}
          badge={activeEntryCount}
        >
          {fulfillmentTab}
        </Tab>
      </Tabs>

      <VoidConfirmDialog
        open={!!confirmTarget}
        onClose={() => {
          setVoidAuthError("");
          setConfirmTarget(null);
        }}
        onConfirm={runConfirm}
        title={
          confirmTarget?.kind === "bill"
            ? "Void this bill?"
            : confirmTarget?.kind === "payment"
              ? "Void this payment?"
              : "Void this fulfillment entry?"
        }
        description={
          confirmTarget?.kind === "bill"
            ? `Void ${bill.bill_number}? This removes the bill from active lists and reverses the customer balance. Linked cash-book entries are not changed.${
                (voidPrecheck?.linked_active_entries_count ?? 0) > 0
                  ? ` Note: ${voidPrecheck?.linked_active_entries_count} linked cash-book entr${
                      voidPrecheck?.linked_active_entries_count === 1 ? "y remains" : "ies remain"
                    } on this bill — void those first to allow bill void.`
                  : ""
              }`
            : confirmTarget?.kind === "payment"
            ? `Void this ${paymentModeLabel(confirmTarget.payment.payment_mode)} payment of ${formatInr(confirmTarget.payment.amount)}.${
                confirmTarget.linkedCount > 0
                  ? ` This will also void ${confirmTarget.linkedCount} set-off payment(s) on opposite bill(s).`
                  : ""
              }`
            : confirmTarget?.kind === "fulfillment"
              ? `Void this ${fulfillmentEntryLabel(
                  confirmTarget.entry.entry_type,
                  confirmTarget.isSales ? "sales" : "purchase"
                ).toLowerCase()} entry (${fulfillmentQtyLabel(confirmTarget.entry, false)}) on ${confirmTarget.lineLabel}? Stock will be reversed.`
              : ""
        }
        confirmLabel="Void"
        cancelLabel="Keep"
        authError={voidAuthError || undefined}
      />
    </>
  );
}
