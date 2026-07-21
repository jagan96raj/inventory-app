import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import {
  expenseCategoriesApi,
  DEFAULT_PAGE_LIMIT,
  newIdempotencyKey,
  type ExpenseCategory,
  type ExpenseCategoryIn,
  type ExpenseCategoryKind,
  type ExpenseCategoryUpdateIn,
} from "../../api/client";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import { Card, CardBody } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import Input from "../../components/ui/Input";
import Modal from "../../components/ui/Modal";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import { toast } from "../../components/ui/Toaster";
import { useSubmitGuard } from "../../hooks/useSubmitGuard";

type FormState = { name: string; kind: ExpenseCategoryKind; is_active: boolean };
const empty: FormState = { name: "", kind: "expense", is_active: true };

export default function ExpenseCategoriesMasterPage() {
  const [rows, setRows] = useState<ExpenseCategory[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [activeFilter, setActiveFilter] = useState<"true" | "false" | "all">("all");
  const [kindFilter, setKindFilter] = useState<ExpenseCategoryKind | "">("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<ExpenseCategory | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<FormState>(empty);
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ExpenseCategory | null>(null);
  const saveIdemRef = useRef<string | null>(null);
  const { guardedSubmit, submitDisabled } = useSubmitGuard();
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    expenseCategoriesApi
      .list({ limit, offset, active: activeFilter, kind: kindFilter || undefined })
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

  const openAdd = () => {
    setForm(empty);
    setAdding(true);
  };

  const openEdit = (c: ExpenseCategory) => {
    if (c.is_system) {
      toast.error("System categories cannot be edited");
      return;
    }
    setForm({ name: c.name, kind: c.kind, is_active: c.is_active });
    setEditing(c);
  };

  const close = () => {
    setAdding(false);
    setEditing(null);
    setForm(empty);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setError("");
    if (!saveIdemRef.current) saveIdemRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setBusy(true);
      try {
        if (editing) {
          const body: ExpenseCategoryUpdateIn = { name: form.name.trim(), is_active: form.is_active };
          await expenseCategoriesApi.update(editing.id, body, saveIdemRef.current!);
          toast.success("Category updated");
        } else {
          const body: ExpenseCategoryIn = { name: form.name.trim(), kind: form.kind };
          await expenseCategoriesApi.create(body, saveIdemRef.current!);
          toast.success("Category added");
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
      await expenseCategoriesApi.remove(pendingDelete.id);
      toast.success("Category deleted");
      setPendingDelete(null);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not delete";
      setError(msg);
      toast.error(msg);
      setPendingDelete(null);
    }
  };

  const kindTone: Record<ExpenseCategoryKind, "danger" | "success" | "info"> = {
    expense: "danger",
    income: "success",
    transfer: "info",
  };

  return (
    <>
      <PageHeader
        eyebrow="Accounts"
        title="Expense categories"
        subtitle="Buckets used by Cash Book entries. System categories (lock icon) cannot be edited or deleted."
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
            Add category
          </Button>
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
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Kind</label>
            <Select value={kindFilter} onChange={(e) => setKindFilter(e.target.value as ExpenseCategoryKind | "")}>
              <option value="">All</option>
              <option value="expense">Expense</option>
              <option value="income">Income</option>
              <option value="transfer">Transfer</option>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Status</label>
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
              title="No categories"
              description="Add an expense or income category to organise cash-book entries."
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
                  Add category
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
                  <th className="px-5 py-3.5 text-left">Kind</th>
                  <th className="px-5 py-3.5 text-left">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="border-t border-line/70">
                    <td className="px-5 py-4 font-semibold text-ink">
                      <span className="inline-flex items-center gap-2">
                        {c.is_system && <Lock className="h-3.5 w-3.5 text-ink-subtle" aria-label="System category" />}
                        {c.name}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <Badge tone={kindTone[c.kind]} size="sm">
                        {c.kind}
                      </Badge>
                    </td>
                    <td className="px-5 py-4">
                      {c.is_active ? <Badge tone="success" size="sm">Active</Badge> : <Badge tone="neutral" size="sm">Inactive</Badge>}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="inline-flex gap-1.5">
                        <Button
                          size="sm"
                          variant="ghost"
                          leftIcon={<Pencil className="h-3.5 w-3.5" />}
                          onClick={() => openEdit(c)}
                          disabled={c.is_system}
                          title={c.is_system ? "System category" : undefined}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setPendingDelete(c)}
                          disabled={c.is_system}
                          title={c.is_system ? "System category" : undefined}
                        >
                          Delete
                        </Button>
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
        title={editing ? "Edit category" : "Add category"}
        size="md"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="cat-form"
              loading={busy}
              disabled={busy || submitDisabled}
              leftIcon={<CheckCircle2 className="h-4 w-4" />}
            >
              {editing ? "Save changes" : "Add"}
            </Button>
          </div>
        }
      >
        <form id="cat-form" onSubmit={submit} className="space-y-4">
          <FormField label="Name" required>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Rent"
              maxLength={120}
            />
          </FormField>
          {!editing && (
            <FormField label="Kind" required hint="Transfer kind is system-managed and cannot be created here">
              <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ExpenseCategoryKind })}>
                <option value="expense">Expense (money out)</option>
                <option value="income">Income (money in)</option>
              </Select>
            </FormField>
          )}
          {editing && (
            <label className="inline-flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-line-strong text-primary-600 focus:ring-primary-500/50"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              />
              Active
            </label>
          )}
        </form>
      </Modal>

      <ConfirmDialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        onConfirm={remove}
        tone="danger"
        title="Delete this category?"
        description="Soft-deletes the category. Rejected if any cash-book entry references it."
        confirmLabel="Delete"
      />
    </>
  );
}
