import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Link2, Lock, PackagePlus, Plus } from "lucide-react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  idempotencyHeaders,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type PageOut,
} from "../api/client";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import {
  searchBagTypes,
  searchBrands,
  searchCustomers,
  searchLocations,
  searchProducts,
  type MasterComboOption,
} from "../lib/masterSearch";
import {
  InventoryDetailView,
  InventorySummaryView,
  isLowStock,
} from "../components/inventory/InventoryStockViews";
import { calcPreviewTotalKg, isLooseBagType } from "../lib/bagType";
import { formatQtyKg } from "../lib/format";
import {
  groupInventoryRows,
  type InvRow,
} from "../lib/inventoryGrouping";
import {
  readCollapsedLocationIds,
  readInventoryViewMode,
  writeCollapsedLocationIds,
  writeInventoryViewMode,
  type InventoryViewMode,
} from "../lib/inventoryViewPrefs";
import {
  clearQtyOnBagTypeChange,
  emptyQtyFields,
  PH_BAGS,
  PH_LOOSE_KG,
  parseBagCount,
  parseLooseKg,
} from "../lib/qtyInput";
import { formatAddressMultiline } from "../lib/address";
import PageHeader from "../components/ui/PageHeader";
import Banner from "../components/ui/Banner";
import Button from "../components/ui/Button";
import FormField from "../components/ui/FormField";
import Select from "../components/ui/Select";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import NumberInput from "../components/ui/NumberInput";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import Modal from "../components/ui/Modal";
import PaginationBar from "../components/ui/PaginationBar";
import SegmentedControl from "../components/ui/SegmentedControl";
import Stat from "../components/ui/Stat";
import Input from "../components/ui/Input";

type Inv = InvRow & {
  location_address_line?: string | null;
  location_district?: string | null;
  location_state?: string | null;
  location_pin_code?: string | null;
};

type InventoryUsageLink = {
  key: string;
  label: string;
  count: number;
  hint?: string | null;
};

type InventoryUsage = {
  inventory_id: number;
  links: InventoryUsageLink[];
  has_activity: boolean;
};

const emptyForm = () => ({
  product_id: "",
  brand_id: "",
  location_id: "",
  bag_type_id: "",
  ...emptyQtyFields(),
});

type MasterLabels = {
  location: string;
  product: string;
  brand: string;
  bagType: string;
};

const emptyMasterLabels = (): MasterLabels => ({
  location: "",
  product: "",
  brand: "",
  bagType: "",
});

function compareInventoryRows(a: Inv, b: Inv): number {
  const byText = (x?: string | null, y?: string | null) =>
    (x ?? "").localeCompare(y ?? "", undefined, { sensitivity: "base", numeric: true });

  let c = byText(a.location_name, b.location_name);
  if (c !== 0) return c;
  c = a.location_id - b.location_id;
  if (c !== 0) return c;

  const aJw = a.owner_type === "job_work";
  const bJw = b.owner_type === "job_work";
  if (aJw !== bJw) return aJw ? 1 : -1;
  if (aJw && bJw) {
    c = byText(a.customer_name, b.customer_name);
    if (c !== 0) return c;
    c = (a.customer_id ?? 0) - (b.customer_id ?? 0);
    if (c !== 0) return c;
  }

  c = byText(a.product_name, b.product_name);
  if (c !== 0) return c;
  c = byText(a.brand_name, b.brand_name);
  if (c !== 0) return c;
  return byText(a.bag_type_name, b.bag_type_name);
}

function rowLocationAddress(r: Inv): string {
  const formatted = formatAddressMultiline({
    address_line: r.location_address_line,
    district: r.location_district,
    state: r.location_state,
    pin_code: r.location_pin_code,
  });
  return formatted || "—";
}

export default function InventoryPage() {
  const [rows, setRows] = useState<Inv[]>([]);
  const bagTypeCache = useBagTypeCache();
  const [formLabels, setFormLabels] = useState<MasterLabels>(emptyMasterLabels);
  const [form, setForm] = useState(emptyForm);
  const [filters, setFilters] = useState({
    product_id: "",
    brand_id: "",
    location_id: "",
    bag_type_id: "",
    owner_type: "" as "" | "owned" | "job_work",
    customer_id: "",
  });
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const limit = DEFAULT_PAGE_LIMIT;
  const [addStockOpen, setAddStockOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const idemKeyRef = useRef<string | null>(null);
  const editIdemKeyRef = useRef<string | null>(null);
  const [editingRow, setEditingRow] = useState<Inv | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [editUsage, setEditUsage] = useState<InventoryUsage | null>(null);
  const [editUsageLoading, setEditUsageLoading] = useState(false);
  const [editAuthPassword, setEditAuthPassword] = useState("");
  const [editError, setEditError] = useState("");
  const [editAuthError, setEditAuthError] = useState("");
  const [locationAddressPopup, setLocationAddressPopup] = useState<{
    name: string;
    address: string;
  } | null>(null);
  const [viewMode, setViewMode] = useState<InventoryViewMode>(() => readInventoryViewMode());
  const [collapsedLocationIds, setCollapsedLocationIds] = useState<Set<number>>(() =>
    readCollapsedLocationIds()
  );
  const [expandedOwnerKeys, setExpandedOwnerKeys] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [showZeroStock, setShowZeroStock] = useState(false);
  const collapsedInitRef = useRef(false);

  const selectedBagType = useMemo(
    () => bagTypeCache.get(form.bag_type_id),
    [bagTypeCache, form.bag_type_id]
  );
  const editBagType = useMemo(
    () => bagTypeCache.get(editForm.bag_type_id),
    [bagTypeCache, editForm.bag_type_id]
  );
  const totalPreviewKg = calcPreviewTotalKg(selectedBagType, form.bag_count, form.loose_kg);
  const editPreviewKg = calcPreviewTotalKg(editBagType, editForm.bag_count, editForm.loose_kg);
  const canSubmit =
    Boolean(selectedBagType && form.product_id && form.brand_id && form.location_id) &&
    (isLooseBagType(selectedBagType)
      ? parseLooseKg(form.loose_kg) > 0
      : parseBagCount(form.bag_count) > 0);
  const canEditSubmit =
    Boolean(editingRow && editBagType) &&
    (isLooseBagType(editBagType)
      ? parseLooseKg(editForm.loose_kg) >= 0
      : parseBagCount(editForm.bag_count) >= 0) &&
    Boolean(editAuthPassword.trim());

  const hasActiveFilters = useMemo(
    () =>
      Boolean(
        filters.product_id ||
          filters.brand_id ||
          filters.location_id ||
          filters.bag_type_id ||
          filters.owner_type ||
          filters.customer_id ||
          searchQuery.trim() ||
          lowStockOnly ||
          showZeroStock
      ),
    [filters, searchQuery, lowStockOnly, showZeroStock]
  );

  const displayRows = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return rows.filter((row) => {
      if (!showZeroStock && Number(row.total_quantity_kg) <= 0) return false;
      if (lowStockOnly && !isLowStock(row)) return false;
      if (!q) return true;
      const customer = (row.customer_name ?? "").toLowerCase();
      return (
        (row.product_name ?? "").toLowerCase().includes(q) ||
        (row.brand_name ?? "").toLowerCase().includes(q) ||
        customer.includes(q)
      );
    });
  }, [rows, searchQuery, lowStockOnly, showZeroStock]);

  const sortedRows = useMemo(
    () => [...displayRows].sort(compareInventoryRows),
    [displayRows]
  );

  const pageStats = useMemo(() => {
    let ownedKg = 0;
    let jobWorkKg = 0;
    let lowStockCount = 0;
    const locationIds = new Set<number>();
    for (const row of sortedRows) {
      const kg = Number(row.total_quantity_kg);
      if (row.owner_type === "job_work") jobWorkKg += kg;
      else ownedKg += kg;
      locationIds.add(row.location_id);
      if (isLowStock(row)) lowStockCount += 1;
    }
    return { ownedKg, jobWorkKg, locationCount: locationIds.size, lowStockCount };
  }, [sortedRows]);

  const groupedInventory = useMemo(
    () => groupInventoryRows(sortedRows),
    [sortedRows]
  );

  useEffect(() => {
    if (collapsedInitRef.current || groupedInventory.length === 0) return;
    const stored = readCollapsedLocationIds();
    if (stored.size === 0 && !localStorage.getItem("v14.inventory.collapsedLocations")) {
      const all = new Set(groupedInventory.map((g) => g.locationId));
      setCollapsedLocationIds(all);
      writeCollapsedLocationIds(all);
    } else {
      setCollapsedLocationIds(stored);
    }
    collapsedInitRef.current = true;
  }, [groupedInventory]);

  const onViewModeChange = (mode: InventoryViewMode) => {
    setViewMode(mode);
    writeInventoryViewMode(mode);
  };

  const onToggleLocation = (locationId: number) => {
    setCollapsedLocationIds((prev) => {
      const next = new Set(prev);
      if (next.has(locationId)) next.delete(locationId);
      else next.add(locationId);
      writeCollapsedLocationIds(next);
      return next;
    });
  };

  const onToggleOwner = (key: string) => {
    setExpandedOwnerKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const setOwnerChip = (chip: "all" | "owned" | "job_work") => {
    if (chip === "all") {
      setFilters((f) => ({ ...f, owner_type: "", customer_id: "" }));
    } else if (chip === "owned") {
      setFilters((f) => ({ ...f, owner_type: "owned", customer_id: "" }));
    } else {
      setFilters((f) => ({ ...f, owner_type: "job_work" }));
    }
  };

  const ownerChipActive = !filters.owner_type
    ? "all"
    : filters.owner_type === "owned"
      ? "owned"
      : "job_work";

  const openLocationPopup = (row: Inv) => {
    setLocationAddressPopup({
      name: row.location_name ?? `Location #${row.location_id}`,
      address: rowLocationAddress(row),
    });
  };

  const load = useCallback(() => {
    setLoading(true);
    const q = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (filters.product_id) q.set("product_id", filters.product_id);
    if (filters.brand_id) q.set("brand_id", filters.brand_id);
    if (filters.location_id) q.set("location_id", filters.location_id);
    if (filters.bag_type_id) q.set("bag_type_id", filters.bag_type_id);
    if (filters.owner_type) q.set("owner_type", filters.owner_type);
    if (filters.customer_id) q.set("customer_id", filters.customer_id);
    const apiSearch = searchQuery.trim();
    if (apiSearch) q.set("search", apiSearch);
    api.get<PageOut<Inv>>(`/api/inventory?${q}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [filters, limit, offset, searchQuery]);

  useEffect(() => {
    setOffset(0);
  }, [filters, searchQuery, lowStockOnly, showZeroStock]);

  useEffect(() => {
    load();
  }, [load]);

  const clearFilters = () => {
    setFilters({
      product_id: "",
      brand_id: "",
      location_id: "",
      bag_type_id: "",
      owner_type: "",
      customer_id: "",
    });
    setSearchQuery("");
    setLowStockOnly(false);
    setShowZeroStock(false);
  };

  const onBagTypeChange = (bagTypeId: string, option?: MasterComboOption) => {
    if (option?.bagType) bagTypeCache.remember(option.bagType);
    setForm({
      ...form,
      bag_type_id: bagTypeId,
      ...clearQtyOnBagTypeChange(),
    });
    setFormLabels((prev) => ({ ...prev, bagType: option?.label ?? prev.bagType }));
  };

  const openAddStock = () => {
    idemKeyRef.current = null;
    setFormError("");
    setForm(emptyForm());
    setFormLabels(emptyMasterLabels());
    setAddStockOpen(true);
  };

  const closeAddStock = () => {
    setAddStockOpen(false);
    setFormError("");
    setForm(emptyForm());
    setFormLabels(emptyMasterLabels());
  };

  const openEdit = (row: Inv) => {
    editIdemKeyRef.current = null;
    setEditError("");
    setEditAuthError("");
    setEditAuthPassword("");
    setEditingRow(row);
    setEditForm({
      product_id: String(row.product_id),
      brand_id: String(row.brand_id),
      location_id: String(row.location_id),
      bag_type_id: String(row.bag_type_id),
      bag_count: String(row.bag_count),
      loose_kg: row.loose_kg,
    });
    void bagTypeCache.ensure(row.bag_type_id);
    setEditUsage(null);
    setEditUsageLoading(true);
    api.get<InventoryUsage>(`/api/inventory/${row.id}/usage`)
      .then(setEditUsage)
      .catch((e) => setEditError(e instanceof Error ? e.message : "Could not load linked activity"))
      .finally(() => setEditUsageLoading(false));
  };

  const closeEdit = () => {
    setEditingRow(null);
    setEditForm(emptyForm());
    setEditUsage(null);
    setEditAuthPassword("");
    setEditError("");
    setEditAuthError("");
    editIdemKeyRef.current = null;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError("");
    const bt = selectedBagType;
    if (!bt) {
      setFormError("Select a bag type");
      idemKeyRef.current = null;
      return;
    }
    const body = {
      product_id: Number(form.product_id),
      brand_id: Number(form.brand_id),
      location_id: Number(form.location_id),
      bag_type_id: Number(form.bag_type_id),
      bag_count: isLooseBagType(bt) ? 0 : parseBagCount(form.bag_count),
      loose_kg: isLooseBagType(bt) ? parseLooseKg(form.loose_kg) : 0,
    };
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    setSaving(true);
    try {
      await api.post("/api/inventory", body, {
        headers: idempotencyHeaders(idemKeyRef.current),
      });
      idemKeyRef.current = null;
      closeAddStock();
      load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Error");
    } finally {
      setSaving(false);
    }
  };

  const submitEdit = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingRow) return;
    setEditError("");
    setEditAuthError("");
    const bt = editBagType;
    if (!bt) {
      setEditError("Invalid bag type");
      editIdemKeyRef.current = null;
      return;
    }
    if (!editAuthPassword.trim()) {
      setEditAuthError("Authorization password is required");
      return;
    }
    const body = {
      product_id: editingRow.product_id,
      brand_id: editingRow.brand_id,
      location_id: editingRow.location_id,
      bag_type_id: editingRow.bag_type_id,
      bag_count: isLooseBagType(bt) ? 0 : parseBagCount(editForm.bag_count),
      loose_kg: isLooseBagType(bt) ? parseLooseKg(editForm.loose_kg) : 0,
    };
    if (!editIdemKeyRef.current) editIdemKeyRef.current = newIdempotencyKey();
    setSaving(true);
    try {
      await api.put<Inv>(`/api/inventory/${editingRow.id}`, body, {
        headers: idempotencyVoidAuthHeaders(editIdemKeyRef.current, editAuthPassword),
      });
      editIdemKeyRef.current = null;
      closeEdit();
      load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setEditAuthError(msg);
      } else {
        setEditError(msg);
      }
    } finally {
      setSaving(false);
    }
  };

  const activeUsageLinks = useMemo(
    () => (editUsage?.links ?? []).filter((link) => link.count > 0),
    [editUsage]
  );

  const addStockSummary = useMemo(() => {
    const parts: string[] = [];
    if (formLabels.location) parts.push(formLabels.location);
    if (formLabels.product) parts.push(formLabels.product);
    if (formLabels.brand) parts.push(formLabels.brand);
    if (formLabels.bagType) parts.push(formLabels.bagType);
    return parts.join(" · ");
  }, [formLabels]);

  const addStockForm = (
    <form id="add-stock-form" onSubmit={submit} className="space-y-6">
      {formError && <Banner tone="danger">{formError}</Banner>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-2xl border-2 border-primary-200/70 bg-primary-50/40 p-4 dark:border-primary-800/50 dark:bg-primary-950/25">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-500 text-sm font-bold text-white">
              1
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-700 dark:text-primary-300">
                Location
              </p>
              <p className="text-sm text-ink-muted">Where is this stock kept?</p>
            </div>
          </div>
          <FormField label="Godown / yard" required>
            {() => (
              <AsyncSearchCombobox
                value={form.location_id ? Number(form.location_id) : null}
                onChange={(id, opt) => {
                  setForm({ ...form, location_id: id != null ? String(id) : "" });
                  setFormLabels((prev) => ({ ...prev, location: opt?.label ?? "" }));
                }}
                searchFn={searchLocations}
                placeholder="Search location…"
                emptyText="No matching location"
              />
            )}
          </FormField>
        </div>

        <div className="rounded-2xl border-2 border-primary-200/70 bg-primary-50/40 p-4 dark:border-primary-800/50 dark:bg-primary-950/20">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-sm font-bold text-white">
              2
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-primary-700 dark:text-primary-300">
                Product
              </p>
              <p className="text-sm text-ink-muted">What commodity is this?</p>
            </div>
          </div>
          <FormField label="Product name" required>
            {() => (
              <AsyncSearchCombobox
                value={form.product_id ? Number(form.product_id) : null}
                onChange={(id, opt) => {
                  setForm({ ...form, product_id: id != null ? String(id) : "" });
                  setFormLabels((prev) => ({ ...prev, product: opt?.label ?? "" }));
                }}
                searchFn={searchProducts}
                placeholder="Search product…"
                emptyText="No matching product"
              />
            )}
          </FormField>
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-surface p-4">
        <div className="mb-4 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-muted text-xs font-bold text-ink-muted ring-1 ring-line">
            3
          </span>
          <p className="text-sm font-semibold text-ink">Brand & packaging</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField label="Brand" required>
            {() => (
              <AsyncSearchCombobox
                value={form.brand_id ? Number(form.brand_id) : null}
                onChange={(id, opt) => {
                  setForm({ ...form, brand_id: id != null ? String(id) : "" });
                  setFormLabels((prev) => ({ ...prev, brand: opt?.label ?? "" }));
                }}
                searchFn={searchBrands}
                placeholder="Search brand…"
                emptyText="No matching brand"
              />
            )}
          </FormField>
          <FormField label="Bag type" required>
            {() => (
              <AsyncSearchCombobox
                value={form.bag_type_id ? Number(form.bag_type_id) : null}
                onChange={(id, opt) =>
                  onBagTypeChange(id != null ? String(id) : "", opt as MasterComboOption | undefined)
                }
                searchFn={searchBagTypes}
                placeholder="Search bag type…"
                emptyText="No matching bag type"
              />
            )}
          </FormField>
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-surface p-4">
        <div className="mb-4 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-surface-muted text-xs font-bold text-ink-muted ring-1 ring-line">
            4
          </span>
          <p className="text-sm font-semibold text-ink">Opening quantity</p>
        </div>

        {!selectedBagType ? (
          <div className="flex items-center gap-3 rounded-xl border border-dashed border-line bg-surface-subtle/50 px-4 py-6 text-sm text-ink-muted">
            <Boxes className="h-5 w-5 shrink-0" aria-hidden="true" />
            Pick a bag type above to enter bags or kilograms
          </div>
        ) : isLooseBagType(selectedBagType) ? (
          <FormField label="Weight" required hint="Loose stock in kilograms">
            {({ id }) => (
              <NumberInput
                id={id}
                min={0.001}
                step="0.001"
                suffix="kg"
                value={form.loose_kg}
                placeholder={PH_LOOSE_KG}
                onChange={(e) => setForm({ ...form, loose_kg: e.target.value, bag_count: "" })}
                required
              />
            )}
          </FormField>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <FormField
              label="Number of bags"
              required
              hint={`${selectedBagType.weight_per_bag_kg} kg each`}
            >
              {({ id }) => (
                <NumberInput
                  id={id}
                  min={0}
                  step={1}
                  value={form.bag_count}
                  placeholder={PH_BAGS}
                  onChange={(e) => setForm({ ...form, bag_count: e.target.value, loose_kg: "" })}
                  required
                />
              )}
            </FormField>
            <div className="rounded-xl bg-surface-subtle px-4 py-3 text-center sm:min-w-[7rem]">
              <p className="text-xs text-ink-subtle">Per bag</p>
              <p className="v2-mono text-lg font-semibold text-ink">{selectedBagType.weight_per_bag_kg} kg</p>
            </div>
          </div>
        )}
      </div>
    </form>
  );

  const inventoryStockList =
    viewMode === "summary" ? (
      <InventorySummaryView
        groups={groupedInventory}
        loading={loading}
        collapsedLocationIds={collapsedLocationIds}
        expandedOwnerKeys={expandedOwnerKeys}
        onToggleLocation={onToggleLocation}
        onToggleOwner={onToggleOwner}
        onEdit={openEdit}
        onAddStock={openAddStock}
      />
    ) : (
      <InventoryDetailView
        groups={groupedInventory}
        loading={loading}
        onEdit={openEdit}
        onAddStock={openAddStock}
        onLocationClick={openLocationPopup}
      />
    );

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        title="Inventory"
        subtitle="Stock by location, product, brand, and bag type. Quantities change only via fulfillment, operations, or processing."
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openAddStock} className="hidden sm:inline-flex">
            Add stock
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {!loading && sortedRows.length > 0 && (
        <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <button type="button" className="text-left" onClick={() => setOwnerChip("owned")}>
            <Stat label="Owned stock (page)" value={formatQtyKg(pageStats.ownedKg)} tone="primary" />
          </button>
          <button type="button" className="text-left" onClick={() => setOwnerChip("job_work")}>
            <Stat label="Job work custody (page)" value={formatQtyKg(pageStats.jobWorkKg)} tone="info" />
          </button>
          <button
            type="button"
            className="text-left"
            onClick={() => setFilters((f) => ({ ...f, location_id: "" }))}
          >
            <Stat label="Locations (page)" value={String(pageStats.locationCount)} tone="neutral" />
          </button>
          <button type="button" className="text-left" onClick={() => setLowStockOnly(true)}>
            <Stat label="Low-stock lines (page)" value={String(pageStats.lowStockCount)} tone="warning" />
          </button>
        </div>
      )}

      <Modal
        open={addStockOpen}
        onClose={closeAddStock}
        size="lg"
        title="Add opening stock"
        description="One-time stock entry. Later changes go through bills, fulfillment, or operations."
        footer={
          <div className="flex w-full min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              {addStockSummary ? (
                <p className="break-words text-sm text-ink-muted">{addStockSummary}</p>
              ) : (
                <p className="text-sm text-ink-subtle">Start with location and product</p>
              )}
              <div className="mt-0.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <p className="v2-mono text-xl font-bold tabular-nums text-ink sm:text-2xl">
                  {formatQtyKg(totalPreviewKg)}
                </p>
                {selectedBagType &&
                  !isLooseBagType(selectedBagType) &&
                  parseBagCount(form.bag_count) > 0 && (
                    <span className="text-sm text-ink-subtle">
                      {parseBagCount(form.bag_count)} bag{parseBagCount(form.bag_count) === 1 ? "" : "s"} ×{" "}
                      {selectedBagType.weight_per_bag_kg} kg
                    </span>
                  )}
              </div>
            </div>
            <div className="flex w-full shrink-0 flex-col-reverse gap-2 sm:w-auto sm:flex-row">
              <Button variant="ghost" onClick={closeAddStock} disabled={saving} className="w-full sm:w-auto">
                Cancel
              </Button>
              <Button
                type="submit"
                form="add-stock-form"
                loading={saving}
                disabled={!canSubmit}
                className="w-full sm:w-auto"
                leftIcon={<PackagePlus className="h-4 w-4" />}
              >
                Add stock
              </Button>
            </div>
          </div>
        }
      >
        {addStockForm}
      </Modal>

      <Modal
        open={!!editingRow}
        onClose={closeEdit}
        size="lg"
        title="Edit stock quantity"
        description="Manual correction only. Normal stock movement goes through bills, fulfillment, or operations."
        footer={
          <div className="flex w-full min-w-0 flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="ghost" onClick={closeEdit} disabled={saving} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button
              type="submit"
              form="edit-stock-form"
              loading={saving}
              disabled={!canEditSubmit}
              className="w-full sm:w-auto"
            >
              Save changes
            </Button>
          </div>
        }
      >
        <form id="edit-stock-form" onSubmit={submitEdit} className="space-y-5">
          {editError && <Banner tone="danger">{editError}</Banner>}

          <div className="rounded-2xl border border-line bg-surface-subtle p-4">
            <p className="break-words text-sm font-semibold text-ink">
              {editingRow?.product_name ?? "Product"}
            </p>
            <p className="mt-1 break-words text-sm text-ink-muted">
              {[editingRow?.location_name, editingRow?.brand_name, editingRow?.bag_type_name]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <p className="mt-2 v2-mono text-xl font-bold tabular-nums text-ink">
              {formatQtyKg(editPreviewKg)}
            </p>
          </div>

          <Banner tone="warning">
            <div className="space-y-2 break-words">
              <p className="font-semibold text-ink">
                This stock row is linked across the app. Changing quantity here does not update those records.
              </p>
              <p className="text-sm text-ink-muted">
                Linked areas include sales bills, fulfillment, bag changes, transfers, disposals, and processing.
              </p>
              {editUsageLoading ? (
                <p className="text-sm text-ink-subtle">Checking linked activity…</p>
              ) : activeUsageLinks.length > 0 ? (
                <ul className="space-y-1.5 text-sm">
                  {activeUsageLinks.map((link) => (
                    <li key={link.key} className="flex items-start gap-2">
                      <Link2 className="mt-0.5 h-4 w-4 shrink-0 text-warning-700 dark:text-warning-300" aria-hidden="true" />
                      <span>
                        <span className="font-medium text-ink">{link.label}</span>
                        <span className="text-ink-muted"> — {link.count} record{link.count === 1 ? "" : "s"}</span>
                        {link.hint ? <span className="block text-xs text-ink-subtle">{link.hint}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-subtle">No linked activity found yet for this row.</p>
              )}
            </div>
          </Banner>

          <div className="rounded-2xl border border-line bg-surface p-4">
            <p className="mb-3 text-sm font-semibold text-ink">Quantity</p>
            {!editBagType ? (
              <p className="text-sm text-ink-muted">Bag type not found.</p>
            ) : isLooseBagType(editBagType) ? (
              <FormField label="Weight" required hint="Loose stock in kilograms">
                {({ id }) => (
                  <NumberInput
                    id={id}
                    min={0}
                    step="0.001"
                    suffix="kg"
                    value={editForm.loose_kg}
                    placeholder={PH_LOOSE_KG}
                    onChange={(e) => setEditForm({ ...editForm, loose_kg: e.target.value, bag_count: "" })}
                    required
                  />
                )}
              </FormField>
            ) : (
              <FormField
                label="Number of bags"
                required
                hint={`${editBagType.weight_per_bag_kg} kg each`}
              >
                {({ id }) => (
                  <NumberInput
                    id={id}
                    min={0}
                    step={1}
                    value={editForm.bag_count}
                    placeholder={PH_BAGS}
                    onChange={(e) => setEditForm({ ...editForm, bag_count: e.target.value, loose_kg: "" })}
                    required
                  />
                )}
              </FormField>
            )}
          </div>

          <FormField
            label="Authorization password"
            hint="Admin void password or your login password."
            error={editAuthError}
            required
          >
            {({ id, "aria-describedby": describedBy, "aria-invalid": invalid }) => (
              <Input
                id={id}
                type="password"
                autoComplete="current-password"
                placeholder="Required to save"
                value={editAuthPassword}
                onChange={(e) => setEditAuthPassword(e.target.value)}
                leftIcon={<Lock className="h-4 w-4" />}
                invalid={invalid || Boolean(editAuthError)}
                aria-describedby={describedBy}
                disabled={saving}
              />
            )}
          </FormField>
        </form>
      </Modal>

      <Card>
        <CardHeader
          title="Stock on hand"
          subtitle="Summary or detail view by location and owner. Click stat tiles or chips to filter."
          actions={
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
              <SegmentedControl
                ariaLabel="Inventory view"
                value={viewMode}
                onChange={(v) => onViewModeChange(v)}
                size="sm"
                className="flex w-full flex-wrap sm:w-auto sm:flex-nowrap [&>button]:min-w-0 [&>button]:flex-1 sm:[&>button]:flex-none"
                options={[
                  { value: "summary", label: "Summary" },
                  { value: "detail", label: "Detail" },
                ]}
              />
              {hasActiveFilters ? (
                <Button variant="secondary" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
            </div>
          }
        />
        <CardBody className="space-y-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant={ownerChipActive === "all" ? "secondary" : "outline"}
                onClick={() => setOwnerChip("all")}
              >
                All
              </Button>
              <Button
                type="button"
                size="sm"
                variant={ownerChipActive === "owned" ? "secondary" : "outline"}
                onClick={() => setOwnerChip("owned")}
              >
                My stock
              </Button>
              <Button
                type="button"
                size="sm"
                variant={ownerChipActive === "job_work" ? "secondary" : "outline"}
                onClick={() => setOwnerChip("job_work")}
              >
                Job work
              </Button>
              <Button
                type="button"
                size="sm"
                variant={showZeroStock ? "secondary" : "outline"}
                onClick={() => setShowZeroStock((v) => !v)}
                title="Include inventory rows with 0 kg on hand"
              >
                Zero kg rows
              </Button>
            </div>
            <FormField label="Search" className="min-w-0 w-full flex-1 lg:max-w-xs">
              {({ id }) => (
                <Input
                  id={id}
                  value={searchQuery}
                  placeholder="Product, brand, or customer…"
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              )}
            </FormField>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <FormField label="Location">
              {() => (
                <AsyncSearchCombobox
                  value={filters.location_id ? Number(filters.location_id) : null}
                  onChange={(id) => setFilters({ ...filters, location_id: id != null ? String(id) : "" })}
                  searchFn={searchLocations}
                  placeholder="All locations"
                  emptyText="No matching location"
                />
              )}
            </FormField>
            <FormField label="Product">
              {() => (
                <AsyncSearchCombobox
                  value={filters.product_id ? Number(filters.product_id) : null}
                  onChange={(id) => setFilters({ ...filters, product_id: id != null ? String(id) : "" })}
                  searchFn={searchProducts}
                  placeholder="All products"
                  emptyText="No matching product"
                />
              )}
            </FormField>
            <FormField label="Brand">
              {() => (
                <AsyncSearchCombobox
                  value={filters.brand_id ? Number(filters.brand_id) : null}
                  onChange={(id) => setFilters({ ...filters, brand_id: id != null ? String(id) : "" })}
                  searchFn={searchBrands}
                  placeholder="All brands"
                  emptyText="No matching brand"
                />
              )}
            </FormField>
            <FormField label="Bag type">
              {() => (
                <AsyncSearchCombobox
                  value={filters.bag_type_id ? Number(filters.bag_type_id) : null}
                  onChange={(id, opt) => {
                    const bagOpt = opt as MasterComboOption | undefined;
                    if (bagOpt?.bagType) bagTypeCache.remember(bagOpt.bagType);
                    setFilters({ ...filters, bag_type_id: id != null ? String(id) : "" });
                  }}
                  searchFn={searchBagTypes}
                  placeholder="All bag types"
                  emptyText="No matching bag type"
                />
              )}
            </FormField>
            <FormField label="Owner">
              {({ id }) => (
                <Select
                  id={id}
                  value={filters.owner_type}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      owner_type: e.target.value as "" | "owned" | "job_work",
                      customer_id: e.target.value === "job_work" ? filters.customer_id : "",
                    })
                  }
                >
                  <option value="">All owners</option>
                  <option value="owned">Owned</option>
                  <option value="job_work">Job work</option>
                </Select>
              )}
            </FormField>
            <FormField label="Customer (job work)">
              {() => (
                <AsyncSearchCombobox
                  value={filters.customer_id ? Number(filters.customer_id) : null}
                  onChange={(id) => setFilters({ ...filters, customer_id: id != null ? String(id) : "" })}
                  searchFn={searchCustomers}
                  placeholder="All customers"
                  emptyText="No matching customer"
                  disabled={filters.owner_type !== "job_work"}
                />
              )}
            </FormField>
          </div>

          {inventoryStockList}

          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />

          {!loading && sortedRows.length > 0 && (
            <p className="text-sm text-ink-subtle">
              {sortedRows.length} stock row{sortedRows.length === 1 ? "" : "s"} — quantities change via
              bills, operations, or processing only
            </p>
          )}
        </CardBody>
      </Card>

      <Modal
        open={!!locationAddressPopup}
        onClose={() => setLocationAddressPopup(null)}
        title={locationAddressPopup?.name ?? "Location"}
        footer={
          <Button variant="secondary" onClick={() => setLocationAddressPopup(null)}>
            Close
          </Button>
        }
      >
        <p className="whitespace-pre-line text-base text-ink-muted">{locationAddressPopup?.address}</p>
      </Modal>
      <button
        type="button"
        onClick={openAddStock}
        className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
        aria-label="Add stock"
      >
        <Plus className="h-6 w-6" />
      </button>
    </div>
  );
}
