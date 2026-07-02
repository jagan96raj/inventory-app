import { FormEvent, useCallback, useEffect, useState, type ReactNode } from "react";
import { MapPin, Pencil, Plus, Trash2, User } from "lucide-react";
import { api, DEFAULT_PAGE_LIMIT, voidAuthHeaders, type PageOut } from "../api/client";
import { formatInr } from "../lib/format";

function apiPath(path: string): string {
  return path.startsWith("/api") ? path : `/api${path}`;
}
import Button from "./ui/Button";
import IconButton from "./ui/IconButton";
import PageHeader from "./ui/PageHeader";
import { Card, CardBody } from "./ui/Card";
import Input from "./ui/Input";
import Textarea from "./ui/Textarea";
import FormField from "./ui/FormField";
import EmptyState from "./ui/EmptyState";
import Banner from "./ui/Banner";
import VoidConfirmDialog from "./ui/VoidConfirmDialog";
import Modal from "./ui/Modal";
import Badge from "./ui/Badge";
import PaginationBar from "./ui/PaginationBar";
import { toast } from "./ui/Toaster";

export type PartyField = {
  key: string;
  label: string;
  type?: "text" | "number" | "textarea";
  hint?: string;
  optional?: boolean;
  wide?: boolean;
  section?: "basic" | "address" | "contact" | "balances";
  placeholder?: string;
  /** Editable only when creating a new record; read-only on edit. */
  createOnly?: boolean;
};

type PartyKind = "customer" | "location";

const KIND_META: Record<
  PartyKind,
  { addTitle: string; editTitle: string; formHint: string; listTitle: string; addButton: string }
> = {
  customer: {
    addTitle: "Add customer",
    editTitle: "Edit customer",
    formHint: "Buyers and suppliers you bill or pay.",
    listTitle: "All customers",
    addButton: "Add customer",
  },
  location: {
    addTitle: "Add location",
    editTitle: "Edit location",
    formHint: "Warehouse, mill, or godown where stock is stored.",
    listTitle: "All locations",
    addButton: "Add location",
  },
};

const SECTION_LABELS: Record<string, string> = {
  basic: "Basic details",
  address: "Address",
  contact: "Contact",
  balances: "Opening balances",
};

const OPTIONAL_KEYS = new Set([
  "address_line",
  "district",
  "state",
  "pin_code",
  "phone",
  "alternate_phone",
  "credit_balance",
  "debit_balance",
]);

type Props<T extends { id: number }> = {
  title: string;
  subtitle?: string;
  path: string;
  kind: PartyKind;
  fields: PartyField[];
  columns: { key: string; label: string; render?: (row: T) => ReactNode }[];
  getInitial?: () => Record<string, string | number>;
  /** Enable name/phone search (customers list API). */
  searchable?: boolean;
};

export default function PartyMasterCrud<T extends { id: number }>({
  title,
  subtitle,
  path,
  kind,
  fields,
  columns,
  getInitial,
  searchable = false,
}: Props<T>) {
  const meta = KIND_META[kind];
  const Icon = kind === "customer" ? User : MapPin;
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState<Record<string, string | number>>({});
  const [editId, setEditId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<T | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  useEffect(() => {
    if (!searchable) return;
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(t);
  }, [search, searchable]);

  useEffect(() => {
    if (searchable) setOffset(0);
  }, [debouncedSearch, searchable]);

  const load = useCallback(() => {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (searchable && debouncedSearch) params.set("search", debouncedSearch);
    api.get<PageOut<T>>(`${apiPath(path)}?${params}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message));
  }, [path, limit, offset, searchable, debouncedSearch]);

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

  const isOptional = (f: PartyField) => f.optional || OPTIONAL_KEYS.has(f.key);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const body: Record<string, unknown> = {};
    for (const f of fields) {
      if (editId && f.createOnly) continue;
      const v = form[f.key];
      if (f.optional && (v === "" || v === undefined)) {
        if (f.type === "number") body[f.key] = 0;
        else body[f.key] = null;
        continue;
      }
      body[f.key] = f.type === "number" ? Number(v) : v;
    }
    setSaving(true);
    try {
      if (editId) {
        await api.put(`${apiPath(path)}/${editId}`, body);
        toast.success(`${kind === "customer" ? "Customer" : "Location"} updated`);
      } else {
        await api.post(apiPath(path), body);
        toast.success(`${kind === "customer" ? "Customer" : "Location"} added`);
      }
      closeForm();
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
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
      await api.delete(`${apiPath(path)}/${pendingDelete.id}`, {
        headers: voidAuthHeaders(authorizationPassword),
      });
      if (editId === pendingDelete.id) closeForm();
      setPendingDelete(null);
      toast.success("Deleted");
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidAuthError(msg);
      } else {
        setError(msg);
        toast.error(msg);
        setPendingDelete(null);
      }
      throw err;
    }
  };

  const sections = ["basic", "address", "contact", "balances"].filter((s) =>
    fields.some((f) => (f.section ?? "basic") === s)
  );

  const renderField = (f: PartyField) => {
    const readOnlyOnEdit = Boolean(editId && f.createOnly);
    const span = f.wide || f.type === "textarea" ? "sm:col-span-2" : undefined;
    if (readOnlyOnEdit) {
      return (
        <div key={f.key} className={span}>
          <p className="text-xs font-medium text-ink-muted">{f.label}</p>
          {f.hint && <p className="text-[11px] text-ink-subtle">{f.hint}</p>}
          <div className="mt-1 rounded-xl border border-line bg-surface-muted px-3 py-2 text-sm v2-mono text-ink-muted">
            {f.type === "number" ? formatInr(form[f.key] ?? 0) : String(form[f.key] ?? "—")}
          </div>
        </div>
      );
    }
    return (
      <FormField
        key={f.key}
        label={f.label}
        hint={f.hint}
        required={!isOptional(f)}
        className={span}
      >
        {({ id }) =>
          f.type === "textarea" ? (
            <Textarea
              id={id}
              rows={3}
              placeholder={f.placeholder}
              value={String(form[f.key] ?? "")}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              required={!isOptional(f)}
            />
          ) : (
            <Input
              id={id}
              type={f.type === "number" ? "number" : "text"}
              placeholder={f.placeholder}
              min={f.type === "number" ? 0 : undefined}
              step={f.type === "number" ? "0.01" : undefined}
              value={(form[f.key] ?? "") as string | number}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              required={!isOptional(f)}
            />
          )
        }
      </FormField>
    );
  };

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
            {meta.addButton}
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card>
        <div className="flex flex-col gap-3 border-b border-line px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold text-ink">{meta.listTitle}</h3>
          <div className="flex flex-wrap items-center gap-2">
            {searchable && (
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search name or phone…"
                className="w-full min-w-[12rem] sm:w-56"
              />
            )}
            <Badge tone="muted" size="sm">
              {total} total
            </Badge>
          </div>
        </div>
        {rows.length === 0 && total === 0 ? (
          <CardBody>
            <EmptyState
              icon={<Icon />}
              title={`No ${kind === "customer" ? "customers" : "locations"} yet`}
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
                  {meta.addButton}
                </Button>
              }
            />
          </CardBody>
        ) : (
          <div className="overflow-x-auto border-t border-line">
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
                      <div className="inline-flex items-center justify-end gap-0.5">
                        <IconButton
                          label={kind === "customer" ? "Edit customer" : "Edit location"}
                          size="sm"
                          variant="outline"
                          onClick={() => startEdit(row)}
                        >
                          <Pencil />
                        </IconButton>
                        <IconButton
                          label={kind === "customer" ? "Delete customer" : "Delete location"}
                          size="sm"
                          onClick={() => setPendingDelete(row)}
                          className="text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:text-rose-400 dark:hover:bg-rose-950/40"
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
        open={formOpen}
        onClose={closeForm}
        size="lg"
        headerIcon={<Icon className="h-5 w-5" />}
        title={editId ? meta.editTitle : meta.addTitle}
        description={meta.formHint}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={closeForm} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="party-master-form" loading={saving}>
              {editId ? "Save changes" : meta.addButton}
            </Button>
          </div>
        }
      >
        <form id="party-master-form" onSubmit={submit} className="space-y-6">
          {sections.map((section) => (
            <fieldset key={section} className="space-y-3">
              <legend className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">
                {SECTION_LABELS[section]}
              </legend>
              {section === "address" && (
                <p className="text-xs text-ink-subtle">Optional — helps on bills and inventory labels.</p>
              )}
              {section === "balances" && kind === "customer" && !editId && (
                <p className="text-xs text-ink-subtle">
                  Opening balance only — can change later only via bills and payments.
                </p>
              )}
              {section === "balances" && kind === "customer" && editId && (
                <p className="text-xs text-ink-subtle">
                  Balances are read-only here. They change through bills and payments.
                </p>
              )}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {fields.filter((f) => (f.section ?? "basic") === section).map(renderField)}
              </div>
            </fieldset>
          ))}
        </form>
      </Modal>

      <VoidConfirmDialog
        open={!!pendingDelete}
        onClose={() => {
          setVoidAuthError("");
          setPendingDelete(null);
        }}
        onConfirm={remove}
        title={`Delete this ${kind}?`}
        description="Only unused entries can be deleted. The backend will reject if it is referenced by bills, inventory, operations, or has a non-zero balance. Prefer edit/rename when possible."
        confirmLabel="Delete"
        authError={voidAuthError || undefined}
      />
    </>
  );
}
