import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { DEFAULT_PAGE_LIMIT, newIdempotencyKey } from "../api/client";
import {
  buildMasterFormBody,
  deleteMasterRecord,
  isVoidAuthErrorMessage,
  loadMasterPage,
  saveMasterRecord,
} from "../lib/masterCrudApi";
import Button from "./ui/Button";
import PageHeader from "./ui/PageHeader";
import { Card, CardBody } from "./ui/Card";
import Input from "./ui/Input";
import Textarea from "./ui/Textarea";
import FormField from "./ui/FormField";
import EmptyState from "./ui/EmptyState";
import Banner from "./ui/Banner";
import VoidConfirmDialog from "./ui/VoidConfirmDialog";
import Modal from "./ui/Modal";
import PaginationBar from "./ui/PaginationBar";
import { toast } from "./ui/Toaster";
import { useSubmitGuard } from "../hooks/useSubmitGuard";

type Field = {
  key: string;
  label: string;
  type?: "text" | "number" | "textarea";
  hint?: string;
  optional?: boolean;
  wide?: boolean;
};

type Props<T extends { id: number }> = {
  title: string;
  subtitle?: string;
  path: string;
  fields: Field[];
  columns: { key: string; label: string; render?: (row: T) => string }[];
  getInitial?: () => Record<string, string | number>;
};

const OPTIONAL_KEYS = new Set([
  "address_line",
  "district",
  "state",
  "pin_code",
  "phone",
  "address",
]);

export default function MasterCrud<T extends { id: number }>({
  title,
  subtitle,
  path,
  fields,
  columns,
  getInitial,
}: Props<T>) {
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<Record<string, string | number>>({});
  const [editId, setEditId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<T | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const idemKeyRef = useRef<string | null>(null);
  const { guardedSubmit, submitDisabled } = useSubmitGuard();
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    loadMasterPage<T>(path, { limit, offset })
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message));
  }, [path, limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const reset = () => {
    setForm(getInitial?.() ?? Object.fromEntries(fields.map((f) => [f.key, ""])));
    setEditId(null);
  };

  const openAdd = () => {
    reset();
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    reset();
  };

  const isOptional = (f: Field) => f.optional || OPTIONAL_KEYS.has(f.key);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const body = buildMasterFormBody(fields, form, {
      editId,
    });
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setSaving(true);
      try {
        await saveMasterRecord(path, body, editId, idemKeyRef.current);
        idemKeyRef.current = null;
        toast.success(editId ? `${title} updated` : `${title} added`);
        closeForm();
        load();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error";
        setError(msg);
        toast.error(msg);
      } finally {
        setSaving(false);
      }
    });
  };

  const startEdit = (row: T) => {
    setEditId(row.id);
    const next: Record<string, string | number> = {};
    for (const f of fields) {
      const val = (row as Record<string, unknown>)[f.key];
      next[f.key] = val == null ? "" : (val as string | number);
    }
    setForm(next);
    setFormOpen(true);
  };

  const remove = async (authorizationPassword: string) => {
    if (!pendingDelete) return;
    setError("");
    setVoidAuthError("");
    try {
      await deleteMasterRecord(path, pendingDelete.id, authorizationPassword);
      if (editId === pendingDelete.id) closeForm();
      setPendingDelete(null);
      toast.success(`${title} deleted`);
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      if (isVoidAuthErrorMessage(msg)) {
        setVoidAuthError(msg);
      } else {
        setError(msg);
        toast.error(msg);
        setPendingDelete(null);
      }
      throw err;
    }
  };

  const addLabel = `Add ${title.toLowerCase().replace(/s$/, "")}`;

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd} className="hidden sm:inline-flex">
            {addLabel}
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card>
        {rows.length === 0 && total === 0 ? (
          <CardBody>
            <EmptyState
              title={`No ${title.toLowerCase()} yet`}
              description={`Add your first ${title.toLowerCase().slice(0, -1) || title.toLowerCase()} with the button above.`}
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
                  {addLabel}
                </Button>
              }
            />
          </CardBody>
        ) : (
          <>
            <div className="hidden overflow-x-auto lg:block">
              <table className="v2-data-table min-w-full text-base">
                <thead className="bg-surface-subtle text-base font-semibold uppercase tracking-wide text-ink-subtle">
                  <tr>
                    {columns.map((c) => (
                      <th key={c.key} className="px-5 py-3.5 text-left">
                        {c.label}
                      </th>
                    ))}
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      className={
                        editId === row.id
                          ? "border-t border-line/70 bg-primary-50/40 dark:bg-primary-900/20"
                          : "border-t border-line/70"
                      }
                    >
                      {columns.map((c) => (
                        <td key={c.key} className="px-5 py-4 text-ink">
                          {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? "")}
                        </td>
                      ))}
                      <td className="px-5 py-4 text-right">
                        <div className="inline-flex gap-1.5">
                          <Button
                            size="sm"
                            variant="ghost"
                            leftIcon={<Pencil className="h-3.5 w-3.5" />}
                            onClick={() => startEdit(row)}
                          >
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                            onClick={() => setPendingDelete(row)}
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
            <div className="space-y-3 p-4 lg:hidden">
              {rows.map((row) => {
                const primary = columns[0];
                const rest = columns.slice(1);
                const primaryValue = primary
                  ? primary.render
                    ? primary.render(row)
                    : String((row as Record<string, unknown>)[primary.key] ?? "")
                  : `#${row.id}`;
                return (
                  <div
                    key={row.id}
                    className={
                      editId === row.id
                        ? "space-y-3 rounded-2xl border border-primary-200/80 bg-primary-50/40 p-4 dark:border-primary-800 dark:bg-primary-900/20"
                        : "space-y-3 rounded-2xl border border-line/80 bg-surface p-4"
                    }
                  >
                    <p className="min-w-0 font-semibold text-ink">{primaryValue}</p>
                    {rest.length > 0 && (
                      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                        {rest.map((c) => (
                          <div key={c.key} className="min-w-0">
                            <dt className="text-ink-subtle">{c.label}</dt>
                            <dd className="truncate text-ink">
                              {c.render
                                ? c.render(row)
                                : String((row as Record<string, unknown>)[c.key] ?? "")}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    <div className="flex flex-wrap gap-2 border-t border-line/60 pt-3">
                      <Button
                        size="md"
                        variant="secondary"
                        className="min-h-10 flex-1 sm:flex-none"
                        leftIcon={<Pencil className="h-3.5 w-3.5" />}
                        onClick={() => startEdit(row)}
                      >
                        Edit
                      </Button>
                      <Button
                        size="md"
                        variant="danger"
                        className="min-h-10 flex-1 sm:flex-none"
                        leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                        onClick={() => setPendingDelete(row)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
        <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="px-4" />
      </Card>

      <Modal
        open={formOpen}
        onClose={closeForm}
        size={fields.some((f) => f.wide || f.type === "textarea") ? "lg" : "md"}
        title={editId ? `Edit ${title.toLowerCase().replace(/s$/, "")}` : addLabel}
        description={editId ? "Update the details below." : `Create a new ${title.toLowerCase().slice(0, -1) || title.toLowerCase()}.`}
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={closeForm} disabled={saving} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button
              type="submit"
              form="master-crud-form"
              loading={saving}
              disabled={saving || submitDisabled}
              className="w-full sm:w-auto"
            >
              {editId ? "Save changes" : addLabel}
            </Button>
          </div>
        }
      >
        <form id="master-crud-form" onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {fields.map((f) => (
              <FormField
                key={f.key}
                label={f.label}
                hint={f.hint}
                required={!isOptional(f)}
                className={f.wide || f.type === "textarea" ? "sm:col-span-2" : undefined}
              >
                {({ id }) =>
                  f.type === "textarea" ? (
                    <Textarea
                      id={id}
                      rows={3}
                      value={String(form[f.key] ?? "")}
                      onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      required={!isOptional(f)}
                    />
                  ) : (
                    <Input
                      id={id}
                      type={f.type === "number" ? "number" : "text"}
                      min={f.type === "number" ? 0 : undefined}
                      step={f.type === "number" ? "0.01" : undefined}
                      value={(form[f.key] ?? "") as string | number}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          [f.key]: f.type === "number" ? e.target.value : e.target.value,
                        })
                      }
                      required={!isOptional(f)}
                    />
                  )
                }
              </FormField>
            ))}
          </div>
        </form>
      </Modal>

      <VoidConfirmDialog
        open={!!pendingDelete}
        onClose={() => {
          setVoidAuthError("");
          setPendingDelete(null);
        }}
        onConfirm={remove}
        title={`Delete this ${title.toLowerCase().replace(/s$/, "")}?`}
        description="Only unused entries can be deleted. The backend will reject if it is referenced by bills, inventory, operations, or has a non-zero balance. Prefer edit/rename when possible."
        confirmLabel="Delete"
        authError={voidAuthError || undefined}
      />

      <button
        type="button"
        onClick={openAdd}
        className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
        aria-label={addLabel}
      >
        <Plus className="h-6 w-6" />
      </button>
    </div>
  );
}
