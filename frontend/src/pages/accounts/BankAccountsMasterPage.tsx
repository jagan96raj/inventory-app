import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Pencil, Plus, Star, Trash2 } from "lucide-react";
import {
  bankAccountsApi,
  DEFAULT_PAGE_LIMIT,
  newIdempotencyKey,
  type BankAccount,
  type BankAccountBalance,
  type BankAccountIn,
  type BankAccountKind,
  type BankAccountUpdateIn,
} from "../../api/client";
import { accountKindLabel } from "../../lib/moneyAccounts";
import { formatDate, formatInr } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import { Card, CardBody } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import IconButton from "../../components/ui/IconButton";
import Input from "../../components/ui/Input";
import NumberInput from "../../components/ui/NumberInput";
import Modal from "../../components/ui/Modal";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import { toast } from "../../components/ui/Toaster";
import { useSubmitGuard } from "../../hooks/useSubmitGuard";

type FormState = {
  kind: BankAccountKind;
  name: string;
  account_number_last4: string;
  ifsc: string;
  opening_balance: string;
  is_default: boolean;
  is_active: boolean;
};

const empty: FormState = {
  kind: "bank",
  name: "",
  account_number_last4: "",
  ifsc: "",
  opening_balance: "0",
  is_default: false,
  is_active: true,
};

export default function BankAccountsMasterPage() {
  const [rows, setRows] = useState<BankAccountBalance[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [activeFilter, setActiveFilter] = useState<"true" | "false" | "all">("all");
  const [kindFilter, setKindFilter] = useState<"all" | "cash" | "bank">("all");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<BankAccount | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<FormState>(empty);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<BankAccount | null>(null);
  const saveIdemRef = useRef<string | null>(null);
  const { guardedSubmit, submitDisabled } = useSubmitGuard();
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    bankAccountsApi
      .list({ limit, offset, active: activeFilter, kind: kindFilter })
      .then((p) => {
        setRows(p.items);
        setTotal(p.total);
      })
      .catch((e) => setError(e.message));
  }, [limit, offset, activeFilter, kindFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [activeFilter, kindFilter]);

  const openAdd = (kind: BankAccountKind = "bank") => {
    setForm({
      ...empty,
      kind,
      name: kind === "cash" ? "Cash" : "",
    });
    setAdding(true);
  };

  const openEdit = (b: BankAccount) => {
    setForm({
      kind: b.kind ?? "bank",
      name: b.name,
      account_number_last4: b.account_number_last4 ?? "",
      ifsc: b.ifsc ?? "",
      opening_balance: b.opening_balance,
      is_default: b.is_default,
      is_active: b.is_active,
    });
    setEditing(b);
  };

  const close = () => {
    setAdding(false);
    setEditing(null);
    setForm(empty);
  };

  const isCash = (editing?.kind ?? form.kind) === "cash";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setError("");
    if (!saveIdemRef.current) saveIdemRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setBusy(true);
      try {
        if (editing) {
          const body: BankAccountUpdateIn = {
            name: form.name.trim(),
            is_active: form.is_active,
          };
          if (editing.kind === "cash") {
            body.opening_balance = form.opening_balance || "0";
          } else {
            body.account_number_last4 = form.account_number_last4.trim() || null;
            body.ifsc = form.ifsc.trim() || null;
          }
          await bankAccountsApi.update(editing.id, body, saveIdemRef.current!);
          toast.success(editing.kind === "cash" ? "Cash account updated" : "Bank account updated");
        } else {
          const body: BankAccountIn =
            form.kind === "cash"
              ? {
                  name: form.name.trim() || "Cash",
                  kind: "cash",
                  opening_balance: form.opening_balance || "0",
                  is_default: false,
                }
              : {
                  name: form.name.trim(),
                  kind: "bank",
                  account_number_last4: form.account_number_last4.trim() || null,
                  ifsc: form.ifsc.trim() || null,
                  opening_balance: form.opening_balance || "0",
                  is_default: form.is_default,
                };
          await bankAccountsApi.create(body, saveIdemRef.current!);
          toast.success(form.kind === "cash" ? "Cash account added" : "Bank account added");
        }
        saveIdemRef.current = null;
        close();
        load();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not save";
        setError(msg);
        toast.error(msg);
      } finally {
        setBusy(false);
      }
    });
  };

  const remove = async () => {
    if (!pendingDelete) return;
    try {
      await bankAccountsApi.remove(pendingDelete.id);
      toast.success("Account deleted");
      setPendingDelete(null);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not delete";
      setError(msg);
      toast.error(msg);
      setPendingDelete(null);
    }
  };

  const makeDefault = async (b: BankAccount) => {
    try {
      await bankAccountsApi.makeDefault(b.id, newIdempotencyKey());
      toast.success(`${b.name} is now the default bank`);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not set default";
      setError(msg);
      toast.error(msg);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Accounts"
        title="Money accounts"
        subtitle="Cash and bank accounts in one list. Opening balances and live closing balances drive the Accounts dashboard."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" leftIcon={<Plus className="h-4 w-4" />} onClick={() => openAdd("cash")}>
              Add Cash
            </Button>
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => openAdd("bank")}>
              Add Bank
            </Button>
          </div>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card className="mb-4">
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Type</label>
            <Select value={kindFilter} onChange={(e) => setKindFilter(e.target.value as "all" | "cash" | "bank")}>
              <option value="all">All</option>
              <option value="cash">Cash</option>
              <option value="bank">Bank</option>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Show</label>
            <Select value={activeFilter} onChange={(e) => setActiveFilter(e.target.value as "true" | "false" | "all")}>
              <option value="all">All</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </Select>
          </div>
        </CardBody>
      </Card>

      <Card>
        {rows.length === 0 && total === 0 ? (
          <CardBody>
            <EmptyState
              title="No money accounts"
              description="Add a Cash or Bank account to record payments and cash book movements."
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => openAdd("bank")}>
                  Add Bank
                </Button>
              }
            />
          </CardBody>
        ) : (
          <div className="overflow-x-auto">
            <table className="v2-data-table w-full text-base">
              <thead className="bg-surface-muted/70 text-base font-semibold uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-5 py-3.5 text-left">Name</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-left">Type</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-left">A/C ending</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-left">IFSC</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-right">Opening balance</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-right">Closing balance</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-left">Opening date</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-left">Status</th>
                  <th className="whitespace-nowrap px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id} className="border-t border-line/70">
                    <td className="px-5 py-4 font-semibold text-ink">{b.name}</td>
                    <td className="whitespace-nowrap px-5 py-4">
                      <Badge tone={b.kind === "cash" ? "info" : "neutral"} size="sm">
                        {accountKindLabel(b.kind ?? "bank")}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 v2-mono text-ink-muted">
                      {b.kind === "bank" && b.account_number_last4 ? `••${b.account_number_last4}` : "—"}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 v2-mono text-ink-muted">
                      {b.kind === "bank" ? b.ifsc ?? "—" : "—"}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-right v2-mono tabular-nums">{formatInr(b.opening_balance)}</td>
                    <td className="whitespace-nowrap px-5 py-4 text-right v2-mono tabular-nums font-semibold text-ink">{formatInr(b.balance)}</td>
                    <td className="whitespace-nowrap px-5 py-4 text-ink-muted">{formatDate(b.opening_balance_at)}</td>
                    <td className="px-5 py-4">
                      <div className="flex flex-wrap gap-1.5">
                        {b.is_default && b.kind === "bank" ? <Badge tone="primary" size="sm">Default</Badge> : null}
                        {b.is_active ? <Badge tone="success" size="sm">Active</Badge> : <Badge tone="neutral" size="sm">Inactive</Badge>}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="inline-flex items-center justify-end gap-0.5">
                        {b.kind === "bank" && !b.is_default && b.is_active ? (
                          <IconButton
                            label="Make default"
                            size="sm"
                            variant="outline"
                            onClick={() => void makeDefault(b)}
                          >
                            <Star />
                          </IconButton>
                        ) : null}
                        <IconButton label="Edit account" size="sm" variant="outline" onClick={() => openEdit(b)}>
                          <Pencil />
                        </IconButton>
                        <IconButton
                          label={
                            b.kind === "cash"
                              ? "Cannot delete Cash"
                              : b.is_default
                                ? "Cannot delete the default bank"
                                : "Delete account"
                          }
                          size="sm"
                          onClick={() => setPendingDelete(b)}
                          disabled={b.kind === "cash" || b.is_default}
                          className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 disabled:hover:bg-transparent dark:text-rose-400 dark:hover:bg-rose-950/40"
                        >
                          <Trash2 />
                        </IconButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="px-4" />
      </Card>

      <Modal
        open={adding || !!editing}
        onClose={close}
        title={
          editing
            ? editing.kind === "cash"
              ? "Edit Cash account"
              : "Edit bank account"
            : form.kind === "cash"
              ? "Add Cash account"
              : "Add bank account"
        }
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="money-account-form"
              loading={busy}
              disabled={busy || submitDisabled}
              leftIcon={<CheckCircle2 className="h-4 w-4" />}
            >
              {editing ? "Save changes" : isCash ? "Add Cash" : "Add Bank"}
            </Button>
          </div>
        }
      >
        <form id="money-account-form" onSubmit={submit} className="space-y-4">
          {!editing && (
            <FormField label="Type" required>
              <Select
                value={form.kind}
                onChange={(e) => {
                  const kind = e.target.value as BankAccountKind;
                  setForm({
                    ...form,
                    kind,
                    name: kind === "cash" ? form.name || "Cash" : form.name === "Cash" ? "" : form.name,
                    is_default: kind === "cash" ? false : form.is_default,
                    account_number_last4: kind === "cash" ? "" : form.account_number_last4,
                    ifsc: kind === "cash" ? "" : form.ifsc,
                  });
                }}
              >
                <option value="cash">Cash</option>
                <option value="bank">Bank</option>
              </Select>
            </FormField>
          )}
          <FormField label="Name" required>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={isCash ? "Cash" : "e.g. HDFC Current"}
              maxLength={120}
            />
          </FormField>
          {!isCash && (
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="A/C number (last 4)" hint="Optional">
                <Input
                  value={form.account_number_last4}
                  onChange={(e) =>
                    setForm({ ...form, account_number_last4: e.target.value.replace(/\D/g, "").slice(0, 4) })
                  }
                  placeholder="1234"
                  maxLength={4}
                />
              </FormField>
              <FormField label="IFSC" hint="Optional">
                <Input
                  value={form.ifsc}
                  onChange={(e) => setForm({ ...form, ifsc: e.target.value.toUpperCase() })}
                  placeholder="HDFC0000123"
                  maxLength={20}
                />
              </FormField>
            </div>
          )}
          {(adding || isCash) && (
            <FormField
              label="Opening balance (₹)"
              hint={isCash ? "Used for cash totals on the Accounts dashboard" : "Cannot be changed after creation"}
            >
              <NumberInput
                min={0}
                step="0.01"
                value={form.opening_balance}
                onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
                readOnly={Boolean(editing && editing.kind === "bank")}
                disabled={Boolean(editing && editing.kind === "bank")}
              />
            </FormField>
          )}
          {adding && form.kind === "bank" && (
            <label className="inline-flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-line-strong text-primary-600 focus:ring-primary-500/50"
                checked={form.is_default}
                onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              />
              Make this the default bank (others will be cleared)
            </label>
          )}
          {editing && editing.kind === "bank" && (
            <label className="inline-flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-line-strong text-primary-600 focus:ring-primary-500/50"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                disabled={editing.is_default}
              />
              Active {editing.is_default && <span className="text-xs text-ink-subtle">(default bank stays active)</span>}
            </label>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={remove}
        tone="danger"
        title="Delete this account?"
        description="Soft-deletes the bank. Rejected if any payment or cash-book entry references it. Cash cannot be deleted."
        confirmLabel="Delete"
      />
    </>
  );
}
