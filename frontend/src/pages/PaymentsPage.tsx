import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { IndianRupee, PackagePlus, Plus, ShoppingCart } from "lucide-react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  EXPECTED_BILL_VERSION_HEADER,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type PageOut,
  type Payment,
} from "../api/client";
import {
  clearRememberedPaymentCreated,
  readRememberedPaymentCreated,
} from "../lib/paymentCreated";
import { formatDateTime, formatInr } from "../lib/format";
import { paymentModeLabel } from "../lib/statusLabels";
import { BILL_TYPE_THEME, themeForBillType } from "../lib/billTypeTheme";
import { cn } from "../lib/cn";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Card, CardBody } from "../components/ui/Card";
import Table, { type Column } from "../components/ui/Table";
import EmptyState from "../components/ui/EmptyState";
import Banner from "../components/ui/Banner";
import VoidConfirmDialog from "../components/ui/VoidConfirmDialog";
import PaginationBar from "../components/ui/PaginationBar";
import { toast } from "../components/ui/Toaster";

function samePaymentId(a: number | string | null | undefined, b: number | string | null | undefined): boolean {
  if (a == null || b == null) return false;
  return Number(a) === Number(b);
}

function prependUniquePayment(payment: Payment, items: Payment[]): Payment[] {
  if (items.some((r) => samePaymentId(r.id, payment.id))) {
    return items.map((r) => (samePaymentId(r.id, payment.id) ? payment : r));
  }
  return [payment, ...items];
}

export default function PaymentsPage() {
  const location = useLocation();
  const createdParam = new URLSearchParams(location.search).get("created");
  const createdId =
    createdParam && Number.isFinite(Number(createdParam)) ? Number(createdParam) : null;

  const [rows, setRows] = useState<Payment[]>(() => {
    const remembered = readRememberedPaymentCreated();
    if (!remembered) return [];
    if (createdId != null && Number(remembered.id) !== createdId) return [];
    return [remembered];
  });
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [voidAuthError, setVoidAuthError] = useState("");
  const [pending, setPending] = useState<Payment | null>(null);
  const [busy, setBusy] = useState(false);
  const [highlightedId, setHighlightedId] = useState<number | null>(createdId);
  const [reloadNonce, setReloadNonce] = useState(0);
  const voidIdemRef = useRef<string | null>(null);
  const loadGenRef = useRef(0);
  const limit = DEFAULT_PAGE_LIMIT;

  useEffect(() => {
    const gen = ++loadGenRef.current;
    let cancelled = false;
    const remembered = readRememberedPaymentCreated();
    const seed =
      remembered && (createdId == null || Number(remembered.id) === createdId) ? remembered : null;

    (async () => {
      setError("");
      let createdPayment: Payment | null = seed;
      if (createdId != null) {
        try {
          createdPayment = await api.get<Payment>(`/api/payments/${createdId}?_=${Date.now()}`);
          if (cancelled || gen !== loadGenRef.current) return;
          setHighlightedId(createdPayment.id);
          setRows([createdPayment]);
          setTotal(1);
        } catch {
          /* keep seed */
        }
      }

      try {
        const page = await api.get<PageOut<Payment>>(
          `/api/payments?limit=${limit}&offset=${offset}&_=${Date.now()}`
        );
        if (cancelled || gen !== loadGenRef.current) return;
        const items = createdPayment
          ? prependUniquePayment(createdPayment, page.items ?? [])
          : (page.items ?? []);
        setRows(items);
        setTotal(
          createdPayment && !(page.items ?? []).some((r) => samePaymentId(r.id, createdPayment!.id))
            ? Math.max((page.total ?? 0) + 1, items.length)
            : (page.total ?? 0)
        );
        if (createdPayment && (page.items ?? []).some((r) => samePaymentId(r.id, createdPayment!.id))) {
          clearRememberedPaymentCreated(createdPayment.id);
        }
      } catch (e) {
        if (cancelled || gen !== loadGenRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
        if (!createdPayment) {
          setRows([]);
          setTotal(0);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [limit, offset, createdId, reloadNonce]);

  const voidPayment = async (authorizationPassword: string) => {
    if (!pending) return;
    if (!voidIdemRef.current) voidIdemRef.current = newIdempotencyKey();
    setBusy(true);
    setVoidAuthError("");
    try {
      await api.post(
        `/api/payments/${pending.id}/void`,
        {},
        {
          headers: idempotencyVoidAuthHeaders(voidIdemRef.current, authorizationPassword, {
            [EXPECTED_BILL_VERSION_HEADER]: String(pending.bill_version ?? 1),
          }),
        }
      );
      voidIdemRef.current = null;
      toast.success("Payment voided");
      setPending(null);
      setReloadNonce((n) => n + 1);
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
      setBusy(false);
    }
  };

  const salesCount = rows.filter((p) => (p.bill_type ?? "sales") === "sales").length;
  const purchaseCount = rows.filter((p) => p.bill_type === "purchase").length;

  const columns: Column<Payment>[] = [
    {
      key: "bill",
      header: "Bill",
      width: "18%",
      cell: (p) => {
        const base = p.bill_type === "purchase" ? "/purchase-bills" : "/sales-bills";
        const theme = themeForBillType(p.bill_type ?? "sales");
        return (
          <div className="space-y-1">
            <Link to={`${base}/${p.bill_id}`} className={cn("v2-mono text-base font-bold", theme.billLink)}>
              {p.bill_number ?? `#${p.bill_id}`}
            </Link>
            <p className="v2-mono text-xs text-ink-subtle">ID #{p.bill_id}</p>
          </div>
        );
      },
    },
    {
      key: "type",
      header: "Type",
      width: "10%",
      cell: (p) => {
        const theme = themeForBillType(p.bill_type ?? "sales");
        return (
          <Badge size="md" tone={theme.badgeTone}>
            {theme.label}
          </Badge>
        );
      },
    },
    {
      key: "customer",
      header: "Customer",
      width: "24%",
      cell: (p) => (
        <div className="space-y-1">
          <p className="truncate text-sm font-semibold text-ink">{p.customer_name ?? "—"}</p>
          <p className="text-xs text-ink-subtle">{formatDateTime(p.paid_at)}</p>
        </div>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      numeric: true,
      width: "14%",
      cell: (p) => <span className="v2-mono text-base font-bold">{formatInr(p.amount)}</span>,
    },
    {
      key: "mode",
      header: "Payment",
      width: "16%",
      cell: (p) => {
        const isSetoff = p.payment_mode === "setoff" || p.linked_payment_id != null;
        return (
          <div className="space-y-1">
            <Badge size="sm" tone={isSetoff ? "info" : "primary"}>
              {paymentModeLabel(p.payment_mode)}
            </Badge>
            {p.payment_mode === "bank" && p.bank_account_name ? (
              <p className="truncate text-xs text-ink-subtle">{p.bank_account_name}</p>
            ) : (
              <p className="text-xs text-ink-subtle">—</p>
            )}
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "",
      align: "right",
      width: "12%",
      cell: (p) => {
        const isSetoff = p.payment_mode === "setoff" || p.linked_payment_id != null;
        if (isSetoff) {
          return <span className="text-xs text-ink-subtle" title="Void the primary payment">Linked</span>;
        }
        return (
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              voidIdemRef.current = null;
              setPending(p);
            }}
            loading={busy && pending?.id === p.id}
          >
            Void
          </Button>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="Active payments against sales and purchase bills. Voiding a primary payment cascades to its set-off rows."
        actions={
          <Link to="/payments/new">
            <Button leftIcon={<Plus className="h-4 w-4" />}>Record payment</Button>
          </Link>
        }
      />
      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={<IndianRupee />}
            title="No active payments"
            description="Use Add payment on a bill with amount due — or record a fresh payment here."
            action={
              <Link to="/payments/new">
                <Button leftIcon={<Plus className="h-4 w-4" />}>Record payment</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <Card className={cn("border-line/80", BILL_TYPE_THEME.sales.filterGradient)}>
              <CardBody className="flex items-center gap-3 p-4 sm:p-5">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
                  <ShoppingCart className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-sm font-medium text-primary-700/80 dark:text-primary-300/80">Sales payments</p>
                  <p className="text-2xl font-bold text-primary-800 dark:text-primary-100">{salesCount}</p>
                </div>
              </CardBody>
            </Card>
            <Card className={cn("border-line/80", BILL_TYPE_THEME.purchase.filterGradient)}>
              <CardBody className="flex items-center gap-3 p-4 sm:p-5">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200">
                  <PackagePlus className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <p className="text-sm font-medium text-emerald-800/80 dark:text-emerald-300/80">Purchase payments</p>
                  <p className="text-2xl font-bold text-emerald-900 dark:text-emerald-100">{purchaseCount}</p>
                </div>
              </CardBody>
            </Card>
          </div>
          <Table
            columns={columns}
            rows={rows}
            rowKey={(p) => p.id}
            caption="Active payments"
            rowClassName={(p) =>
              cn(
                themeForBillType(p.bill_type ?? "sales").row,
                highlightedId != null && samePaymentId(p.id, highlightedId)
                  ? "bg-emerald-50/90 dark:bg-emerald-950/40"
                  : undefined
              )
            }
            zebra
            compact
            stickyHeader={false}
          />
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="mt-2" />
        </>
      )}
      <VoidConfirmDialog
        open={!!pending}
        onClose={() => {
          voidIdemRef.current = null;
          setVoidAuthError("");
          setPending(null);
        }}
        onConfirm={voidPayment}
        title="Void this payment?"
        description={
          pending
            ? `Void this ${paymentModeLabel(pending.payment_mode)} payment of ${formatInr(pending.amount)} on ${pending.bill_number ?? `bill #${pending.bill_id}`}.`
            : ""
        }
        confirmLabel="Void"
        authError={voidAuthError || undefined}
      />
    </>
  );
}
