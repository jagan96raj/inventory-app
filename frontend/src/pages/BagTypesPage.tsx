import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Box, Package, Plus, Scale, Sparkles, Trash2 } from "lucide-react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  idempotencyHeaders,
  newIdempotencyKey,
  voidAuthHeaders,
  type PageOut,
} from "../api/client";
import { formatBagTypeWeight } from "../lib/bagType";
import { cn } from "../lib/cn";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import NumberInput from "../components/ui/NumberInput";
import Banner from "../components/ui/Banner";
import EmptyState from "../components/ui/EmptyState";
import VoidConfirmDialog from "../components/ui/VoidConfirmDialog";
import Modal from "../components/ui/Modal";
import Skeleton from "../components/ui/Skeleton";
import PaginationBar from "../components/ui/PaginationBar";
import { toast } from "../components/ui/Toaster";
import { useSubmitGuard } from "../hooks/useSubmitGuard";

type BagType = { id: number; name: string; weight_per_bag_kg: string; is_loose: boolean };

const LIST_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-left text-base font-semibold uppercase tracking-wide text-ink-muted";
const LIST_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

export default function BagTypesPage() {
  const [rows, setRows] = useState<BagType[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [form, setForm] = useState({ name: "", weight_per_bag_kg: "", is_loose: false });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<BagType | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const createIdemRef = useRef<string | null>(null);
  const { guardedSubmit, submitDisabled } = useSubmitGuard();
  const limit = DEFAULT_PAGE_LIMIT;

  const load = () => {
    setLoading(true);
    api.get<PageOut<BagType>>(`/api/bag-types?limit=${limit}&offset=${offset}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [offset]);

  const baggedCount = useMemo(() => rows.filter((r) => !r.is_loose).length, [rows]);
  const looseCount = useMemo(() => rows.filter((r) => r.is_loose).length, [rows]);

  const reset = () => setForm({ name: "", weight_per_bag_kg: "", is_loose: false });

  const openAdd = () => {
    reset();
    setAddOpen(true);
  };

  const closeAdd = () => {
    setAddOpen(false);
    setConfirmOpen(false);
    reset();
  };

  const validateForm = () => {
    const isLoose = form.is_loose;
    const weight = isLoose ? 0 : Number(form.weight_per_bag_kg);
    if (!form.name.trim()) throw new Error("Name is required");
    if (!isLoose && (!weight || weight <= 0)) {
      throw new Error("Weight per bag must be greater than zero for bagged types");
    }
    return { isLoose, weight, name: form.name.trim() };
  };

  const openConfirm = (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      validateForm();
      setConfirmOpen(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      setError(msg);
      toast.error(msg);
    }
  };

  const createBagType = async () => {
    setError("");
    if (!createIdemRef.current) createIdemRef.current = newIdempotencyKey();
    await guardedSubmit(async () => {
      setSaving(true);
      try {
        const { isLoose, weight, name } = validateForm();
        await api.post(
          "/api/bag-types",
          { name, weight_per_bag_kg: weight, is_loose: isLoose },
          { headers: idempotencyHeaders(createIdemRef.current!) }
        );
        createIdemRef.current = null;
        toast.success("Bag type added");
        closeAdd();
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

  const onLooseChange = (checked: boolean) => {
    setForm((f) => ({
      ...f,
      is_loose: checked,
      weight_per_bag_kg: checked ? "0" : f.weight_per_bag_kg === "0" ? "" : f.weight_per_bag_kg,
      name: checked && !f.name.trim() ? "Loose" : f.name,
    }));
  };

  const remove = async (authorizationPassword: string) => {
    if (!pendingDelete) return;
    setError("");
    setVoidAuthError("");
    try {
      await api.delete(`/api/bag-types/${pendingDelete.id}`, {
        headers: voidAuthHeaders(authorizationPassword),
      });
      toast.success("Bag type deleted");
      setPendingDelete(null);
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

  const seed = async () => {
    try {
      const r = await api.post<{ created: string[] }>("/api/seed/bag-types", {});
      toast.success(`Seeded: ${r.created.join(", ") || "already present"}`);
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error";
      toast.error(msg);
    }
  };

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        title="Bag types"
        subtitle="Standard bag weights (50 / 30 / 25 kg) and loose-by-kg variants used across bills and inventory."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd} className="hidden sm:inline-flex">
              Add bag type
            </Button>
            <Button
              variant="secondary"
              leftIcon={<Sparkles className="h-4 w-4" />}
              onClick={() => void seed()}
            >
              <span className="sm:hidden">Seed</span>
              <span className="hidden sm:inline">Seed defaults</span>
            </Button>
          </div>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Card className="border-primary-200/70 bg-gradient-to-br from-primary-50/80 via-surface to-violet-50/40 dark:border-primary-800/40 dark:from-primary-950/35 dark:via-surface dark:to-violet-950/25">
          <CardBody className="flex items-center gap-4 p-5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-md">
              <Package className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-medium text-primary-700/80 dark:text-primary-300/80">Total types</p>
              <p className="text-3xl font-bold text-primary-900 dark:text-primary-50">{total}</p>
            </div>
          </CardBody>
        </Card>
        <Card className="border-line/80 bg-surface">
          <CardBody className="flex items-center gap-4 p-5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200">
              <Box className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-medium text-ink-muted">Bagged</p>
              <p className="text-3xl font-bold text-ink">{baggedCount}</p>
            </div>
          </CardBody>
        </Card>
        <Card className="border-sky-200/70 bg-gradient-to-br from-sky-50/60 via-surface to-surface dark:border-sky-800/40 dark:from-sky-950/25">
          <CardBody className="flex items-center gap-4 p-5">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200">
              <Scale className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-medium text-sky-800/80 dark:text-sky-300/80">Loose (by kg)</p>
              <p className="text-3xl font-bold text-sky-900 dark:text-sky-100">{looseCount}</p>
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="All bag types"
          subtitle="Weight and bagged/loose setting are fixed after creation."
        />
        {loading ? (
          <CardBody className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-xl" />
            ))}
          </CardBody>
        ) : total === 0 ? (
          <CardBody>
            <EmptyState
              icon={<Package className="h-8 w-8" />}
              title="No bag types yet"
              description="Seed defaults or add a bag type."
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAdd}>
                  Add bag type
                </Button>
              }
            />
          </CardBody>
        ) : (
          <>
            <div className="hidden overflow-x-auto lg:block">
              <table className="v2-data-table min-w-full w-full text-base">
                <caption className="sr-only">Bag types</caption>
                <thead>
                  <tr>
                    <th scope="col" className={LIST_TH}>
                      Name
                    </th>
                    <th scope="col" className={cn(LIST_TH, "text-right")}>
                      Weight
                    </th>
                    <th scope="col" className={LIST_TH}>
                      Type
                    </th>
                    <th scope="col" className={cn(LIST_TH, "text-right")}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      className={cn(
                        "border-l-4",
                        row.is_loose
                          ? "border-l-sky-500 bg-sky-50/40 dark:bg-sky-950/20 [&>td]:bg-sky-50/40 dark:[&>td]:bg-sky-950/20"
                          : "border-l-emerald-500 bg-emerald-50/35 dark:bg-emerald-950/20 [&>td]:bg-emerald-50/35 dark:[&>td]:bg-emerald-950/20"
                      )}
                    >
                      <td className={cn(LIST_TD, "font-semibold text-ink")}>{row.name}</td>
                      <td className={cn(LIST_TD, "v2-mono text-right font-semibold tabular-nums")}>
                        {formatBagTypeWeight(row)}
                      </td>
                      <td className={LIST_TD}>
                        {row.is_loose ? (
                          <Badge tone="info" size="md">
                            Loose
                          </Badge>
                        ) : (
                          <Badge tone="success" size="md">
                            Bagged
                          </Badge>
                        )}
                      </td>
                      <td className={cn(LIST_TD, "text-right")}>
                        <Button
                          size="sm"
                          variant="danger"
                          leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setPendingDelete(row)}
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="space-y-3 border-t border-line p-4 lg:hidden">
              {rows.map((row) => (
                <div
                  key={row.id}
                  className={cn(
                    "space-y-3 rounded-2xl border border-l-4 p-4",
                    row.is_loose
                      ? "border-line/80 border-l-sky-500 bg-sky-50/40 dark:bg-sky-950/20"
                      : "border-line/80 border-l-emerald-500 bg-emerald-50/35 dark:bg-emerald-950/20"
                  )}
                >
                  <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">{row.name}</p>
                      <p className="v2-mono mt-0.5 text-sm font-semibold tabular-nums text-ink">
                        {formatBagTypeWeight(row)}
                      </p>
                    </div>
                    {row.is_loose ? (
                      <Badge tone="info" size="md">
                        Loose
                      </Badge>
                    ) : (
                      <Badge tone="success" size="md">
                        Bagged
                      </Badge>
                    )}
                  </div>
                  <div className="border-t border-line/60 pt-3">
                    <Button
                      size="md"
                      variant="danger"
                      className="min-h-10 w-full sm:w-auto"
                      leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                      onClick={() => setPendingDelete(row)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
        <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="px-4" />
      </Card>

      <Modal
        open={addOpen}
        onClose={closeAdd}
        size="md"
        headerIcon={<Package className="h-5 w-5" />}
        title="Add bag type"
        description="Weight and bagged/loose setting are permanent after save. Review carefully."
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={closeAdd} disabled={saving} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button
              type="submit"
              form="add-bag-type-form"
              leftIcon={<Plus className="h-4 w-4" />}
              className="w-full sm:w-auto"
            >
              Review & add
            </Button>
          </div>
        }
      >
        <form id="add-bag-type-form" onSubmit={openConfirm} className="space-y-4">
          <FormField label="Name" required hint="Shown on bills and inventory">
            {({ id }) => (
              <Input
                id={id}
                value={form.name}
                placeholder={form.is_loose ? "Loose" : "e.g. 40kg"}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
            )}
          </FormField>
          <FormField
            label="Weight per bag (kg)"
            required={!form.is_loose}
            hint={form.is_loose ? "Zero for loose types" : "Cannot be changed after save"}
          >
            {({ id }) => (
              <NumberInput
                id={id}
                min={0}
                step="0.001"
                suffix="kg"
                value={form.is_loose ? "0" : form.weight_per_bag_kg}
                disabled={form.is_loose}
                onChange={(e) => setForm({ ...form, weight_per_bag_kg: e.target.value })}
                required={!form.is_loose}
              />
            )}
          </FormField>
          <label className="inline-flex min-h-[2.75rem] w-full cursor-pointer items-center gap-3 rounded-xl border border-line/80 bg-surface px-4 text-base text-ink">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line-strong text-primary-600 focus:ring-primary-500/50"
              checked={form.is_loose}
              onChange={(e) => onLooseChange(e.target.checked)}
            />
            <span>
              <span className="font-medium">Sold by kg</span>
              <span className="ml-2 text-sm text-ink-muted">Not counted in bags</span>
            </span>
          </label>
        </form>
      </Modal>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        size="md"
        headerIcon={<Package className="h-5 w-5" />}
        title="Confirm bag type"
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="ghost"
              onClick={() => setConfirmOpen(false)}
              disabled={saving}
              className="w-full sm:w-auto"
            >
              Cancel
            </Button>
            <Button
              loading={saving}
              disabled={saving || submitDisabled}
              onClick={() => void createBagType()}
              className="w-full sm:w-auto"
            >
              Confirm & create
            </Button>
          </div>
        }
      >
        <div className="space-y-4 text-base text-ink">
          <dl className="space-y-3 rounded-xl border border-line/80 bg-surface-muted/40 p-4">
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">Name</dt>
              <dd className="font-semibold text-ink">{form.name.trim() || "—"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">Weight</dt>
              <dd className="v2-mono font-semibold text-ink">
                {form.is_loose ? "Loose (sold by kg)" : `${form.weight_per_bag_kg} kg per bag`}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">Type</dt>
              <dd className="font-semibold text-ink">{form.is_loose ? "Loose" : "Bagged"}</dd>
            </div>
          </dl>
          <p className="text-sm leading-relaxed text-warning-800 dark:text-warning-200">
            Weight and bagged/loose setting cannot be changed after creation. If wrong, you must
            create a new bag type.
          </p>
        </div>
      </Modal>

      <VoidConfirmDialog
        open={!!pendingDelete}
        onClose={() => {
          setVoidAuthError("");
          setPendingDelete(null);
        }}
        onConfirm={remove}
        title="Delete this bag type?"
        description="Backend rejects deletion if bills, inventory, or operations reference it. Prefer keeping the row and adding a new bag type if the weight was wrong."
        confirmLabel="Delete"
        authError={voidAuthError || undefined}
      />

      <button
        type="button"
        onClick={openAdd}
        className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
        aria-label="Add bag type"
      >
        <Plus className="h-6 w-6" />
      </button>
    </div>
  );
}
