import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, IndianRupee } from "lucide-react";
import {
  api,
  bankAccountsApi,
  idempotencyHeadersOptionalAuth,
  newIdempotencyKey,
  type BankAccount,
  type Bill,
  type Payment,
  type SetoffPreview,
} from "../api/client";
import { accountsByKind, legacyFieldsFromAccount, pickDefaultMoneyAccountId } from "../lib/moneyAccounts";
import { isAuthPasswordError, isBackdatedDate } from "../lib/backdateAuth";
import { billDueAmount } from "../lib/billAmounts";
import BackdateAuthDialog from "../components/ui/BackdateAuthDialog";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { formatInr, localIsoDate, validateDateNotFuture } from "../lib/format";
import BusinessDateField from "../components/ui/BusinessDateField";
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

const SETOFF_DEBIT = "__debit__";
const SETOFF_CREDIT = "__credit__";

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

function sourceToPaymentFields(
  source: string,
  accounts: BankAccount[]
): { payment_mode: string; bank_account_id: number | null } | null {
  if (source === SETOFF_DEBIT) return { payment_mode: "debit", bank_account_id: null };
  if (source === SETOFF_CREDIT) return { payment_mode: "credit", bank_account_id: null };
  const account = accounts.find((a) => String(a.id) === source);
  if (!account) return null;
  const legacy = legacyFieldsFromAccount(account);
  return { payment_mode: legacy.mode, bank_account_id: legacy.bank_account_id };
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
  const [form, setForm] = useState({
    amount: "",
    source: "" as string,
    paid_date: localIsoDate(),
  });
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");
  const [billLoading, setBillLoading] = useState(false);
  const [billLoadError, setBillLoadError] = useState("");
  const billRequestIdRef = useRef(0);
  const previewRequestIdRef = useRef(0);

  const billType = billTypeProp ?? bill?.bill_type ?? "sales";
  const listPath = billType === "sales" ? "/sales-bills" : "/purchase-bills";
  const grouped = useMemo(() => accountsByKind(accounts), [accounts]);

  useEffect(() => {
    if (!billId) {
      setError("Missing bill id");
      setBill(null);
      return;
    }
    const requestId = ++billRequestIdRef.current;
    setBillLoading(true);
    setBillLoadError("");
    setBill(null);
    api
      .get<Bill>(`/api/bills/${billId}`)
      .then((b) => {
        if (billRequestIdRef.current !== requestId) return;
        setBill(b);
        setForm((f) => ({
          amount: "",
          source: f.source,
          paid_date: localIsoDate(),
        }));
      })
      .catch((e) => {
        if (billRequestIdRef.current !== requestId) return;
        setBill(null);
        setBillLoadError(e.message);
      })
      .finally(() => {
        if (billRequestIdRef.current === requestId) setBillLoading(false);
      });
  }, [billId]);

  useEffect(() => {
    bankAccountsApi
      .list({ limit: 200, active: "true", kind: "all" })
      .then((p) => {
        setAccounts(p.items);
        setForm((f) => {
          if (f.source !== "") return f;
          const def = pickDefaultMoneyAccountId(p.items);
          return def !== "" ? { ...f, source: String(def) } : f;
        });
      })
      .catch(() => setAccounts([]));
  }, []);

  const creditBal = Number(bill?.customer_credit_balance ?? 0);
  const debitBal = Number(bill?.customer_debit_balance ?? 0);
  const oppositeDue = Number(bill?.opposite_due_total ?? 0);
  const due = bill ? billDueAmount(bill) : 0;

  const paymentFields = useMemo(
    () => (form.source ? sourceToPaymentFields(form.source, accounts) : null),
    [form.source, accounts]
  );
  const paymentMode = paymentFields?.payment_mode ?? "";
  const balanceMode = bill ? isBalanceMode(bill.bill_type, paymentMode) : false;
  const amountReadOnly = balanceMode;

  useEffect(() => {
    if (!bill || !balanceMode) {
      setSetoffPreview(null);
      return;
    }
    const requestId = ++previewRequestIdRef.current;
    const amt = Number(form.amount) || 0;
    const params = new URLSearchParams({
      bill_id: String(bill.id),
      amount: String(amt > 0 ? amt : 0),
      payment_mode: paymentMode,
    });
    api
      .get<SetoffPreview>(`/api/payments/setoff-preview?${params}`)
      .then((preview) => {
        if (previewRequestIdRef.current !== requestId) return;
        setSetoffPreview(preview);
      })
      .catch(() => {
        if (previewRequestIdRef.current !== requestId) return;
        setSetoffPreview(null);
      });
  }, [bill, balanceMode, form.amount, paymentMode]);

  const onSourceChange = (source: string) => {
    if (!bill) return;
    const fields = sourceToPaymentFields(source, accounts);
    const mode = fields?.payment_mode ?? "cash";
    setForm((f) => ({
      ...f,
      source,
      amount: autoFillAmount(bill.bill_type, mode, debitBal, creditBal, due, oppositeDue),
    }));
  };

  const postPayment = async (authorizationPassword?: string) => {
    if (!bill || !idemKeyRef.current || !paymentFields) return;
    const amt = Number(form.amount);
    await api.post<Payment>(
      "/api/payments",
      {
        bill_id: bill.id,
        amount: amt,
        payment_mode: paymentFields.payment_mode,
        bank_account_id: paymentFields.bank_account_id,
        expected_version: bill.version,
        paid_date: form.paid_date,
      },
      { headers: idempotencyHeadersOptionalAuth(idemKeyRef.current, authorizationPassword) }
    );
    idemKeyRef.current = null;
    toast.success("Payment recorded");
    navigate(listPath);
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
    if (!paymentFields) {
      setError("Choose an account for this payment");
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
    const dateError = validateDateNotFuture(form.paid_date);
    if (dateError) {
      setError(dateError);
      idemKeyRef.current = null;
      return;
    }
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    if (isBackdatedDate(form.paid_date)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }
    await guardedSubmit(async () => {
      setError("");
      try {
        await postPayment();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error";
        setError(msg);
        toast.error(msg);
      }
    });
  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    await guardedSubmit(async () => {
      try {
        await postPayment(authorizationPassword);
        setBackdateAuthOpen(false);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error";
        if (isAuthPasswordError(msg)) {
          setBackdateAuthError(msg);
        } else {
          setError(msg);
          toast.error(msg);
          setBackdateAuthOpen(false);
        }
        throw err;
      }
    });
  };

  const showDebit = Boolean(bill && bill.bill_type === "purchase" && debitBal > 0 && oppositeDue > 0);
  const showCredit = Boolean(bill && bill.bill_type === "sales" && creditBal > 0 && oppositeDue > 0);

  return (
    <>
      <PageHeader
        eyebrow={billType === "sales" ? "Sales" : "Purchase"}
        title="Record payment"
        subtitle={bill ? `Bill ${bill.bill_number}` : "Loading…"}
        actions={
          <Button variant="ghost" leftIcon={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(listPath)}>
            Back to bills
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {billLoadError && (
        <Banner tone="danger" className="mb-4">
          {billLoadError}
        </Banner>
      )}

      {bill && !billLoading ? (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
          <Card>
            <CardHeader title="Bill summary" />
            <CardBody className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-ink-muted">Customer</span>
                <span className="font-medium text-ink">{bill.customer_name ?? "—"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-ink-muted">Grand total</span>
                <span className="v2-mono font-semibold">{formatInr(bill.grand_total)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-ink-muted">Amount due</span>
                <span className="v2-mono font-semibold text-primary-700 dark:text-primary-200">{formatInr(due)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-ink-muted">Status</span>
                <PaymentPill status={bill.payment_status} />
              </div>
              <p className="pt-2 text-xs text-ink-subtle">
                <Link className="text-primary-600 hover:underline" to={`${listPath}/${bill.id}`}>
                  Open bill detail
                </Link>
              </p>
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
              <CardHeader title="New payment" subtitle="Pick the Cash or Bank account (or a set-off balance)." />
              <CardBody>
                <form onSubmit={submit} className="space-y-4">
                  <BusinessDateField
                    value={form.paid_date}
                    onChange={(paid_date) => setForm((f) => ({ ...f, paid_date }))}
                  />
                  <FormField label="Paid from" required>
                    {({ id }) => (
                      <Select id={id} value={form.source} onChange={(e) => onSourceChange(e.target.value)} required>
                        <option value="">Select account…</option>
                        {grouped.cash.length > 0 && (
                          <optgroup label="Cash">
                            {grouped.cash.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {grouped.bank.length > 0 && (
                          <optgroup label="Bank">
                            {grouped.bank.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name}
                                {a.is_default ? " (default)" : ""}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {(showDebit || showCredit) && (
                          <optgroup label="Set-off">
                            {showDebit && <option value={SETOFF_DEBIT}>Debit balance</option>}
                            {showCredit && <option value={SETOFF_CREDIT}>Credit balance</option>}
                          </optgroup>
                        )}
                      </Select>
                    )}
                  </FormField>
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
                    <div
                      className={cn(
                        "rounded-xl border border-primary-200 bg-primary-50 p-3 dark:border-primary-800/60 dark:bg-primary-900/30"
                      )}
                    >
                      <p className="text-xs font-semibold text-primary-700 dark:text-primary-200">
                        Set-off allocation (FIFO)
                      </p>
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

                  <Button
                    type="submit"
                    size="lg"
                    block
                    loading={submitting}
                    disabled={submitDisabled}
                    leftIcon={<IndianRupee className="h-4 w-4" />}
                  >
                    {submitting ? "Saving…" : "Submit payment"}
                  </Button>
                </form>
              </CardBody>
            </Card>
          )}
        </div>
      ) : (
        !billLoadError && (
          <Card>
            <CardBody>
              <p className="text-sm text-ink-muted">Loading bill…</p>
            </CardBody>
          </Card>
        )
      )}

      <BackdateAuthDialog
        open={backdateAuthOpen}
        onClose={() => setBackdateAuthOpen(false)}
        onConfirm={confirmBackdateAuth}
        dateLabel={form.paid_date}
        authError={backdateAuthError || undefined}
      />
    </>
  );
}
