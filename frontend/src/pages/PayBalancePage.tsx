import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, IndianRupee } from "lucide-react";
import {
  api,
  bankAccountsApi,
  idempotencyHeadersOptionalAuth,
  newIdempotencyKey,
  type BankAccount,
  type Customer,
  type CustomerPayBalanceOut,
  type CustomerPayBalancePreview,
} from "../api/client";
import { accountsByKind, pickDefaultMoneyAccountId } from "../lib/moneyAccounts";
import { isAuthPasswordError, isBackdatedDate } from "../lib/backdateAuth";
import BackdateAuthDialog from "../components/ui/BackdateAuthDialog";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { formatInr, localIsoDate, validateDateNotFuture } from "../lib/format";
import { formatCustomerName } from "../lib/customerDisplay";
import BusinessDateField from "../components/ui/BusinessDateField";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import FormField from "../components/ui/FormField";
import NumberInput from "../components/ui/NumberInput";
import Select from "../components/ui/Select";
import Banner from "../components/ui/Banner";
import EmptyState from "../components/ui/EmptyState";
import { toast } from "../components/ui/Toaster";

type Direction = "debit" | "credit";

type Props = { direction: Direction };

export default function PayBalancePage({ direction }: Props) {
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const customerId = Number(routeId || 0);

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [preview, setPreview] = useState<CustomerPayBalancePreview | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);
  const previewRequestIdRef = useRef(0);
  const [form, setForm] = useState({
    amount: "",
    source: "" as string,
    paid_date: localIsoDate(),
  });
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");

  const grouped = useMemo(() => accountsByKind(accounts), [accounts]);
  const title = direction === "debit" ? "Pay debit" : "Pay credit";
  const balanceLabel =
    direction === "debit" ? "Debit balance (they owe)" : "Credit balance (I owe)";

  const balance = customer
    ? Number(direction === "debit" ? customer.debit_balance : customer.credit_balance)
    : 0;
  const maxAmount = preview ? Number(preview.max_amount) : balance;
  const accountId = form.source ? Number(form.source) : 0;

  useEffect(() => {
    if (!customerId) {
      setLoadError("Missing customer id");
      setCustomer(null);
      return;
    }
    setLoading(true);
    setLoadError("");
    api
      .get<Customer>(`/api/customers/${customerId}`)
      .then((c) => {
        setCustomer(c);
        setForm((f) => ({ ...f, amount: "", paid_date: localIsoDate() }));
      })
      .catch((e) => {
        setCustomer(null);
        setLoadError(e.message);
      })
      .finally(() => setLoading(false));
  }, [customerId]);

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

  useEffect(() => {
    if (!customerId || balance <= 0) {
      setPreview(null);
      return;
    }
    const requestId = ++previewRequestIdRef.current;
    const amt = Number(form.amount) || 0;
    const params = new URLSearchParams({
      direction,
      amount: String(amt > 0 ? amt : 0),
    });
    api
      .get<CustomerPayBalancePreview>(
        `/api/customers/${customerId}/pay-balance-preview?${params}`
      )
      .then((data) => {
        if (previewRequestIdRef.current !== requestId) return;
        setPreview(data);
      })
      .catch(() => {
        if (previewRequestIdRef.current !== requestId) return;
        setPreview(null);
      });
  }, [customerId, direction, form.amount, balance]);

  const postPay = async (authorizationPassword?: string) => {
    if (!idemKeyRef.current || !accountId) return;
    const amt = Number(form.amount);
    await api.post<CustomerPayBalanceOut>(
      `/api/customers/${customerId}/pay-balance`,
      {
        direction,
        amount: amt,
        account_id: accountId,
        paid_date: form.paid_date,
      },
      { headers: idempotencyHeadersOptionalAuth(idemKeyRef.current, authorizationPassword) }
    );
    idemKeyRef.current = null;
    toast.success(direction === "debit" ? "Debit paid" : "Credit paid");
    navigate("/customers");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const amt = Number(form.amount);
    if (!(amt > 0)) {
      setError("Amount must be greater than zero");
      idemKeyRef.current = null;
      return;
    }
    if (amt > maxAmount) {
      setError(`Amount cannot exceed ${formatInr(maxAmount)}`);
      idemKeyRef.current = null;
      return;
    }
    if (!accountId) {
      setError("Choose a cash or bank account");
      idemKeyRef.current = null;
      return;
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
        await postPay();
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
        await postPay(authorizationPassword);
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

  return (
    <>
      <PageHeader
        eyebrow="Customers"
        title={title}
        subtitle={
          customer
            ? `${formatCustomerName(customer.name)} · ${balanceLabel} ${formatInr(balance)}`
            : "Loading…"
        }
        actions={
          <Button
            variant="ghost"
            leftIcon={<ArrowLeft className="h-4 w-4" />}
            onClick={() => navigate("/customers")}
          >
            <span className="sm:hidden">Back</span>
            <span className="hidden sm:inline">Back to customers</span>
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {loadError && (
        <Banner tone="danger" className="mb-4">
          {loadError}
        </Banner>
      )}

      {customer && !loading ? (
        balance <= 0 ? (
          <Card>
            <CardBody>
              <EmptyState
                icon={<IndianRupee />}
                title={direction === "debit" ? "No debit balance" : "No credit balance"}
                description="Nothing to pay for this customer in this direction."
              />
            </CardBody>
          </Card>
        ) : (
          <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
            <Card className="min-w-0">
              <CardHeader title="Customer" />
              <CardBody className="space-y-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="shrink-0 text-ink-muted">Name</span>
                  <span className="min-w-0 truncate text-right font-medium text-ink">
                    {formatCustomerName(customer.name)}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="shrink-0 text-ink-muted">{balanceLabel}</span>
                  <span className="v2-mono font-semibold text-primary-700 dark:text-primary-200">
                    {formatInr(balance)}
                  </span>
                </div>
                {preview && (
                  <>
                    <div className="flex justify-between gap-3">
                      <span className="shrink-0 text-ink-muted">Open bill dues</span>
                      <span className="v2-mono">{formatInr(preview.open_due_total)}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="shrink-0 text-ink-muted">Max payable</span>
                      <span className="v2-mono font-semibold">{formatInr(preview.max_amount)}</span>
                    </div>
                  </>
                )}
                <p className="pt-2 text-xs text-ink-subtle">
                  Cash/bank only. Amount is allocated FIFO across open{" "}
                  {direction === "debit" ? "sales" : "purchase"} bills (oldest first).
                </p>
              </CardBody>
            </Card>

            <Card className="min-w-0">
              <CardHeader
                title={title}
                subtitle="Pick Cash or Bank. No set-off on this page."
              />
              <CardBody>
                <form onSubmit={submit} className="space-y-4">
                  <BusinessDateField
                    value={form.paid_date}
                    onChange={(paid_date) => setForm((f) => ({ ...f, paid_date }))}
                  />
                  <FormField label="Paid from" required>
                    {({ id }) => (
                      <Select
                        id={id}
                        value={form.source}
                        onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
                        required
                      >
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
                      </Select>
                    )}
                  </FormField>
                  <FormField
                    label={`Amount (max ${formatInr(maxAmount)})`}
                    required
                    hint="Leave empty until you type. Must be greater than zero and at most the balance / open dues."
                  >
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0.01}
                        max={maxAmount}
                        step="0.01"
                        suffix="₹"
                        value={form.amount}
                        placeholder="e.g. 5000.00"
                        onChange={(e) => setForm({ ...form, amount: e.target.value })}
                        required
                      />
                    )}
                  </FormField>

                  {preview && preview.allocations.length > 0 && (
                    <div className="rounded-xl border border-line bg-surface-muted/50 p-3">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-subtle">
                        FIFO allocation preview
                      </p>
                      <ul className="space-y-1.5 text-sm">
                        {preview.allocations.map((a) => (
                          <li
                            key={a.bill_id}
                            className="flex items-center justify-between gap-3"
                          >
                            <span className="min-w-0 truncate text-ink">{a.bill_number}</span>
                            <span className="v2-mono shrink-0">{formatInr(a.amount)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => navigate("/customers")}
                      disabled={submitting}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" loading={submitting} disabled={submitting || submitDisabled}>
                      {title}
                    </Button>
                  </div>
                </form>
              </CardBody>
            </Card>
          </div>
        )
      ) : null}

      <BackdateAuthDialog
        open={backdateAuthOpen}
        onClose={() => {
          setBackdateAuthOpen(false);
          setBackdateAuthError("");
        }}
        onConfirm={confirmBackdateAuth}
        authError={backdateAuthError || undefined}
        dateLabel={form.paid_date}
      />
    </>
  );
}
