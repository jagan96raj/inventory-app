import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, IndianRupee } from "lucide-react";
import { api, bankAccountsApi, idempotencyHeaders, newIdempotencyKey, type BankAccount, type Bill, type SetoffPreview } from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { formatInr } from "../lib/format";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import FormField from "../components/ui/FormField";
import NumberInput from "../components/ui/NumberInput";
import Select from "../components/ui/Select";
import Banner from "../components/ui/Banner";
import EmptyState from "../components/ui/EmptyState";
import { PaymentPill } from "../components/ui/StatusPill";
import { toast } from "../components/ui/Toaster";
import { cn } from "../lib/cn";

type Props = { billType?: "sales" | "purchase" };

function dueAmount(b: Bill): number {
  return Number(b.amount_due ?? b.due_amount ?? Number(b.grand_total) - Number(b.amount_paid));
}

function isBalanceMode(billType: string, mode: string): boolean {
  return (billType === "purchase" && mode === "debit") || (billType === "sales" && mode === "credit");
}

function autoFillAmount(
  billType: string,
  mode: string,
  debitBal: number,
  creditBal: number,
  due: number,
  oppositeDue: number
): string {
  if (billType === "purchase" && mode === "debit") {
    return String(Math.min(debitBal, due, oppositeDue));
  }
  if (billType === "sales" && mode === "credit") {
    return String(Math.min(creditBal, due, oppositeDue));
  }
  return "";
}

export default function PaymentPage({ billType: billTypeProp }: Props) {
  const { id: routeId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const billId = Number(routeId || searchParams.get("bill_id") || 0);

  const [bill, setBill] = useState<Bill | null>(null);
  const [setoffPreview, setSetoffPreview] = useState<SetoffPreview | null>(null);
  const [error, setError] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);
  const [form, setForm] = useState({ amount: "", payment_mode: "cash", bank_account_id: "" as number | "" });
  const [banks, setBanks] = useState<BankAccount[]>([]);

  const billType = billTypeProp ?? bill?.bill_type ?? "sales";
  const listPath = billType === "sales" ? "/sales-bills" : "/purchase-bills";

  useEffect(() => {
    if (!billId) {
      setError("Missing bill id");
      return;
    }
    api
      .get<Bill>(`/api/bills/${billId}`)
      .then((b) => {
        setBill(b);
        setForm({ amount: "", payment_mode: "cash", bank_account_id: "" });
      })
      .catch((e) => setError(e.message));
  }, [billId]);

  useEffect(() => {
    bankAccountsApi
      .list({ limit: 200, active: "true" })
      .then((p) => {
        setBanks(p.items);
        setForm((f) => {
          if (f.bank_account_id !== "") return f;
          const def = p.items.find((b) => b.is_default);
          return def ? { ...f, bank_account_id: def.id } : f;
        });
      })
      .catch(() => setBanks([]));
  }, []);

  const creditBal = Number(bill?.customer_credit_balance ?? 0);
  const debitBal = Number(bill?.customer_debit_balance ?? 0);
  const oppositeDue = Number(bill?.opposite_due_total ?? 0);
  const due = bill ? dueAmount(bill) : 0;

  const modes = useMemo(() => {
    if (!bill) return [] as { value: string; label: string }[];
    if (bill.bill_type === "purchase") {
      const m = [
        { value: "cash", label: "Cash" },
        { value: "bank", label: "Bank" },
      ];
      if (debitBal > 0 && oppositeDue > 0) m.push({ value: "debit", label: "Debit balance" });
      return m;
    }
    const m = [
      { value: "cash", label: "Cash" },
      { value: "bank", label: "Bank" },
    ];
    if (creditBal > 0 && oppositeDue > 0) m.push({ value: "credit", label: "Credit balance" });
    return m;
  }, [bill, creditBal, debitBal, oppositeDue]);

  useEffect(() => {
    if (!bill || !modes.length) return;
    if (!modes.some((m) => m.value === form.payment_mode)) {
      const nextMode = modes[0].value;
      setForm((f) => ({
        ...f,
        payment_mode: nextMode,
        amount: autoFillAmount(bill.bill_type, nextMode, debitBal, creditBal, due, oppositeDue),
      }));
    }
  }, [modes, bill, debitBal, creditBal, due, oppositeDue, form.payment_mode]);

  const balanceMode = bill ? isBalanceMode(bill.bill_type, form.payment_mode) : false;
  const amountReadOnly = balanceMode;

  useEffect(() => {
    if (!bill || !balanceMode) {
      setSetoffPreview(null);
      return;
    }
    const amt = Number(form.amount) || 0;
    const params = new URLSearchParams({
      bill_id: String(bill.id),
      amount: String(amt > 0 ? amt : 0),
      payment_mode: form.payment_mode,
    });
    api
      .get<SetoffPreview>(`/api/payments/setoff-preview?${params}`)
      .then(setSetoffPreview)
      .catch(() => setSetoffPreview(null));
  }, [bill, balanceMode, form.amount, form.payment_mode]);

  const onModeChange = (mode: string) => {
    if (!bill) return;
    setForm((f) => ({
      ...f,
      payment_mode: mode,
      amount: autoFillAmount(bill.bill_type, mode, debitBal, creditBal, due, oppositeDue),
    }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!bill) return;
    setError("");
    const amt = Number(form.amount);
    if (amt <= 0) {
      setError("Amount must be greater than zero");
      idemKeyRef.current = null;
      return;
    }
    if (amt > due) {
      setError(`Amount cannot exceed due (${formatInr(due)})`);
      idemKeyRef.current = null;
      return;
    }
    if (balanceMode) {
      const maxSetoff = Math.min(
        bill.bill_type === "purchase" ? debitBal : creditBal,
        due,
        oppositeDue
      );
      if (amt > maxSetoff) {
        setError(`Amount cannot exceed set-off limit (${formatInr(maxSetoff)})`);
        idemKeyRef.current = null;
        return;
      }
    }
    if (form.payment_mode === "bank" && form.bank_account_id === "") {
      setError("Choose a bank account for bank payments");
      idemKeyRef.current = null;
      return;
    }
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setError("");
      try {
        await api.post(
          "/api/payments",
          {
            bill_id: bill.id,
            amount: amt,
            payment_mode: form.payment_mode,
            bank_account_id: form.payment_mode === "bank" ? form.bank_account_id : null,
            expected_version: bill.version,
          },
          { headers: idempotencyHeaders(idemKeyRef.current!) }
        );
        idemKeyRef.current = null;
        toast.success("Payment recorded");
        navigate(listPath);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error";
        setError(msg);
        toast.error(msg);
      }
    });
  };

  if (!billId) {
    return (
      <Banner tone="warning">Open this page from a bill (Record payment).</Banner>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Payment"
        title="Record payment"
        subtitle={
          bill ? (
            <span className="inline-flex items-center gap-2">
              <span className="v2-mono font-medium">{bill.bill_number}</span>
              <span>·</span>
              <span>{bill.customer_name}</span>
              <PaymentPill status={bill.payment_status} />
            </span>
          ) : (
            "Loading bill…"
          )
        }
        actions={
          <Link to={listPath}>
            <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
              Back to bills
            </Button>
          </Link>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {bill && (
        <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <Card>
            <CardHeader title="Bill snapshot" subtitle="Read-only summary of money on this bill" />
            <CardBody className="grid grid-cols-2 gap-3 pt-0 sm:grid-cols-3">
              {[
                ["Final payable", formatInr(bill.grand_total)],
                ["Amount paid", formatInr(bill.amount_paid)],
                ["Amount due", formatInr(due)],
                ...(bill.bill_type === "purchase" && debitBal > 0 ? [["Customer debit balance", formatInr(debitBal)] as const] : []),
                ...(bill.bill_type === "sales" && creditBal > 0 ? [["Customer credit balance", formatInr(creditBal)] as const] : []),
                ...(oppositeDue > 0 ? [["Opposite bills due", formatInr(oppositeDue)] as const] : []),
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-line bg-surface-subtle px-3 py-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">{label}</p>
                  <p className="mt-0.5 v2-mono text-sm font-semibold text-ink">{value}</p>
                </div>
              ))}
            </CardBody>
          </Card>

          {due <= 0 ? (
            <Card>
              <CardBody>
                <EmptyState
                  icon={<IndianRupee />}
                  title="This bill is fully paid"
                  description="Nothing more to record. Voiding a payment elsewhere can reopen a balance."
                />
              </CardBody>
            </Card>
          ) : (
            <Card>
              <CardHeader title="New payment" subtitle="Backend validates set-off rules and limits." />
              <CardBody>
                <form onSubmit={submit} className="space-y-4">
                  <FormField label="Payment mode" required>
                    {({ id }) => (
                      <Select
                        id={id}
                        value={form.payment_mode}
                        onChange={(e) => onModeChange(e.target.value)}
                        required
                      >
                        {modes.map((m) => (
                          <option key={m.value} value={m.value}>
                            {m.label}
                          </option>
                        ))}
                      </Select>
                    )}
                  </FormField>
                  {form.payment_mode === "bank" && (
                    <FormField label="Bank account" required>
                      <Select
                        value={form.bank_account_id === "" ? "" : String(form.bank_account_id)}
                        onChange={(e) =>
                          setForm({ ...form, bank_account_id: e.target.value ? Number(e.target.value) : "" })
                        }
                        required
                      >
                        <option value="">Select bank…</option>
                        {banks.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.name}
                            {b.is_default ? " (default)" : ""}
                          </option>
                        ))}
                      </Select>
                    </FormField>
                  )}
                  <FormField
                    label={`Amount (max ${formatInr(due)})`}
                    required
                    hint={
                      amountReadOnly
                        ? "Auto-filled: min(balance, due, opposite bills due)."
                        : "Enter any amount up to the due."
                    }
                  >
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0.01}
                        max={due}
                        step="0.01"
                        suffix="₹"
                        value={form.amount}
                        placeholder="e.g. 5000.00"
                        readOnly={amountReadOnly}
                        disabled={amountReadOnly}
                        onChange={(e) => setForm({ ...form, amount: e.target.value })}
                        required
                      />
                    )}
                  </FormField>

                  {balanceMode && setoffPreview && setoffPreview.allocations.length > 0 && (
                    <div className={cn("rounded-xl border border-primary-200 bg-primary-50 p-3 dark:border-primary-800/60 dark:bg-primary-900/30")}>
                      <p className="text-xs font-semibold text-primary-700 dark:text-primary-200">Set-off allocation (FIFO)</p>
                      <ul className="mt-2 space-y-1 text-sm">
                        {setoffPreview.allocations.map((row) => (
                          <li key={row.bill_id} className="flex items-center justify-between">
                            <span className="v2-mono text-ink">{row.bill_number}</span>
                            <span className="v2-mono font-semibold text-primary-700 dark:text-primary-200">
                              {formatInr(row.amount)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <Button type="submit" size="lg" block loading={submitting} disabled={submitDisabled} leftIcon={<IndianRupee className="h-4 w-4" />}>
                    {submitting ? "Saving…" : "Submit payment"}
                  </Button>
                </form>
              </CardBody>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
