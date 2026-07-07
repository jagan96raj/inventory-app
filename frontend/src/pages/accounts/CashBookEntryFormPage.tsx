import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Save, Trash2 } from "lucide-react";
import {
  bankAccountsApi,
  billsApi,
  cashBookApi,
  expenseCategoriesApi,
  newIdempotencyKey,
  type BankAccount,
  type BillPickerItem,
  type CashBookEntry,
  type CashBookEntryIn,
  type CashBookEntryType,
  type ExpenseCategory,
} from "../../api/client";
import { useSubmitGuard } from "../../hooks/useSubmitGuard";
import { usePermissions } from "../../lib/permissions";
import { formatDateTime, formatInr, localIsoDate, validateDateNotFuture } from "../../lib/format";
import { isAuthPasswordError, isBackdatedDate } from "../../lib/backdateAuth";
import BusinessDateField from "../../components/ui/BusinessDateField";
import BackdateAuthDialog from "../../components/ui/BackdateAuthDialog";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Banner from "../../components/ui/Banner";
import { Card, CardBody, CardFooter, CardHeader } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import Input from "../../components/ui/Input";
import NumberInput from "../../components/ui/NumberInput";
import Select from "../../components/ui/Select";
import SegmentedControl from "../../components/ui/SegmentedControl";
import Textarea from "../../components/ui/Textarea";
import VoidConfirmDialog from "../../components/ui/VoidConfirmDialog";
import { toast } from "../../components/ui/Toaster";

type Mode = "cash" | "bank";
type PaymentMode = Mode | "";

const FREIGHT_CATEGORY_NAME = "Freight Charges";

const TRANSFER_CATEGORY_NAME = "Cash <-> Bank Transfer";

function findCategoryByName(categories: ExpenseCategory[], name: string): ExpenseCategory | undefined {
  const target = name.toLowerCase();
  return categories.find((c) => c.name.toLowerCase() === target);
}

function transferCategoryId(categories: ExpenseCategory[]): number | "" {
  const named = findCategoryByName(categories, TRANSFER_CATEGORY_NAME);
  if (named) return named.id;
  return categories[0]?.id ?? "";
}

function isFreightExpense(entryType: CashBookEntryType, category: ExpenseCategory | undefined): boolean {
  return entryType === "expense" && category?.name.toLowerCase() === FREIGHT_CATEGORY_NAME.toLowerCase();
}

type FormState = {
  entry_type: CashBookEntryType;
  category_id: number | "";
  amount: string;
  description: string;
  reference_no: string;
  bill_id: number | "";
  source_mode: PaymentMode;
  source_bank_id: number | "";
  dest_mode: PaymentMode;
  dest_bank_id: number | "";
  entry_date: string;
};

function blankState(initial?: Partial<FormState>): FormState {
  return {
    entry_type: "expense",
    category_id: "",
    amount: "",
    description: "",
    reference_no: "",
    bill_id: "",
    source_mode: "",
    source_bank_id: "",
    dest_mode: "bank",
    dest_bank_id: "",
    entry_date: localIsoDate(),
    ...initial,
  };
}

function pickDefaultBank(banks: BankAccount[]): number | "" {
  const def = banks.find((b) => b.is_default && b.is_active);
  if (def) return def.id;
  const first = banks.find((b) => b.is_active);
  return first ? first.id : "";
}

export default function CashBookEntryFormPage() {
  const navigate = useNavigate();
  const { canVoid } = usePermissions();
  const { id: idParam } = useParams<{ id?: string }>();
  const editing = !!idParam;
  const entryId = idParam ? Number(idParam) : null;

  const [searchParams] = useSearchParams();
  const typeParam = (searchParams.get("type") as CashBookEntryType | null) ?? null;
  const billIdParam = searchParams.get("bill_id");
  const categoryParam = searchParams.get("category");

  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [banks, setBanks] = useState<BankAccount[]>([]);
  const [billSearch, setBillSearch] = useState("");
  const [billOptions, setBillOptions] = useState<BillPickerItem[]>([]);
  const [selectedBillLabel, setSelectedBillLabel] = useState("");
  const [error, setError] = useState("");
  const [voidAuthError, setVoidAuthError] = useState("");
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidBusy, setVoidBusy] = useState(false);
  const { submitting: busy, guardedSubmit, submitDisabled } = useSubmitGuard();
  const [original, setOriginal] = useState<CashBookEntry | null>(null);
  const voidIdemRef = useRef<string | null>(null);

  const [state, setState] = useState<FormState>(() =>
    blankState({
      entry_type: typeParam ?? "expense",
      bill_id: billIdParam ? Number(billIdParam) : "",
    })
  );
  const idemRef = useRef<string | null>(null);

  // Load masters
  useEffect(() => {
    bankAccountsApi
      .list({ limit: 200, active: "all" })
      .then((p) => {
        setBanks(p.items);
        setState((prev) => {
          if (prev.entry_type !== "transfer") return prev;
          const next = { ...prev };
          if (next.source_mode === "bank" && next.source_bank_id === "") {
            next.source_bank_id = pickDefaultBank(p.items);
          }
          if (next.dest_mode === "bank" && next.dest_bank_id === "") {
            next.dest_bank_id = pickDefaultBank(p.items);
          }
          return next;
        });
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    expenseCategoriesApi
      .list({ limit: 200, active: "true", kind: state.entry_type })
      .then((p) => {
        setCategories(p.items);
        setState((prev) => {
          if (editing && !original) return prev;
          if (
            editing &&
            original &&
            original.entry_type === prev.entry_type &&
            p.items.some((c) => c.id === prev.category_id)
          ) {
            return prev;
          }
          if (prev.entry_type === "transfer") {
            return { ...prev, category_id: transferCategoryId(p.items) };
          }
          const fromParam =
            !editing && prev.entry_type === "expense" && categoryParam
              ? findCategoryByName(p.items, categoryParam)?.id ?? ""
              : "";
          const category = p.items.find((c) => c.id === fromParam);
          const keepBill =
            isFreightExpense(prev.entry_type, category) &&
            (prev.bill_id !== "" || (!editing && billIdParam));
          return {
            ...prev,
            category_id: fromParam,
            bill_id: keepBill
              ? prev.bill_id !== ""
                ? prev.bill_id
                : billIdParam
                  ? Number(billIdParam)
                  : ""
              : "",
          };
        });
      })
      .catch((e) => setError(e.message));
  }, [state.entry_type, categoryParam, editing, original, billIdParam]);

  useEffect(() => {
    if (!editing || entryId == null) return;
    cashBookApi
      .get(entryId)
      .then((entry) => {
        setOriginal(entry);
        setState({
          entry_type: entry.entry_type,
          category_id: entry.category_id,
          amount: entry.amount,
          description: entry.description ?? "",
          reference_no: entry.reference_no ?? "",
          bill_id: entry.bill_id ?? "",
          source_mode: (entry.source_payment_mode ?? "cash") as Mode,
          source_bank_id: entry.source_bank_account_id ?? "",
          dest_mode: (entry.dest_payment_mode ?? "bank") as Mode,
          dest_bank_id: entry.dest_bank_account_id ?? "",
        });
        if (entry.bill_id && entry.bill_number) {
          setSelectedBillLabel(entry.bill_number);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [editing, entryId]);

  // Bill picker live search
  useEffect(() => {
    const t = setTimeout(() => {
      billsApi
        .picker({ limit: 20, search: billSearch || undefined })
        .then((p) => setBillOptions(p.items))
        .catch(() => setBillOptions([]));
    }, 250);
    return () => clearTimeout(t);
  }, [billSearch]);

  const setType = useCallback(
    (t: CashBookEntryType) => {
      setBillSearch("");
      setSelectedBillLabel("");
      setState((prev) => {
        const next = blankState({
          entry_type: t,
          description: prev.description,
          reference_no: prev.reference_no,
          amount: prev.amount,
          bill_id: "",
          category_id: "",
          source_mode: "",
          source_bank_id: "",
        });
        if (t === "transfer") {
          next.source_mode = "cash";
          next.dest_mode = "bank";
          next.dest_bank_id = pickDefaultBank(banks);
        }
        return next;
      });
    },
    [banks]
  );

  const selectedCategory = useMemo(
    () => categories.find((c) => c.id === state.category_id),
    [categories, state.category_id]
  );

  const showBillLink = isFreightExpense(state.entry_type, selectedCategory);

  const payload = useMemo<CashBookEntryIn | null>(() => {
    if (state.category_id === "" || !state.amount) return null;
    const amount = Number(state.amount);
    if (!isFinite(amount) || amount <= 0) return null;
    const base: CashBookEntryIn = {
      entry_type: state.entry_type,
      category_id: Number(state.category_id),
      amount: state.amount,
      description: state.description.trim() || null,
      reference_no: state.reference_no.trim() || null,
      bill_id:
        showBillLink && state.bill_id !== "" ? Number(state.bill_id) : null,
    };
    if (state.entry_type === "transfer") {
      base.source_payment_mode = state.source_mode;
      base.source_bank_account_id = state.source_mode === "bank" ? (state.source_bank_id === "" ? null : Number(state.source_bank_id)) : null;
      base.dest_payment_mode = state.dest_mode;
      base.dest_bank_account_id = state.dest_mode === "bank" ? (state.dest_bank_id === "" ? null : Number(state.dest_bank_id)) : null;
      const sameCash = state.source_mode === "cash" && state.dest_mode === "cash";
      const sameBank =
        state.source_mode === "bank" &&
        state.dest_mode === "bank" &&
        state.source_bank_id === state.dest_bank_id &&
        state.source_bank_id !== "";
      if (sameCash || sameBank) return null;
    } else {
      if (state.source_mode === "") return null;
      base.source_payment_mode = state.source_mode;
      base.source_bank_account_id =
        state.source_mode === "bank"
          ? state.source_bank_id === ""
            ? null
            : Number(state.source_bank_id)
          : null;
      if (state.source_mode === "bank" && base.source_bank_account_id == null) return null;
    }
    if (!editing) {
      base.entry_date = state.entry_date;
    }
    return base;
  }, [state, showBillLink, editing]);

  const saveEntry = async (authorizationPassword?: string) => {
    if (!payload) return;
    if (!idemRef.current) idemRef.current = newIdempotencyKey();
    if (editing && original) {
      await cashBookApi.update(original.id, { ...payload, expected_version: original.version }, idemRef.current);
      toast.success("Entry updated");
    } else {
      await cashBookApi.create(payload, idemRef.current, authorizationPassword);
      toast.success("Entry recorded");
    }
    idemRef.current = null;
    navigate("/accounts/cashbook");
  };

  const onSubmit = async () => {
    if (!payload) {
      setError("Fill all required fields. Transfers must have different source and destination.");
      return;
    }
    if (!editing) {
      const dateError = validateDateNotFuture(state.entry_date);
      if (dateError) {
        setError(dateError);
        return;
      }
    }
    setError("");
    if (!editing && isBackdatedDate(state.entry_date)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }
    if (!idemRef.current) idemRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      try {
        await saveEntry();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not save entry";
        setError(msg);
        toast.error(msg);
      }
    });
  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    await guardedSubmit(async () => {
      try {
        await saveEntry(authorizationPassword);
        setBackdateAuthOpen(false);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not save entry";
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

  const isVoided = Boolean(original?.voided_at);
  const canVoidEntry = editing && original && !isVoided && canVoid;

  const voidEntry = async (authorizationPassword: string) => {
    if (!original) return;
    if (!voidIdemRef.current) voidIdemRef.current = newIdempotencyKey();
    setVoidBusy(true);
    setVoidAuthError("");
    try {
      const voided = await cashBookApi.void(
        original.id,
        original.version,
        voidIdemRef.current,
        authorizationPassword
      );
      voidIdemRef.current = null;
      setOriginal(voided);
      setVoidOpen(false);
      toast.success("Entry voided — cash and bank balances have been reversed.");
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
      setVoidBusy(false);
    }
  };

  const billLabelFor = (b: BillPickerItem) =>
    `${b.bill_number} · ${b.bill_type === "sales" ? "Sales" : "Purchase"} · ${b.customer_name ?? "—"} · ${b.grand_total}`;

  return (
    <>
      <PageHeader
        eyebrow={editing ? "Cash book" : "Cash book"}
        title={editing ? "Edit cash-book entry" : "New cash-book entry"}
        subtitle={
          editing
            ? "Updates re-derive cash and bank balances. Entry date cannot be changed."
            : "Record a non-bill money movement. Date defaults to today; past dates allowed."
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {canVoidEntry && (
              <Button
                variant="danger"
                leftIcon={<Trash2 className="h-4 w-4" />}
                onClick={() => {
                  voidIdemRef.current = null;
                  setVoidAuthError("");
                  setVoidOpen(true);
                }}
              >
                Void entry
              </Button>
            )}
            <Button variant="ghost" leftIcon={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(-1)}>
              Back
            </Button>
          </div>
        }
      />

      {isVoided && original?.voided_at && (
        <Banner tone="warning" className="mb-4">
          This entry was voided on {formatDateTime(original.voided_at)}. It no longer affects cash or bank balances.
        </Banner>
      )}

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card>
        <CardHeader
          title="Entry details"
          actions={isVoided ? <Badge tone="danger">Voided</Badge> : undefined}
        />
        <CardBody className="space-y-5">
          <fieldset disabled={isVoided} className="space-y-5 disabled:opacity-70">
          <div>
            <SegmentedControl
              ariaLabel="Entry type"
              value={state.entry_type}
              onChange={(v) => setType(v as CashBookEntryType)}
              options={[
                { value: "expense", label: "Expense", hint: "Money out" },
                { value: "income", label: "Income", hint: "Money in" },
                { value: "transfer", label: "Transfer", hint: "Cash ↔ Bank" },
              ]}
            />
          </div>

          {!editing && (
            <BusinessDateField
              value={state.entry_date}
              onChange={(entry_date) => setState((prev) => ({ ...prev, entry_date }))}
            />
          )}
          {editing && original && (
            <FormField label="Entry date">
              <Input readOnly value={original.entry_date} />
            </FormField>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Amount (₹)" required>
              <NumberInput
                min={0}
                step="0.01"
                value={state.amount}
                onChange={(e) => setState({ ...state, amount: e.target.value })}
                placeholder="0.00"
              />
            </FormField>

            {state.entry_type !== "transfer" && (
              <FormField label="Category" required>
                <Select
                  value={state.category_id === "" ? "" : String(state.category_id)}
                  onChange={(e) => {
                    const category_id = e.target.value ? Number(e.target.value) : "";
                    const category = categories.find((c) => c.id === category_id);
                    const freight = isFreightExpense(state.entry_type, category);
                    setState((prev) => ({
                      ...prev,
                      category_id,
                      bill_id: freight ? prev.bill_id : "",
                    }));
                    if (!freight) {
                      setSelectedBillLabel("");
                      setBillSearch("");
                    }
                  }}
                >
                  <option value="">Select…</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </FormField>
            )}

            {state.entry_type === "transfer" && (
              <FormField label="Category" hint="System-managed for transfers">
                <Select value={state.category_id === "" ? "" : String(state.category_id)} disabled>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                  {state.category_id === "" && <option value="">Loading…</option>}
                </Select>
              </FormField>
            )}
          </div>

          {state.entry_type !== "transfer" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Payment mode" required>
                <Select
                  value={state.source_mode}
                  onChange={(e) => {
                    const mode = e.target.value as PaymentMode;
                    setState({
                      ...state,
                      source_mode: mode,
                      source_bank_id: "",
                    });
                  }}
                >
                  <option value="">Select…</option>
                  <option value="cash">Cash</option>
                  <option value="bank">Bank</option>
                </Select>
              </FormField>
              {state.source_mode === "bank" && (
                <FormField label="Bank account" required>
                  <Select
                    value={state.source_bank_id === "" ? "" : String(state.source_bank_id)}
                    onChange={(e) =>
                      setState({ ...state, source_bank_id: e.target.value ? Number(e.target.value) : "" })
                    }
                  >
                    <option value="">Select…</option>
                    {banks
                      .filter((b) => b.is_active || b.id === state.source_bank_id)
                      .map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                          {b.is_default ? " (default)" : ""}
                        </option>
                      ))}
                  </Select>
                </FormField>
              )}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-3 rounded-xl border border-line/70 bg-surface-subtle/50 p-3">
                <p className="text-sm font-semibold text-ink-muted">Source (debit)</p>
                <FormField label="From">
                  <Select
                    value={state.source_mode}
                    onChange={(e) => {
                      const mode = e.target.value as Mode;
                      setState({
                        ...state,
                        source_mode: mode,
                        source_bank_id: mode === "bank" ? pickDefaultBank(banks) : "",
                      });
                    }}
                  >
                    <option value="cash">Cash</option>
                    <option value="bank">Bank</option>
                  </Select>
                </FormField>
                {state.source_mode === "bank" && (
                  <FormField label="From bank">
                    <Select
                      value={state.source_bank_id === "" ? "" : String(state.source_bank_id)}
                      onChange={(e) =>
                        setState({ ...state, source_bank_id: e.target.value ? Number(e.target.value) : "" })
                      }
                    >
                      <option value="">Select…</option>
                      {banks
                        .filter((b) => b.is_active || b.id === state.source_bank_id)
                        .map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.name}
                          </option>
                        ))}
                    </Select>
                  </FormField>
                )}
              </div>
              <div className="space-y-3 rounded-xl border border-line/70 bg-surface-subtle/50 p-3">
                <p className="text-sm font-semibold text-ink-muted">Destination (credit)</p>
                <FormField label="To">
                  <Select
                    value={state.dest_mode}
                    onChange={(e) => {
                      const mode = e.target.value as Mode;
                      setState({
                        ...state,
                        dest_mode: mode,
                        dest_bank_id: mode === "bank" ? pickDefaultBank(banks) : "",
                      });
                    }}
                  >
                    <option value="cash">Cash</option>
                    <option value="bank">Bank</option>
                  </Select>
                </FormField>
                {state.dest_mode === "bank" && (
                  <FormField label="To bank">
                    <Select
                      value={state.dest_bank_id === "" ? "" : String(state.dest_bank_id)}
                      onChange={(e) =>
                        setState({ ...state, dest_bank_id: e.target.value ? Number(e.target.value) : "" })
                      }
                    >
                      <option value="">Select…</option>
                      {banks
                        .filter((b) => b.is_active || b.id === state.dest_bank_id)
                        .map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.name}
                          </option>
                        ))}
                    </Select>
                  </FormField>
                )}
              </div>
            </div>
          )}

          <div className={showBillLink ? "grid gap-4 sm:grid-cols-2" : ""}>
            <FormField label="Reference no." hint="Cheque, UTR, voucher…">
              <Input
                value={state.reference_no}
                onChange={(e) => setState({ ...state, reference_no: e.target.value })}
                maxLength={100}
              />
            </FormField>

            {showBillLink && (
              <FormField
                label="Link to bill (optional)"
                hint="Trace freight paid for a purchase bill (e.g. lorry charges for PUR-0042)"
              >
                <div className="space-y-2">
                  <Input
                    placeholder={
                      state.bill_id ? selectedBillLabel || `#${state.bill_id}` : "Search bill number / customer…"
                    }
                    value={billSearch}
                    onChange={(e) => setBillSearch(e.target.value)}
                  />
                  {(billOptions.length > 0 || state.bill_id) && (
                    <div className="max-h-40 overflow-auto rounded-lg border border-line/60 bg-surface-subtle/40">
                      {state.bill_id && (
                        <button
                          type="button"
                          className="block w-full px-3 py-1.5 text-left text-xs text-rose-600 hover:bg-surface-muted"
                          onClick={() => {
                            setState({ ...state, bill_id: "" });
                            setSelectedBillLabel("");
                          }}
                        >
                          Clear linked bill (currently {selectedBillLabel || `#${state.bill_id}`})
                        </button>
                      )}
                      {billOptions.map((b) => (
                        <button
                          key={b.id}
                          type="button"
                          className="block w-full px-3 py-1.5 text-left text-sm hover:bg-surface-muted"
                          onClick={() => {
                            setState({ ...state, bill_id: b.id });
                            setSelectedBillLabel(billLabelFor(b));
                            setBillSearch("");
                          }}
                        >
                          {billLabelFor(b)}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </FormField>
            )}
          </div>

          <FormField label="Description">
            <Textarea
              rows={2}
              maxLength={500}
              value={state.description}
              onChange={(e) => setState({ ...state, description: e.target.value })}
              placeholder="Notes for this entry"
            />
          </FormField>
          </fieldset>
        </CardBody>
        <CardFooter>
          <Button variant="ghost" onClick={() => navigate(-1)} disabled={busy || voidBusy}>
            {isVoided ? "Back to cash book" : "Cancel"}
          </Button>
          {!isVoided && (
            <Button onClick={onSubmit} disabled={submitDisabled || busy || !payload} loading={busy} leftIcon={<Save className="h-4 w-4" />}>
              {busy ? "Saving…" : editing ? "Save changes" : "Record entry"}
            </Button>
          )}
        </CardFooter>
      </Card>

      <VoidConfirmDialog
        open={voidOpen}
        onClose={() => {
          voidIdemRef.current = null;
          setVoidAuthError("");
          setVoidOpen(false);
        }}
        onConfirm={voidEntry}
        title="Void this cash-book entry?"
        description={
          original
            ? `Void this ${original.entry_type} of ${formatInr(original.amount)} — cash and bank balances will be reversed.`
            : ""
        }
        confirmLabel={voidBusy ? "Voiding…" : "Void entry"}
        authError={voidAuthError || undefined}
      />

      <BackdateAuthDialog
        open={backdateAuthOpen}
        onClose={() => setBackdateAuthOpen(false)}
        onConfirm={confirmBackdateAuth}
        dateLabel={state.entry_date}
        authError={backdateAuthError || undefined}
      />
    </>
  );
}
