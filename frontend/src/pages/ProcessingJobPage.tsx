import { FormEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowUpFromLine,
  CheckCircle2,
  Layers,
  Plus,
  Scale,
  Trash2,
  Ban,
  Eye,
} from "lucide-react";
import {
  api,
  bookSettingsApi,
  idempotencyHeaders,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type BagType,
  type BookSettings,
  type ProcessingBatch,
  type ProcessingInputSource,
  type ProcessingJob,
  type ProcessingJobSummary,
  type ProcessingOwnerAllocationWeight,
  type ProcessingWasteAllocation,
} from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Banner from "../components/ui/Banner";
import Badge from "../components/ui/Badge";
import FormField from "../components/ui/FormField";
import Select from "../components/ui/Select";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import Input from "../components/ui/Input";
import NumberInput from "../components/ui/NumberInput";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import Tabs, { Tab } from "../components/ui/Tabs";
import Table, { type Column } from "../components/ui/Table";
import Skeleton from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import VoidConfirmDialog from "../components/ui/VoidConfirmDialog";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import Modal from "../components/ui/Modal";
import { VoidPill } from "../components/ui/StatusPill";
import SegmentedControl from "../components/ui/SegmentedControl";
import { cn } from "../lib/cn";
import { calcPreviewTotalKg, isLooseBagType } from "../lib/bagType";
import { formatDate, formatDateTime, formatQtyKg } from "../lib/format";
import {
  computeMassBalance,
  computeOutputLineCountsByBrand,
  computeProcessingEntryCounts,
  jobAvailableReprocessKg,
  jobSummary,
  lastBalanceReturnEntries,
  lastBrandOutputEntries,
  lastMiscEntries,
  lastPowderEntries,
  lastWasteEntries,
  totalOutputKg,
  totalPowderKgFromBatches,
  activeProcessingBatches,
  type RecentBalanceReturnEntry,
  type RecentBrandOutputEntry,
  type RecentMiscEntry,
  type RecentWasteEntry,
} from "../lib/processingSummary";
import { usePermissions } from "../lib/permissions";
import { useSidebarCollapsed } from "../components/Sidebar";
import {
  formatRemainingStockAfterReserved,
  reservedStockFromEarlierLines,
  reservedStockFromSiblingLines,
  stockExceedsMessageWithReserved,
} from "../lib/stockWarning";
import {
  emptyQtyFields,
  outputLineStarted,
  parseBagCount,
  parseLooseKg,
  parseOptionalNumber,
  PH_BAGS,
  PH_LOOSE_KG,
  stockLineStarted,
  validateStockLineQty,
} from "../lib/qtyInput";
import {
  bagTypesFromStock,
  stockRow,
  type StockAtLocation,
  type StockOwnerFilter,
} from "../lib/stockAtLocation";
import {
  fetchCustomerById,
  searchBagTypes,
  searchBrands,
  searchCustomers,
  searchLocations,
  type MasterComboOption,
} from "../lib/masterSearch";

type TabId = "input" | "output" | "waste" | "summary" | "batches";

const PROCESSING_LAYOUT_GUTTER_FR = 3;
const PROCESSING_LAYOUT_CONTENT_FR = 71;
const PROCESSING_LAYOUT_SNAPSHOT_FR = 25;
const PROCESSING_LAYOUT_TOTAL_FR =
  PROCESSING_LAYOUT_GUTTER_FR * 2 + PROCESSING_LAYOUT_CONTENT_FR + PROCESSING_LAYOUT_SNAPSHOT_FR;

type InputLineForm = {
  key: string;
  input_source: ProcessingInputSource;
  owner_type: "owned" | "job_work";
  customer_id: string;
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
};

type BalanceReturnLineForm = {
  key: string;
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
};

type OutputLineForm = {
  key: string;
  brand_id: string;
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
  brand_label?: string;
  location_label?: string;
  bag_type_label?: string;
};

const emptyInputLine = (): InputLineForm => ({
  key: crypto.randomUUID(),
  input_source: "fresh",
  owner_type: "owned",
  customer_id: "",
  location_id: "",
  bag_type_id: "",
  ...emptyQtyFields(),
});

const emptyBalanceReturnLine = (): BalanceReturnLineForm => ({
  key: crypto.randomUUID(),
  location_id: "",
  bag_type_id: "",
  ...emptyQtyFields(),
});

const emptyOutputLine = (): OutputLineForm => ({
  key: crypto.randomUUID(),
  brand_id: "",
  location_id: "",
  bag_type_id: "",
  ...emptyQtyFields(),
});

const emptyInputForm = () => ({
  input_lines: [emptyInputLine()],
});

type PowderLineForm = {
  brand_id: string;
  location_id: string;
  bag_type_id: string;
  bag_count: string;
  loose_kg: string;
};

const emptyPowderLine = (): PowderLineForm => ({
  brand_id: "",
  location_id: "",
  bag_type_id: "",
  ...emptyQtyFields(),
});

const emptyOutputForm = () => ({
  output_lines: [emptyOutputLine()],
  balance_return_lines: [emptyBalanceReturnLine()],
  dust_kg: "",
  stone_kg: "",
  sack_weight_waste_kg: "",
  powder_line: emptyPowderLine(),
  miscellaneous_waste_kg: "",
});

const ZERO_BATCH = {
  dust_kg: 0,
  stone_kg: 0,
  sack_weight_waste_kg: 0,
  powder_kg: 0,
  miscellaneous_waste_kg: 0,
};

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Error";
}

function ProcessingSection({
  title,
  subtitle,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-4 rounded-2xl border border-line/80 bg-surface-subtle/25 p-5", className)}>
      <div>
        <h4 className="text-lg font-semibold text-ink">{title}</h4>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function ProcessingLineCard({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line/70 bg-surface p-4 shadow-sm">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{children}</div>
      {footer}
    </div>
  );
}

function jobStatusTone(status: string): "primary" | "success" | "muted" {
  if (status === "open") return "primary";
  if (status === "completed") return "success";
  return "muted";
}

function powderLineStarted(line: PowderLineForm) {
  return Boolean(
    line.brand_id || line.location_id || line.bag_type_id || line.bag_count.trim() || line.loose_kg.trim()
  );
}

function isPowderBrandOption(
  brandId: number,
  brandName: string,
  bookSettings: BookSettings | null | undefined
) {
  if (brandName.trim().toLowerCase() === "powder") return true;
  return bookSettings?.powder_brand_id != null && brandId === bookSettings.powder_brand_id;
}

function powderKgFromLine(
  line: PowderLineForm,
  getBagType: (id: string) => BagType | undefined
): number {
  if (!powderLineStarted(line)) return 0;
  const bt = getBagType(line.bag_type_id);
  return calcPreviewTotalKg(bt, parseBagCount(line.bag_count), parseLooseKg(line.loose_kg));
}

function wasteHasContent(form: ReturnType<typeof emptyOutputForm>) {
  return (
    parseOptionalNumber(form.dust_kg) > 0 ||
    parseOptionalNumber(form.stone_kg) > 0 ||
    parseOptionalNumber(form.sack_weight_waste_kg) > 0 ||
    powderLineStarted(form.powder_line)
  );
}

function inputFormHasContent(inputForm: ReturnType<typeof emptyInputForm>) {
  return inputForm.input_lines.some((ln) => stockLineStarted(ln));
}

function balanceReturnLineStarted(line: BalanceReturnLineForm) {
  return stockLineStarted(line);
}

function outputBalanceHasContent(outputForm: ReturnType<typeof emptyOutputForm>) {
  return (
    outputForm.output_lines.some((ln) => outputLineStarted(ln)) ||
    outputForm.balance_return_lines.some((ln) => balanceReturnLineStarted(ln))
  );
}

function outputFormHasContent(outputForm: ReturnType<typeof emptyOutputForm>) {
  return outputBalanceHasContent(outputForm) || wasteHasContent(outputForm);
}

type CustomerLabelLookup = Record<number, string>;

function resolveCustomerName(id: number | null | undefined, lookup: CustomerLabelLookup): string | undefined {
  if (id == null) return undefined;
  return lookup[id];
}

function buildInputOwnerMixMessage(
  job: ProcessingJob,
  customerLabels: CustomerLabelLookup
): string | null {
  if (job.output_allocation_hint) return job.output_allocation_hint;
  if (job.output_allocation_locked && job.output_allocation_mode === "single_owner") {
    const name =
      job.single_allocation_customer_name ??
      resolveCustomerName(job.single_allocation_customer_id, customerLabels);
    if (job.single_allocation_owner_type === "owned") {
      return "Output allocation: 100% Owned";
    }
    return `Output allocation: 100% Job work · ${name ?? "customer"}`;
  }
  const apiWeights = job.owner_allocation_weights ?? [];
  if (apiWeights.length > 0) {
    if (apiWeights.length === 1) {
      const w = apiWeights[0];
      if (w.owner_type === "owned") return "Output will post to Owned only.";
      const name =
        w.customer_name ?? resolveCustomerName(w.customer_id, customerLabels) ?? "Job work";
      return `Output will post to Job work only · ${name}.`;
    }
    const parts = apiWeights.map((w) => {
      const pct = Number(w.share_pct).toFixed(2);
      if (w.owner_type === "owned") return `${pct}% Owned`;
      const name =
        w.customer_name ?? resolveCustomerName(w.customer_id, customerLabels) ?? "Job work";
      return `${pct}% Job work · ${name}`;
    });
    return `Input mix: ${parts.join(", ")}`;
  }

  const lines = (job.batches ?? []).flatMap((b) => b.input_lines);
  if (!lines.length) return null;
  const byKey = new Map<string, { kg: number; owner_type: string; customer_id?: number | null }>();
  for (const ln of lines) {
    const kg = Number(ln.quantity_kg);
    if (kg <= 0) continue;
    const key = ln.owner_type === "job_work" ? `jw:${ln.customer_id ?? ""}` : "owned";
    const prev = byKey.get(key) ?? {
      kg: 0,
      owner_type: ln.owner_type ?? "owned",
      customer_id: ln.customer_id,
    };
    byKey.set(key, { ...prev, kg: prev.kg + kg });
  }
  const entries = [...byKey.values()];
  const total = entries.reduce((sum, v) => sum + v.kg, 0);
  if (total <= 0) return null;
  if (entries.length === 1) {
    const only = entries[0];
    if (only.owner_type === "owned") return "Output will post to Owned only.";
    const name = resolveCustomerName(only.customer_id, customerLabels) ?? "Job work";
    return `Output will post to Job work only · ${name}.`;
  }
  const parts = entries.map((v) => {
    const pct = ((v.kg / total) * 100).toFixed(2);
    if (v.owner_type === "owned") return `${pct}% Owned`;
    const name = resolveCustomerName(v.customer_id, customerLabels) ?? "Job work";
    return `${pct}% Job work · ${name}`;
  });
  return `Input mix: ${parts.join(", ")}`;
}

function willCreateMix(
  job: ProcessingJob,
  pendingLines: { owner_type: string; customer_id: number | null }[]
): boolean {
  if (job.output_allocation_locked) return false;
  const keys = new Set<string>();
  for (const batch of job.batches ?? []) {
    for (const ln of batch.input_lines) {
      if (Number(ln.quantity_kg) <= 0) continue;
      keys.add(ln.owner_type === "job_work" ? `jw:${ln.customer_id ?? ""}` : "owned");
    }
  }
  for (const ln of pendingLines) {
    keys.add(ln.owner_type === "job_work" ? `jw:${ln.customer_id ?? ""}` : "owned");
  }
  return keys.size >= 2;
}

type OutputAllocationMode = "proportional" | "single_owner";

function defaultSingleOwnerKey(weights: ProcessingOwnerAllocationWeight[]): string {
  if (!weights.length) return "owned";
  const sorted = [...weights].sort((a, b) => {
    const kgDiff = Number(b.input_kg) - Number(a.input_kg);
    if (kgDiff !== 0) return kgDiff;
    if (a.owner_type === "owned" && b.owner_type !== "owned") return -1;
    if (b.owner_type === "owned" && a.owner_type !== "owned") return 1;
    return (b.customer_id ?? 0) - (a.customer_id ?? 0);
  });
  const w = sorted[0];
  return w.owner_type === "job_work" ? `jw:${w.customer_id}` : "owned";
}

function ownerKeyLabel(key: string, customerLabels: CustomerLabelLookup): string {
  if (key === "owned") return "Owned";
  const id = Number(key.replace("jw:", ""));
  const name = resolveCustomerName(id, customerLabels) ?? "Job work";
  return `Job work · ${name}`;
}

function parseOwnerKey(key: string): ["owned" | "job_work", number | undefined] {
  if (key === "owned") return ["owned", undefined];
  return ["job_work", Number(key.replace("jw:", ""))];
}

function lockedInputOwnerFromJob(job: ProcessingJob): Pick<InputLineForm, "owner_type" | "customer_id"> | null {
  if (job.input_allowed_owner) {
    return {
      owner_type: job.input_allowed_owner.owner_type,
      customer_id:
        job.input_allowed_owner.customer_id != null
          ? String(job.input_allowed_owner.customer_id)
          : "",
    };
  }
  if (job.owner_mode !== "single_owner" || !job.has_output) return null;
  const w = job.owner_allocation_weights?.[0];
  if (w) {
    return {
      owner_type: w.owner_type,
      customer_id: w.customer_id != null ? String(w.customer_id) : "",
    };
  }
  const lines = (job.batches ?? []).flatMap((b) => b.input_lines);
  const first = lines.find((ln) => Number(ln.quantity_kg) > 0);
  if (!first) return null;
  return {
    owner_type: first.owner_type === "job_work" ? "job_work" : "owned",
    customer_id: first.customer_id != null ? String(first.customer_id) : "",
  };
}

function ownerRulesBannerMessage(job: ProcessingJob, customerLabels: CustomerLabelLookup): string | null {
  if (job.input_rules_hint) return job.input_rules_hint;
  return buildInputOwnerMixMessage(job, customerLabels);
}

export default function ProcessingJobPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const bagTypeCache = useBagTypeCache();
  const getBagType = bagTypeCache.get;
  const [customerLabels, setCustomerLabels] = useState<CustomerLabelLookup>({});
  const [stockByLocation, setStockByLocation] = useState<Record<string, StockAtLocation[]>>({});
  const [bookSettings, setBookSettings] = useState<BookSettings | null>(null);
  const [inputForm, setInputForm] = useState(emptyInputForm);
  const [outputForm, setOutputForm] = useState(emptyOutputForm);
  const [activeTab, setActiveTab] = useState<TabId>("input");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const { submitting: saving, guardedSubmit, submitDisabled } = useSubmitGuard();
  const [completeAuthOpen, setCompleteAuthOpen] = useState(false);
  const [completeAuthError, setCompleteAuthError] = useState("");
  const [voidBatchTarget, setVoidBatchTarget] = useState<ProcessingBatch | null>(null);
  const [voidBatchAuthError, setVoidBatchAuthError] = useState("");
  const [inputMixConfirmOpen, setInputMixConfirmOpen] = useState(false);
  const [completeFlowConfirmOpen, setCompleteFlowConfirmOpen] = useState(false);
  const [completeBalanceConfirmOpen, setCompleteBalanceConfirmOpen] = useState(false);
  const [jobLoadDone, setJobLoadDone] = useState(false);
  const [outputAllocationMode, setOutputAllocationMode] = useState<OutputAllocationMode>("proportional");
  const [singleAllocationOwnerKey, setSingleAllocationOwnerKey] = useState("owned");
  const inputBatchIdemRef = useRef<string | null>(null);
  const outputBatchIdemRef = useRef<string | null>(null);
  const wasteBatchIdemRef = useRef<string | null>(null);
  const completeIdemRef = useRef<string | null>(null);

  const { canVoid } = usePermissions();
  const summary = useMemo(() => (job ? jobSummary(job) : null), [job]);
  const [sidebarCollapsed] = useSidebarCollapsed();
  const layoutGridRef = useRef<HTMLDivElement>(null);
  const [fixedSnapshotBox, setFixedSnapshotBox] = useState<{ left: number; width: number } | null>(null);

  const updateFixedSnapshotBox = useCallback(() => {
    const grid = layoutGridRef.current;
    if (!grid || window.innerWidth < 1024) {
      setFixedSnapshotBox(null);
      return;
    }
    const rect = grid.getBoundingClientRect();
    const width = (rect.width * PROCESSING_LAYOUT_SNAPSHOT_FR) / PROCESSING_LAYOUT_TOTAL_FR;
    const left =
      rect.left +
      (rect.width *
        (PROCESSING_LAYOUT_GUTTER_FR + PROCESSING_LAYOUT_CONTENT_FR + PROCESSING_LAYOUT_GUTTER_FR)) /
        PROCESSING_LAYOUT_TOTAL_FR;
    setFixedSnapshotBox({ left, width });
  }, []);

  useLayoutEffect(() => {
    updateFixedSnapshotBox();
    window.addEventListener("resize", updateFixedSnapshotBox);
    const observer = new ResizeObserver(updateFixedSnapshotBox);
    if (layoutGridRef.current) observer.observe(layoutGridRef.current);
    const afterSidebarTransition = window.setTimeout(updateFixedSnapshotBox, 220);
    return () => {
      window.removeEventListener("resize", updateFixedSnapshotBox);
      observer.disconnect();
      window.clearTimeout(afterSidebarTransition);
    };
  }, [updateFixedSnapshotBox, sidebarCollapsed, summary, jobLoadDone]);
  const availableReprocessKg = useMemo(
    () => (summary ? jobAvailableReprocessKg(summary) : 0),
    [summary]
  );
  const inputOwnerMixMessage = useMemo(
    () => (job ? buildInputOwnerMixMessage(job, customerLabels) : null),
    [job, customerLabels]
  );
  const ownerRulesMessage = useMemo(
    () => (job ? ownerRulesBannerMessage(job, customerLabels) : null),
    [job, customerLabels]
  );
  const customerNameMap = useMemo(
    () => new Map(Object.entries(customerLabels).map(([id, name]) => [Number(id), name] as const)),
    [customerLabels]
  );
  const searchPowderBrands = useCallback(
    async (query: string): Promise<MasterComboOption[]> => {
      const rows = await searchBrands(query);
      return rows.filter((row) => isPowderBrandOption(row.value, row.label, bookSettings));
    },
    [bookSettings]
  );
  const lockedInputOwner = useMemo(() => (job ? lockedInputOwnerFromJob(job) : null), [job]);
  const inputLocked = Boolean(job?.input_locked);
  const completed = job?.status === "completed";

  useEffect(() => {
    if (!lockedInputOwner) return;
    setInputForm((f) => ({
      ...f,
      input_lines: f.input_lines.map((ln) => ({
        ...ln,
        owner_type: lockedInputOwner.owner_type,
        customer_id: lockedInputOwner.customer_id,
        bag_type_id: "",
        ...emptyQtyFields(),
      })),
    }));
  }, [lockedInputOwner]);

  useEffect(() => {
    if (availableReprocessKg > 0) return;
    setInputForm((f) => {
      const needsFresh = f.input_lines.some((ln) => ln.input_source === "balance_reprocess");
      if (!needsFresh) return f;
      return {
        ...f,
        input_lines: f.input_lines.map((ln) =>
          ln.input_source === "balance_reprocess" ? { ...ln, input_source: "fresh" } : ln
        ),
      };
    });
  }, [availableReprocessKg]);

  const loadJob = useCallback(() => {
    if (!id) return;
    setJobLoadDone(false);
    api
      .get<ProcessingJob>(`/api/operations/processing/${id}`)
      .then(setJob)
      .catch((e) => setError(errMsg(e)))
      .finally(() => setJobLoadDone(true));
  }, [id]);

  const loadStock = useCallback((locationId: string) => {
    if (!locationId) return;
    api
      .get<StockAtLocation[]>(`/api/inventory/stock-at-location?location_id=${locationId}`)
      .then((rows) => setStockByLocation((prev) => ({ ...prev, [locationId]: rows })))
      .catch(() => setStockByLocation((prev) => ({ ...prev, [locationId]: [] })));
  }, []);

  const reloadInputLocationsStock = useCallback(
    (lines: InputLineForm[]) => {
      const ids = [...new Set(lines.map((ln) => ln.location_id).filter(Boolean))];
      ids.forEach((locId) => loadStock(locId));
    },
    [loadStock]
  );

  useEffect(() => {
    bookSettingsApi.get().then(setBookSettings).catch(() => setBookSettings(null));
    loadJob();
  }, [loadJob]);

  useEffect(() => {
    if (!job?.batches?.length) return;
    const ids = job.batches.flatMap((batch) => [
      ...batch.input_lines.map((ln) => ln.bag_type_id),
      ...batch.output_lines.map((ln) => ln.bag_type_id),
      ...(batch.balance_return_lines ?? []).map((ln) => ln.bag_type_id),
      batch.powder_bag_type_id,
    ]);
    void bagTypeCache.ensureMany(ids);
  }, [job, bagTypeCache.ensureMany]);

  useEffect(() => {
    if (!job) return;
    const fromJob: CustomerLabelLookup = {};
    if (job.single_allocation_customer_id != null && job.single_allocation_customer_name) {
      fromJob[job.single_allocation_customer_id] = job.single_allocation_customer_name;
    }
    if (job.input_allowed_owner?.customer_id != null && job.input_allowed_owner.customer_name) {
      fromJob[job.input_allowed_owner.customer_id] = job.input_allowed_owner.customer_name;
    }
    for (const w of job.owner_allocation_weights ?? []) {
      if (w.customer_id != null && w.customer_name) fromJob[w.customer_id] = w.customer_name;
    }
    setCustomerLabels((prev) => ({ ...fromJob, ...prev }));

    const missingIds = new Set<number>();
    for (const batch of job.batches ?? []) {
      for (const ln of batch.input_lines) {
        if (ln.owner_type === "job_work" && ln.customer_id != null && !fromJob[ln.customer_id]) {
          missingIds.add(ln.customer_id);
        }
      }
      for (const ln of batch.output_lines) {
        if (ln.owner_type === "job_work" && ln.customer_id != null && !fromJob[ln.customer_id]) {
          missingIds.add(ln.customer_id);
        }
      }
      for (const ln of batch.balance_return_lines ?? []) {
        if (ln.owner_type === "job_work" && ln.customer_id != null && !fromJob[ln.customer_id]) {
          missingIds.add(ln.customer_id);
        }
      }
    }
    if (!missingIds.size) return;
    let cancelled = false;
    Promise.all([...missingIds].map((customerId) => fetchCustomerById(customerId))).then((rows) => {
      if (cancelled) return;
      setCustomerLabels((prev) => {
        const next = { ...prev };
        for (const customer of rows) {
          if (customer) next[customer.id] = customer.name;
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [job]);

  useEffect(() => {
    reloadInputLocationsStock(inputForm.input_lines);
  }, [inputForm.input_lines, reloadInputLocationsStock]);

  const inputLinesForApi = useMemo(
    () =>
      inputForm.input_lines
        .filter((ln) => stockLineStarted(ln))
        .map((ln) => ({
          location_id: Number(ln.location_id),
          bag_type_id: Number(ln.bag_type_id),
          bag_count: parseBagCount(ln.bag_count),
          loose_kg: parseLooseKg(ln.loose_kg),
          input_source: ln.input_source,
          owner_type: ln.owner_type,
          customer_id: ln.owner_type === "job_work" && ln.customer_id ? Number(ln.customer_id) : null,
        })),
    [inputForm.input_lines]
  );

  const allocationOwnerOptions = useMemo(() => {
    const byKey = new Map<
      string,
      { key: string; label: string; kg: number; owner_type: string; customer_id?: number | null }
    >();
    for (const w of job?.owner_allocation_weights ?? []) {
      const key = w.owner_type === "job_work" ? `jw:${w.customer_id}` : "owned";
      byKey.set(key, {
        key,
        kg: Number(w.input_kg),
        owner_type: w.owner_type,
        customer_id: w.customer_id,
        label:
          w.owner_type === "owned"
            ? `Owned (${formatQtyKg(w.input_kg)} input)`
            : `Job work · ${w.customer_name ?? "customer"} (${formatQtyKg(w.input_kg)} input)`,
      });
    }
    for (const ln of inputLinesForApi) {
      const bt = getBagType(ln.bag_type_id);
      const kg =
        (ln.bag_count || 0) * Number(bt?.weight_per_bag_kg ?? 0) + Number(ln.loose_kg || 0);
      if (kg <= 0) continue;
      const key = ln.owner_type === "job_work" ? `jw:${ln.customer_id}` : "owned";
      const prev = byKey.get(key);
      const name =
        ln.owner_type === "job_work"
          ? resolveCustomerName(ln.customer_id, customerLabels) ?? "customer"
          : undefined;
      const totalKg = (prev?.kg ?? 0) + kg;
      byKey.set(key, {
        key,
        kg: totalKg,
        owner_type: ln.owner_type,
        customer_id: ln.customer_id,
        label:
          ln.owner_type === "owned"
            ? `Owned (${formatQtyKg(totalKg)} input)`
            : `Job work · ${name} (${formatQtyKg(totalKg)} input)`,
      });
    }
    return [...byKey.values()];
  }, [job?.owner_allocation_weights, inputLinesForApi, getBagType, customerLabels]);

  const inputWillCreateMix = useMemo(
    () => (job ? willCreateMix(job, inputLinesForApi) : false),
    [job, inputLinesForApi]
  );

  useEffect(() => {
    if (!job) return;
    if (job.output_allocation_locked && job.output_allocation_mode) {
      setOutputAllocationMode(job.output_allocation_mode);
      if (job.single_allocation_owner_type === "job_work" && job.single_allocation_customer_id != null) {
        setSingleAllocationOwnerKey(`jw:${job.single_allocation_customer_id}`);
      } else if (job.single_allocation_owner_type === "owned") {
        setSingleAllocationOwnerKey("owned");
      }
      return;
    }
    if (!inputWillCreateMix) return;
    const weights = allocationOwnerOptions.map((o) => ({
      owner_type: o.owner_type as "owned" | "job_work",
      customer_id: o.customer_id,
      input_kg: String(o.kg),
      share_pct: "0",
    }));
    if (weights.length) {
      setSingleAllocationOwnerKey(defaultSingleOwnerKey(weights));
    }
    setOutputAllocationMode("proportional");
  }, [
    job?.id,
    job?.output_allocation_locked,
    job?.output_allocation_mode,
    job?.single_allocation_owner_type,
    job?.single_allocation_customer_id,
    allocationOwnerOptions,
    inputWillCreateMix,
  ]);

  const ownerFilterForLine = (ln: InputLineForm): StockOwnerFilter => ({
    owner_type: ln.owner_type,
    customer_id: ln.owner_type === "job_work" && ln.customer_id ? Number(ln.customer_id) : null,
  });

  const balanceReturnLinesForApi = useMemo(
    () =>
      outputForm.balance_return_lines
        .filter((ln) => balanceReturnLineStarted(ln))
        .map((ln) => ({
          location_id: Number(ln.location_id),
          bag_type_id: Number(ln.bag_type_id),
          bag_count: parseBagCount(ln.bag_count),
          loose_kg: parseLooseKg(ln.loose_kg),
        })),
    [outputForm.balance_return_lines]
  );

  const outputLinesForApi = useMemo(
    () =>
      outputForm.output_lines
        .filter((ln) => outputLineStarted(ln))
        .map((ln) => ({
          brand_id: Number(ln.brand_id),
          location_id: Number(ln.location_id),
          bag_type_id: Number(ln.bag_type_id),
          bag_count: parseBagCount(ln.bag_count),
          loose_kg: parseLooseKg(ln.loose_kg),
        })),
    [outputForm.output_lines]
  );

  const inputLineStockInfo = useMemo(() => {
    if (!job) return [] as { available: string; warning: string; hasEarlierReserved: boolean }[];
    return inputForm.input_lines.map((ln, idx) => {
      const stock = stockByLocation[ln.location_id] ?? [];
      const bt = getBagType(ln.bag_type_id);
      const row = stockRow(
        stock,
        String(job.input_product_id),
        String(job.input_brand_id),
        ln.bag_type_id,
        ownerFilterForLine(ln)
      );
      const sameBucket = (i: number) =>
        inputForm.input_lines[i].location_id === ln.location_id &&
        inputForm.input_lines[i].bag_type_id === ln.bag_type_id &&
        inputForm.input_lines[i].owner_type === ln.owner_type &&
        inputForm.input_lines[i].customer_id === ln.customer_id;
      const reservedEarlier = reservedStockFromEarlierLines(
        bt,
        inputForm.input_lines,
        idx,
        sameBucket
      );
      const reservedSiblings = reservedStockFromSiblingLines(
        bt,
        inputForm.input_lines,
        idx,
        sameBucket
      );
      const hasEarlierReserved = reservedEarlier.bagCount > 0 || reservedEarlier.looseKg > 0;
      const available =
        row && bt
          ? formatRemainingStockAfterReserved(bt, row, reservedEarlier.bagCount, reservedEarlier.looseKg)
          : "";
      const warning = stockExceedsMessageWithReserved(
        bt,
        ln.bag_count,
        ln.loose_kg,
        row,
        reservedSiblings.bagCount,
        reservedSiblings.looseKg
      );
      const reprocessWarning =
        ln.input_source === "balance_reprocess" && warning
          ? `Returned balance may have been sold; stock here: ${available || "none"}`
          : warning;
      return { available, warning: reprocessWarning, hasEarlierReserved };
    });
  }, [inputForm.input_lines, job, getBagType, stockByLocation]);

  const pendingReprocessKg = useMemo(() => {
    let total = 0;
    for (const ln of inputLinesForApi) {
      if (ln.input_source !== "balance_reprocess") continue;
      const bt = getBagType(ln.bag_type_id);
      total += calcPreviewTotalKg(bt, ln.bag_count, ln.loose_kg);
    }
    return total;
  }, [inputLinesForApi, getBagType]);

  const inputValidationErrors = useMemo(() => {
    if (!job) return [] as string[];
    const errs: string[] = [];
    if (availableReprocessKg <= 0 && inputLinesForApi.some((ln) => ln.input_source === "balance_reprocess")) {
      errs.push("No unclean balance returned in this job yet; use From stock only");
    }
    if (pendingReprocessKg > availableReprocessKg) {
      errs.push(
        `Reprocess (${pendingReprocessKg.toFixed(2)} kg) exceeds unclean balance available from this job (${availableReprocessKg.toFixed(2)} kg)`
      );
    }
    inputForm.input_lines.forEach((ln, i) => {
      if (!stockLineStarted(ln)) return;
      if (!ln.location_id) errs.push(`Input line ${i + 1}: select location`);
      const stock = stockByLocation[ln.location_id] ?? [];
      const btOpts = bagTypesFromStock(stock, String(job.input_product_id), String(job.input_brand_id));
      if (!ln.bag_type_id) errs.push(`Input line ${i + 1}: select bag type`);
      if (ln.owner_type === "job_work" && !ln.customer_id) {
        errs.push(`Input line ${i + 1}: select customer for job work stock`);
      }
      else if (!btOpts.some((o) => String(o.id) === ln.bag_type_id)) {
        errs.push(`Input line ${i + 1}: no stock for this bag type`);
      }
      const bt = getBagType(ln.bag_type_id);
      const qtyErr = validateStockLineQty(bt, ln, `Input line ${i + 1}`);
      if (qtyErr) errs.push(qtyErr);
      const stockInfo = inputLineStockInfo[i];
      if (stockInfo?.warning) errs.push(`Input line ${i + 1}: ${stockInfo.warning}`);
    });
    return errs;
  }, [inputForm.input_lines, job, getBagType, stockByLocation, inputLineStockInfo, availableReprocessKg, pendingReprocessKg, inputLinesForApi]);

  const outputValidationErrors = useMemo(() => {
    const errs: string[] = [];
    outputForm.output_lines.forEach((ln, i) => {
      if (!outputLineStarted(ln)) return;
      if (!ln.brand_id) errs.push(`Output line ${i + 1}: select brand`);
      if (!ln.location_id) errs.push(`Output line ${i + 1}: select location`);
      if (!ln.bag_type_id) errs.push(`Output line ${i + 1}: select bag type`);
      const bt = getBagType(ln.bag_type_id);
      const qtyErr = validateStockLineQty(bt, ln, `Output line ${i + 1}`);
      if (qtyErr) errs.push(qtyErr);
    });
    outputForm.balance_return_lines.forEach((ln, i) => {
      if (!balanceReturnLineStarted(ln)) return;
      if (!ln.location_id) errs.push(`Balance return line ${i + 1}: select location`);
      if (!ln.bag_type_id) errs.push(`Balance return line ${i + 1}: select bag type`);
      const bt = getBagType(ln.bag_type_id);
      const qtyErr = validateStockLineQty(bt, ln, `Balance return line ${i + 1}`);
      if (qtyErr) errs.push(qtyErr);
    });
    return errs;
  }, [outputForm.output_lines, outputForm.balance_return_lines, getBagType]);

  const pendingPowderKg = useMemo(
    () => powderKgFromLine(outputForm.powder_line, getBagType),
    [outputForm.powder_line, getBagType]
  );

  const powderBrandConfigured = bookSettings?.powder_brand_id != null;

  const wasteValidationErrors = useMemo(() => {
    const errs: string[] = [];
    if (powderLineStarted(outputForm.powder_line)) {
      const ln = outputForm.powder_line;
      if (!ln.brand_id) errs.push("Powder: select brand");
      if (!ln.location_id) errs.push("Powder: select storage location");
      if (!ln.bag_type_id) errs.push("Powder: select bag type");
      const bt = getBagType(ln.bag_type_id);
      const qtyErr = validateStockLineQty(bt, ln, "Powder");
      if (qtyErr) errs.push(qtyErr);
    }
    return errs;
  }, [outputForm.powder_line, getBagType]);

  const batchesForBalance = useMemo(
    () => activeProcessingBatches(job?.batches ?? []),
    [job?.batches]
  );

  const committedMassBalance = useMemo(
    () => computeMassBalance(batchesForBalance, bagTypeCache.list),
    [batchesForBalance, bagTypeCache.list]
  );

  const outputPendingMassBalance = useMemo(
    () =>
      computeMassBalance(batchesForBalance, bagTypeCache.list, {
        outputLines: outputLinesForApi,
        balanceReturnLines: balanceReturnLinesForApi,
        dustKg: 0,
        stoneKg: 0,
        sackWeightWasteKg: 0,
        powderKg: 0,
        miscellaneousWasteKg: 0,
      }),
    [batchesForBalance, bagTypeCache.list, outputLinesForApi, balanceReturnLinesForApi]
  );

  const wastePendingMassBalance = useMemo(
    () =>
      computeMassBalance(batchesForBalance, bagTypeCache.list, {
        dustKg: parseOptionalNumber(outputForm.dust_kg),
        stoneKg: parseOptionalNumber(outputForm.stone_kg),
        sackWeightWasteKg: parseOptionalNumber(outputForm.sack_weight_waste_kg),
        powderKg: pendingPowderKg,
        miscellaneousWasteKg: 0,
      }),
    [
      batchesForBalance,
      bagTypeCache.list,
      outputForm.dust_kg,
      outputForm.stone_kg,
      outputForm.sack_weight_waste_kg,
      pendingPowderKg,
    ]
  );

  const massBalanceIncludesPending = activeTab === "output" || activeTab === "waste";
  const displayMassBalance = useMemo(() => {
    if (activeTab === "output") return outputPendingMassBalance;
    if (activeTab === "waste") return wastePendingMassBalance;
    return committedMassBalance;
  }, [activeTab, committedMassBalance, outputPendingMassBalance, wastePendingMassBalance]);

  const canSubmitInput =
    !completed && !inputLocked && inputLinesForApi.length > 0 && inputValidationErrors.length === 0;

  const canSubmitOutput =
    !completed &&
    outputBalanceHasContent(outputForm) &&
    outputValidationErrors.length === 0 &&
    outputPendingMassBalance.isValid;

  const canSubmitWaste =
    !completed &&
    wasteHasContent(outputForm) &&
    wasteValidationErrors.length === 0 &&
    wastePendingMassBalance.isValid;

  const canComplete =
    !completed &&
    (summary?.batch_count ?? 0) > 0 &&
    !inputFormHasContent(inputForm) &&
    !outputFormHasContent(outputForm) &&
    committedMassBalance.isValid;

  const submitInputBatch = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !canSubmitInput || !job) return;

    if (inputWillCreateMix && outputAllocationMode === "single_owner") {
      setInputMixConfirmOpen(true);
      return;
    }
    await submitInputBatchConfirmed();
  };

  const submitInputBatchConfirmed = async () => {
    if (!id || !canSubmitInput || !job) return;

    if (!inputBatchIdemRef.current) inputBatchIdemRef.current = newIdempotencyKey();
    setError("");
    setSuccess("");
    await guardedSubmit(async () => {
      try {
      const payload: Record<string, unknown> = {
        input_lines: inputLinesForApi,
        output_lines: [],
        balance_return_lines: [],
        ...ZERO_BATCH,
      };
      if (inputWillCreateMix) {
        payload.output_allocation_mode = outputAllocationMode;
        if (outputAllocationMode === "single_owner") {
          const [ownerType, customerId] = parseOwnerKey(singleAllocationOwnerKey);
          payload.single_allocation_owner_type = ownerType;
          if (ownerType === "job_work") {
            payload.single_allocation_customer_id = customerId;
          }
        }
      }
      const updated = await api.post<ProcessingJob>(
        `/api/operations/processing/${id}/batches`,
        payload,
        { headers: idempotencyHeaders(inputBatchIdemRef.current) }
      );
      inputBatchIdemRef.current = null;
      setJob(updated);
      reloadInputLocationsStock(inputForm.input_lines);
      setInputForm(emptyInputForm());
      setSuccess("Input batch saved.");
      } catch (e) {
        setError(errMsg(e));
      }
    });
  };

  const submitOutputBatch = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !canSubmitOutput || !job) return;

    if (!outputBatchIdemRef.current) outputBatchIdemRef.current = newIdempotencyKey();
    setError("");
    setSuccess("");
    await guardedSubmit(async () => {
      try {
      const updated = await api.post<ProcessingJob>(
        `/api/operations/processing/${id}/batches`,
        {
          input_lines: [],
          output_lines: outputLinesForApi,
          balance_return_lines: balanceReturnLinesForApi,
          dust_kg: 0,
          stone_kg: 0,
          sack_weight_waste_kg: 0,
          powder_kg: 0,
          miscellaneous_waste_kg: 0,
        },
        { headers: idempotencyHeaders(outputBatchIdemRef.current) }
      );
      outputBatchIdemRef.current = null;
      setJob(updated);
      setOutputForm((f) => ({
        ...f,
        output_lines: [emptyOutputLine()],
        balance_return_lines: [emptyBalanceReturnLine()],
      }));
      setSuccess("Output batch saved.");
      } catch (e) {
        setError(errMsg(e));
      }
    });
  };

  const submitWasteBatch = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !canSubmitWaste || !job) return;

    if (!wasteBatchIdemRef.current) wasteBatchIdemRef.current = newIdempotencyKey();
    setError("");
    setSuccess("");
    await guardedSubmit(async () => {
      try {
      const payload: Record<string, unknown> = {
          input_lines: [],
          output_lines: [],
          balance_return_lines: [],
          dust_kg: parseOptionalNumber(outputForm.dust_kg),
          stone_kg: parseOptionalNumber(outputForm.stone_kg),
          sack_weight_waste_kg: parseOptionalNumber(outputForm.sack_weight_waste_kg),
          powder_kg: 0,
          miscellaneous_waste_kg: 0,
        };
      if (powderLineStarted(outputForm.powder_line)) {
        const ln = outputForm.powder_line;
        payload.powder_line = {
          brand_id: Number(ln.brand_id),
          location_id: Number(ln.location_id),
          bag_type_id: Number(ln.bag_type_id),
          bag_count: parseBagCount(ln.bag_count),
          loose_kg: parseLooseKg(ln.loose_kg),
        };
      }
      const updated = await api.post<ProcessingJob>(
        `/api/operations/processing/${id}/batches`,
        payload,
        { headers: idempotencyHeaders(wasteBatchIdemRef.current) }
      );
      wasteBatchIdemRef.current = null;
      setJob(updated);
      setOutputForm((f) => ({
        ...f,
        dust_kg: "",
        stone_kg: "",
        sack_weight_waste_kg: "",
        powder_line: emptyPowderLine(),
      }));
      setSuccess("Waste batch saved.");
      } catch (e) {
        setError(errMsg(e));
      }
    });
  };

  const startCompleteProcess = () => {
    if (!id || !job || completed) return;

    if (inputFormHasContent(inputForm) || outputFormHasContent(outputForm)) {
      setError("Submit or clear unsaved data on the Input, Output, or Waste tab before completing.");
      return;
    }

    if (inputValidationErrors.length > 0 || outputValidationErrors.length > 0 || wasteValidationErrors.length > 0) {
      setError("Fix validation errors before completing.");
      return;
    }

    const s = jobSummary(job);
    const totalFresh = Number(s.total_fresh_input_kg);
    const totalOutput = totalOutputKg(s);
    const netBalance = Number(s.net_balance_kg);

    if (totalFresh > 0 && totalOutput === 0) {
      setCompleteFlowConfirmOpen(true);
      return;
    }

    if (netBalance > 0.001 && totalFresh > 0 && netBalance / totalFresh > 0.05) {
      setCompleteBalanceConfirmOpen(true);
      return;
    }

    if ((s.batch_count ?? 0) === 0) {
      setError("Cannot complete without at least one batch.");
      return;
    }

    setError("");
    setSuccess("");
    setCompleteAuthError("");
    setCompleteAuthOpen(true);
  };

  const continueCompleteProcess = () => {
    if (!job || completed) return;
    const s = jobSummary(job);
    const totalFresh = Number(s.total_fresh_input_kg);
    const totalOutput = totalOutputKg(s);
    const netBalance = Number(s.net_balance_kg);
    if (totalFresh > 0 && totalOutput === 0) {
      setCompleteFlowConfirmOpen(true);
      return;
    }
    if (netBalance > 0.001 && totalFresh > 0 && netBalance / totalFresh > 0.05) {
      setCompleteBalanceConfirmOpen(true);
      return;
    }
    setError("");
    setSuccess("");
    setCompleteAuthError("");
    setCompleteAuthOpen(true);
  };

  const confirmCompleteProcess = async (authorizationPassword: string) => {
    if (!id || !job || completed) return;

    if (!completeIdemRef.current) completeIdemRef.current = newIdempotencyKey();
    setCompleteAuthError("");
    await guardedSubmit(async () => {
      try {
        const updated = await api.post<ProcessingJob>(
          `/api/operations/processing/${id}/complete`,
          {
            input_lines: [],
            output_lines: [],
            balance_return_lines: [],
            ...ZERO_BATCH,
          },
          { headers: idempotencyVoidAuthHeaders(completeIdemRef.current!, authorizationPassword) }
        );
        completeIdemRef.current = null;
        setJob(updated);
        setActiveTab("summary");
        setCompleteAuthOpen(false);
        setSuccess("Job completed.");
      } catch (e) {
        const msg = errMsg(e);
        if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
          setCompleteAuthError(msg);
        } else {
          setCompleteAuthOpen(false);
          setError(msg);
        }
        throw e;
      }
    });
  };

  const confirmVoidBatch = async (authorizationPassword: string) => {
    if (!voidBatchTarget) return;
    setVoidBatchAuthError("");
    try {
      const updated = await api.post<ProcessingJob>(
        `/api/operations/processing/batches/${voidBatchTarget.id}/void`,
        {},
        { headers: idempotencyVoidAuthHeaders(newIdempotencyKey(), authorizationPassword) }
      );
      setJob(updated);
      setVoidBatchTarget(null);
      setSuccess("Batch voided — stock reversed and job summary updated.");
      if (updated.status === "open") {
        setActiveTab("summary");
      }
    } catch (e) {
      const msg = errMsg(e);
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidBatchAuthError(msg);
      } else {
        setVoidBatchTarget(null);
        setError(msg);
      }
      throw e;
    }
  };

  if (!jobLoadDone) {
    return (
      <>
        <PageHeader
          eyebrow="Processing job"
          title="Loading job…"
          actions={
            <Link to="/operations/processing">
              <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
                Back
              </Button>
            </Link>
          }
        />
        <div className="grid min-w-0 grid-cols-1 items-start lg:grid-cols-[3fr_71fr_3fr_25fr]">
          <div className="hidden lg:col-start-2 lg:block">
            <div className="space-y-4">
              <Skeleton className="h-12 w-full rounded-xl" />
              <Skeleton className="h-64 w-full rounded-2xl" />
            </div>
          </div>
          <Skeleton className="hidden h-96 w-full rounded-2xl lg:col-start-4 lg:block" />
        </div>
      </>
    );
  }

  if (!job) {
    return (
      <>
        <PageHeader
          eyebrow="Processing job"
          title="Could not load job"
          actions={
            <Link to="/operations/processing">
              <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
                Back
              </Button>
            </Link>
          }
        />
        {error && (
          <Banner tone="danger" className="mb-4">
            {error}
          </Banner>
        )}
        <EmptyState
          icon={<Layers className="h-8 w-8" />}
          title="Job unavailable"
          description={error || "This processing job could not be loaded. It may have been removed or the server returned an error."}
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button type="button" variant="secondary" onClick={loadJob}>
                Retry
              </Button>
              <Link to="/operations/processing">
                <Button variant="ghost" leftIcon={<ArrowLeft className="h-4 w-4" />}>
                  Back to jobs
                </Button>
              </Link>
            </div>
          }
        />
      </>
    );
  }

  const allBatches = [...(job.batches ?? [])].sort(
    (a, b) => new Date(b.operation_at).getTime() - new Date(a.operation_at).getTime()
  );
  const activeBatchCount = activeProcessingBatches(allBatches).length;
  const fromParam = searchParams.get("from");
  const fromHistory = fromParam === "history" || (fromParam !== "open" && job.status === "completed");
  const backTo = fromHistory ? "/histories/processing" : "/operations/processing";
  const backLabel = fromHistory ? "Back to history" : "Back to processing";

  return (
    <>
      <div className="min-w-0">
        <div
          ref={layoutGridRef}
          className="grid min-w-0 grid-cols-1 items-start lg:grid-cols-[3fr_71fr_3fr_25fr]"
        >
          <div className="min-w-0 space-y-4 lg:col-start-2 lg:row-start-1">
            <div className="sticky top-16 z-20 -mx-1 mb-1 rounded-2xl border border-line/60 bg-[rgb(var(--canvas)/0.94)] px-3 py-3 shadow-sm backdrop-blur-md sm:px-4">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1 pt-0.5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-300">
                    {fromHistory ? (
                      <Link to="/histories/processing" className="hover:underline">
                        Processing history
                      </Link>
                    ) : (
                      <Link to="/operations/processing" className="hover:underline">
                        Processing
                      </Link>
                    )}
                    <span className="mx-1.5 text-ink-subtle">/</span>
                    <span className="text-ink-muted">Job</span>
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <h1 className="truncate text-lg font-bold tracking-tight text-ink sm:text-xl">
                      {job.input_product_name} · {job.input_brand_name}
                    </h1>
                    <Badge tone={jobStatusTone(job.status)} size="md">
                      {job.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">
                    {job.completed_at
                      ? `Completed ${formatDateTime(job.completed_at)}`
                      : "Record input and output batches, then complete when mass balance is valid."}
                  </p>
                </div>
                <Link
                  to={backTo}
                  className="group inline-flex shrink-0 items-center gap-2.5 rounded-full border border-line/70 bg-surface px-2.5 py-1.5 pr-3.5 text-sm font-semibold text-ink shadow-sm transition hover:border-primary-300 hover:bg-primary-50 hover:text-primary-800 dark:hover:border-primary-700 dark:hover:bg-primary-950/40 dark:hover:text-primary-100"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-md transition group-hover:scale-105">
                    <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <span className="hidden sm:inline">{backLabel}</span>
                  <span className="sm:hidden">Back</span>
                </Link>
              </div>
            </div>

            {error && (
              <Banner tone="danger" onClose={() => setError("")}>
                {error}
              </Banner>
            )}
            {success && (
              <Banner tone="success" onClose={() => setSuccess("")}>
                {success}
              </Banner>
            )}

            <MassBalancePanel
              balance={displayMassBalance}
              includesPending={massBalanceIncludesPending}
            />

            <Tabs
              value={activeTab}
              onChange={(id) => setActiveTab(id as TabId)}
              variant="pill"
              size="lg"
              className="min-w-0"
            >
        <Tab id="input" label="Input batch" badge={activeBatchCount > 0 ? activeBatchCount : undefined}>
          <Card>
            <CardHeader
              title="Input batch"
              subtitle="Subtract raw stock for this job's product and brand."
            />
            <CardBody>
              {completed ? (
                <EmptyState
                  icon={<ArrowDownToLine className="h-8 w-8" />}
                  title="Job completed"
                  description="Input batches are read-only. See the Summary tab for the full history."
                />
              ) : inputLocked ? (
                <EmptyState
                  icon={<ArrowDownToLine className="h-8 w-8" />}
                  title="Input closed"
                  description={
                    ownerRulesMessage ??
                    "Mixed-owner jobs do not allow further input. Create a new processing job for additional material."
                  }
                />
              ) : (
                <form onSubmit={submitInputBatch} className="space-y-6">
                  {ownerRulesMessage && (
                    <Banner tone="info">{ownerRulesMessage}</Banner>
                  )}
                  {availableReprocessKg > 0 && (
                    <Banner tone="info" title="Unclean balance available">
                      {formatQtyKg(availableReprocessKg)} can be reprocessed from this job instead of fresh stock.
                    </Banner>
                  )}

                  <ProcessingSection title="Input lines" subtitle="Pull stock from a location or reuse unclean balance.">
                    <div className="space-y-4">
                      {inputForm.input_lines.map((ln, idx) => {
                        const stockAll = stockByLocation[ln.location_id] ?? [];
                        const stock = stockAll.filter((row) => {
                          if (ln.owner_type === "owned") return !row.owner_type || row.owner_type === "owned";
                          if (!ln.customer_id) return row.owner_type === "job_work";
                          return row.owner_type === "job_work" && row.customer_id === Number(ln.customer_id);
                        });
                        const bagOpts = bagTypesFromStock(
                          stock,
                          String(job.input_product_id),
                          String(job.input_brand_id)
                        );
                        const bt = getBagType(ln.bag_type_id);
                        const row = stockRow(
                          stock,
                          String(job.input_product_id),
                          String(job.input_brand_id),
                          ln.bag_type_id,
                          ownerFilterForLine(ln)
                        );
                        const stockInfo = inputLineStockInfo[idx];
                        const lineQtyKg = calcPreviewTotalKg(bt, ln.bag_count, ln.loose_kg);
                        return (
                          <ProcessingLineCard
                            key={ln.key}
                            footer={
                              <div className="mt-3 space-y-2">
                                {stockInfo?.available && (
                                  <p className="text-sm text-ink-muted">
                                    {stockInfo.hasEarlierReserved
                                      ? "Remaining (after earlier lines):"
                                      : "Available:"}{" "}
                                    {stockInfo.available}
                                  </p>
                                )}
                                {stockInfo?.warning && (
                                  <Banner tone="warning">{stockInfo.warning}</Banner>
                                )}
                                {inputForm.input_lines.length > 1 && (
                                  <div className="flex justify-end">
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      leftIcon={<Trash2 className="h-4 w-4" />}
                                      onClick={() =>
                                        setInputForm((f) => ({
                                          ...f,
                                          input_lines: f.input_lines.filter((_, i) => i !== idx),
                                        }))
                                      }
                                    >
                                      Remove line
                                    </Button>
                                  </div>
                                )}
                              </div>
                            }
                          >
                            <FormField label="Stock owner" required>
                              {({ id }) => (
                                <Select
                                  id={id}
                                  value={ln.owner_type}
                                  disabled={Boolean(lockedInputOwner)}
                                  onChange={(e) => {
                                    if (lockedInputOwner) return;
                                    const v = e.target.value as "owned" | "job_work";
                                    setInputForm((f) => {
                                      const lines = [...f.input_lines];
                                      lines[idx] = {
                                        ...lines[idx],
                                        owner_type: v,
                                        customer_id: "",
                                        bag_type_id: "",
                                        ...emptyQtyFields(),
                                      };
                                      return { ...f, input_lines: lines };
                                    });
                                  }}
                                >
                                  <option value="owned">Owned stock</option>
                                  <option value="job_work">Job work (customer)</option>
                                </Select>
                              )}
                            </FormField>
                            {ln.owner_type === "job_work" && (
                              <FormField label="Customer" required>
                                {() => (
                                  <AsyncSearchCombobox
                                    value={ln.customer_id ? Number(ln.customer_id) : null}
                                    disabled={Boolean(lockedInputOwner)}
                                    onChange={(customerId, opt) => {
                                      if (lockedInputOwner) return;
                                      const v = customerId != null ? String(customerId) : "";
                                      if (v && opt?.label) {
                                        setCustomerLabels((prev) => ({
                                          ...prev,
                                          [Number(v)]: opt.label,
                                        }));
                                      }
                                      setInputForm((f) => {
                                        const lines = [...f.input_lines];
                                        lines[idx] = {
                                          ...lines[idx],
                                          customer_id: v,
                                          bag_type_id: "",
                                          ...emptyQtyFields(),
                                        };
                                        return { ...f, input_lines: lines };
                                      });
                                    }}
                                    searchFn={searchCustomers}
                                    placeholder="Search customer…"
                                    emptyText="No matching customer"
                                    initialLabel={
                                      ln.customer_id
                                        ? resolveCustomerName(Number(ln.customer_id), customerLabels)
                                        : lockedInputOwner?.customer_id === ln.customer_id
                                          ? job.input_allowed_owner?.customer_name ??
                                            job.single_allocation_customer_name ??
                                            undefined
                                          : undefined
                                    }
                                  />
                                )}
                              </FormField>
                            )}
                            <FormField label="Source">
                              {({ id }) => (
                                <Select
                                  id={id}
                                  value={ln.input_source}
                                  onChange={(e) => {
                                    const v = e.target.value as ProcessingInputSource;
                                    setInputForm((f) => {
                                      const lines = [...f.input_lines];
                                      lines[idx] = { ...lines[idx], input_source: v };
                                      return { ...f, input_lines: lines };
                                    });
                                  }}
                                >
                                  <option value="fresh">From stock</option>
                                  {availableReprocessKg > 0 && (
                                    <option value="balance_reprocess">Use unclean balance</option>
                                  )}
                                </Select>
                              )}
                            </FormField>
                            <FormField label="Location" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.location_id ? Number(ln.location_id) : null}
                                  onChange={(locationId) => {
                                    const v = locationId != null ? String(locationId) : "";
                                    setInputForm((f) => {
                                      const lines = [...f.input_lines];
                                      lines[idx] = {
                                        ...lines[idx],
                                        location_id: v,
                                        bag_type_id: "",
                                        ...emptyQtyFields(),
                                      };
                                      return { ...f, input_lines: lines };
                                    });
                                    if (v) loadStock(v);
                                  }}
                                  searchFn={searchLocations}
                                  placeholder="Search location…"
                                  emptyText="No matching location"
                                />
                              )}
                            </FormField>
                            <FormField label="Bag type" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.bag_type_id ? Number(ln.bag_type_id) : null}
                                  disabled={!ln.location_id}
                                  onChange={(bagTypeId, opt) => {
                                    const masterOpt = opt as MasterComboOption | undefined;
                                    if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);
                                    const v = bagTypeId != null ? String(bagTypeId) : "";
                                    setInputForm((f) => {
                                      const lines = [...f.input_lines];
                                      lines[idx] = { ...lines[idx], bag_type_id: v, ...emptyQtyFields() };
                                      return { ...f, input_lines: lines };
                                    });
                                  }}
                                  searchFn={searchBagTypes}
                                  placeholder="Search bag type…"
                                  emptyText="No matching bag type"
                                  initialLabel={
                                    ln.bag_type_id
                                      ? bagOpts.find((o) => String(o.id) === ln.bag_type_id)?.label ??
                                        getBagType(ln.bag_type_id)?.name
                                      : undefined
                                  }
                                />
                              )}
                            </FormField>
                            {!isLooseBagType(bt) && (
                              <FormField label="Bags" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    max={row?.bag_count ?? undefined}
                                    placeholder={PH_BAGS}
                                    value={ln.bag_count}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setInputForm((f) => {
                                        const lines = [...f.input_lines];
                                        lines[idx] = { ...lines[idx], bag_count: v };
                                        return { ...f, input_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                            {(isLooseBagType(bt) || ln.loose_kg) && (
                              <FormField label="Loose kg" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    step="0.01"
                                    suffix="kg"
                                    max={row ? Number(row.loose_kg) : undefined}
                                    placeholder={PH_LOOSE_KG}
                                    value={ln.loose_kg}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setInputForm((f) => {
                                        const lines = [...f.input_lines];
                                        lines[idx] = { ...lines[idx], loose_kg: v };
                                        return { ...f, input_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                            {lineQtyKg > 0 && (
                              <FormField label="Quantity kg">
                                {({ id }) => (
                                  <Input id={id} readOnly value={lineQtyKg.toFixed(2)} className="v2-mono" />
                                )}
                              </FormField>
                            )}
                          </ProcessingLineCard>
                        );
                      })}
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      leftIcon={<Plus className="h-4 w-4" />}
                      onClick={() =>
                        setInputForm((f) => ({
                          ...f,
                          input_lines: [...f.input_lines, emptyInputLine()],
                        }))
                      }
                    >
                      Add input line
                    </Button>
                  </ProcessingSection>

                  {inputWillCreateMix && (
                    <Card className="border-line/70 bg-surface-subtle/40">
                      <CardBody className="space-y-4">
                        <div>
                          <p className="text-sm font-semibold text-ink">Output allocation for this mixed job</p>
                          <p className="mt-1 text-sm text-ink-muted">
                            Choose how finished output, balance return, and waste are attributed — billing is manual.
                          </p>
                        </div>
                        <SegmentedControl
                          ariaLabel="Output allocation mode"
                          value={outputAllocationMode}
                          onChange={setOutputAllocationMode}
                          options={[
                            {
                              value: "proportional",
                              label: "Split by input proportion",
                              hint: "Default — closes further input",
                            },
                            {
                              value: "single_owner",
                              label: "Single owner 100%",
                              hint: "All output to one owner",
                            },
                          ]}
                        />
                        {outputAllocationMode === "single_owner" && allocationOwnerOptions.length > 0 && (
                          <FormField label="100% of all outputs to" required>
                            {({ id: selectId }) => (
                              <Select
                                id={selectId}
                                value={singleAllocationOwnerKey}
                                onChange={(e) => setSingleAllocationOwnerKey(e.target.value)}
                              >
                                {allocationOwnerOptions.map((opt) => (
                                  <option key={opt.key} value={opt.key}>
                                    {opt.label}
                                  </option>
                                ))}
                              </Select>
                            )}
                          </FormField>
                        )}
                      </CardBody>
                    </Card>
                  )}

                  {inputValidationErrors.length > 0 && (
                    <Banner tone="warning" title="Fix these before submitting">
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {inputValidationErrors.map((m) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </Banner>
                  )}

                  <div className="flex flex-wrap gap-2 border-t border-line/60 pt-4">
                    <Button type="submit" loading={saving} disabled={!canSubmitInput}>
                      Submit input batch
                    </Button>
                    {inputFormHasContent(inputForm) && (
                      <Button type="button" variant="ghost" onClick={() => setInputForm(emptyInputForm())}>
                        Clear form
                      </Button>
                    )}
                  </div>
                </form>
              )}
            </CardBody>
          </Card>
          <Card className="mt-5">
            <CardHeader title="Input history" subtitle="Recorded input lines for this tab. See Summary for all activity or Batch history to void." />
            <CardBody>
              <ProcessingInputLog batches={allBatches} customerNames={customerNameMap} />
            </CardBody>
          </Card>
        </Tab>

        <Tab id="output" label="Output & balance">
          <Card>
            <CardHeader
              title="Output & balance return"
              subtitle={`Add finished stock and return unclean balance (${job.input_product_name} / ${job.input_brand_name}).`}
            />
            <CardBody>
              {completed ? (
                <EmptyState
                  icon={<ArrowUpFromLine className="h-8 w-8" />}
                  title="Job completed"
                  description="Output is read-only. See Summary for all activity or Batch history to void a batch."
                />
              ) : (
                <form onSubmit={submitOutputBatch} className="space-y-6">
                  {ownerRulesMessage && (
                    <Banner tone="info">{ownerRulesMessage}</Banner>
                  )}

                  <ProcessingSection title="Output lines" subtitle="Finished stock added to inventory.">
                    <div className="space-y-4">
                      {outputForm.output_lines.map((ln, idx) => {
                        const bt = getBagType(ln.bag_type_id);
                        return (
                          <ProcessingLineCard
                            key={ln.key}
                            footer={
                              outputForm.output_lines.length > 1 ? (
                                <div className="mt-3 flex justify-end">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    leftIcon={<Trash2 className="h-4 w-4" />}
                                    onClick={() =>
                                      setOutputForm((f) => ({
                                        ...f,
                                        output_lines: f.output_lines.filter((_, i) => i !== idx),
                                      }))
                                    }
                                  >
                                    Remove line
                                  </Button>
                                </div>
                              ) : undefined
                            }
                          >
                            <FormField label="Brand" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.brand_id ? Number(ln.brand_id) : null}
                                  onChange={(brandId) => {
                                    const v = brandId != null ? String(brandId) : "";
                                    setOutputForm((f) => {
                                      const lines = [...f.output_lines];
                                      lines[idx] = { ...lines[idx], brand_id: v, brand_label: undefined };
                                      return { ...f, output_lines: lines };
                                    });
                                  }}
                                  searchFn={searchBrands}
                                  placeholder="Search brand…"
                                  emptyText="No matching brand"
                                  initialLabel={ln.brand_label}
                                />
                              )}
                            </FormField>
                            <FormField label="Location" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.location_id ? Number(ln.location_id) : null}
                                  onChange={(locationId) => {
                                    const v = locationId != null ? String(locationId) : "";
                                    setOutputForm((f) => {
                                      const lines = [...f.output_lines];
                                      lines[idx] = { ...lines[idx], location_id: v, location_label: undefined };
                                      return { ...f, output_lines: lines };
                                    });
                                  }}
                                  searchFn={searchLocations}
                                  placeholder="Search location…"
                                  emptyText="No matching location"
                                  initialLabel={ln.location_label}
                                />
                              )}
                            </FormField>
                            <FormField label="Bag type" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.bag_type_id ? Number(ln.bag_type_id) : null}
                                  onChange={(bagTypeId, opt) => {
                                    const masterOpt = opt as MasterComboOption | undefined;
                                    if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);
                                    const v = bagTypeId != null ? String(bagTypeId) : "";
                                    setOutputForm((f) => {
                                      const lines = [...f.output_lines];
                                      lines[idx] = {
                                        ...lines[idx],
                                        bag_type_id: v,
                                        bag_type_label: undefined,
                                        ...emptyQtyFields(),
                                      };
                                      return { ...f, output_lines: lines };
                                    });
                                  }}
                                  searchFn={searchBagTypes}
                                  placeholder="Search bag type…"
                                  emptyText="No matching bag type"
                                  initialLabel={ln.bag_type_label ?? getBagType(ln.bag_type_id)?.name}
                                />
                              )}
                            </FormField>
                            {!isLooseBagType(bt) && (
                              <FormField label="Bags" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    placeholder={PH_BAGS}
                                    value={ln.bag_count}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setOutputForm((f) => {
                                        const lines = [...f.output_lines];
                                        lines[idx] = { ...lines[idx], bag_count: v };
                                        return { ...f, output_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                            {(isLooseBagType(bt) || ln.loose_kg) && (
                              <FormField label="Loose kg" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    step="0.01"
                                    suffix="kg"
                                    placeholder={PH_LOOSE_KG}
                                    value={ln.loose_kg}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setOutputForm((f) => {
                                        const lines = [...f.output_lines];
                                        lines[idx] = { ...lines[idx], loose_kg: v };
                                        return { ...f, output_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                          </ProcessingLineCard>
                        );
                      })}
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      leftIcon={<Plus className="h-4 w-4" />}
                      onClick={() =>
                        setOutputForm((f) => ({
                          ...f,
                          output_lines: [...f.output_lines, emptyOutputLine()],
                        }))
                      }
                    >
                      Add output line
                    </Button>
                  </ProcessingSection>

                  <ProcessingSection
                    title="Balance return"
                    subtitle={`Unclean stock back to inventory — ${job.input_product_name} / ${job.input_brand_name}`}
                  >
                    <div className="space-y-4">
                      {outputForm.balance_return_lines.map((ln, idx) => {
                        const bt = getBagType(ln.bag_type_id);
                        return (
                          <ProcessingLineCard
                            key={ln.key}
                            footer={
                              outputForm.balance_return_lines.length > 1 ? (
                                <div className="mt-3 flex justify-end">
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    leftIcon={<Trash2 className="h-4 w-4" />}
                                    onClick={() =>
                                      setOutputForm((f) => ({
                                        ...f,
                                        balance_return_lines: f.balance_return_lines.filter((_, i) => i !== idx),
                                      }))
                                    }
                                  >
                                    Remove line
                                  </Button>
                                </div>
                              ) : undefined
                            }
                          >
                            <FormField label="Location" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.location_id ? Number(ln.location_id) : null}
                                  onChange={(locationId) => {
                                    const v = locationId != null ? String(locationId) : "";
                                    setOutputForm((f) => {
                                      const lines = [...f.balance_return_lines];
                                      lines[idx] = { ...lines[idx], location_id: v };
                                      return { ...f, balance_return_lines: lines };
                                    });
                                  }}
                                  searchFn={searchLocations}
                                  placeholder="Search location…"
                                  emptyText="No matching location"
                                />
                              )}
                            </FormField>
                            <FormField label="Bag type" required>
                              {() => (
                                <AsyncSearchCombobox
                                  value={ln.bag_type_id ? Number(ln.bag_type_id) : null}
                                  onChange={(bagTypeId, opt) => {
                                    const masterOpt = opt as MasterComboOption | undefined;
                                    if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);
                                    const v = bagTypeId != null ? String(bagTypeId) : "";
                                    setOutputForm((f) => {
                                      const lines = [...f.balance_return_lines];
                                      lines[idx] = { ...lines[idx], bag_type_id: v, ...emptyQtyFields() };
                                      return { ...f, balance_return_lines: lines };
                                    });
                                  }}
                                  searchFn={searchBagTypes}
                                  placeholder="Search bag type…"
                                  emptyText="No matching bag type"
                                  initialLabel={getBagType(ln.bag_type_id)?.name}
                                />
                              )}
                            </FormField>
                            {!isLooseBagType(bt) && (
                              <FormField label="Bags" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    placeholder={PH_BAGS}
                                    value={ln.bag_count}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setOutputForm((f) => {
                                        const lines = [...f.balance_return_lines];
                                        lines[idx] = { ...lines[idx], bag_count: v };
                                        return { ...f, balance_return_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                            {(isLooseBagType(bt) || ln.loose_kg) && (
                              <FormField label="Loose kg" required>
                                {({ id }) => (
                                  <NumberInput
                                    id={id}
                                    min={0}
                                    step="0.01"
                                    suffix="kg"
                                    placeholder={PH_LOOSE_KG}
                                    value={ln.loose_kg}
                                    onChange={(e) => {
                                      const v = e.target.value;
                                      setOutputForm((f) => {
                                        const lines = [...f.balance_return_lines];
                                        lines[idx] = { ...lines[idx], loose_kg: v };
                                        return { ...f, balance_return_lines: lines };
                                      });
                                    }}
                                  />
                                )}
                              </FormField>
                            )}
                          </ProcessingLineCard>
                        );
                      })}
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      leftIcon={<Plus className="h-4 w-4" />}
                      onClick={() =>
                        setOutputForm((f) => ({
                          ...f,
                          balance_return_lines: [...f.balance_return_lines, emptyBalanceReturnLine()],
                        }))
                      }
                    >
                      Add balance return line
                    </Button>
                  </ProcessingSection>

                  {outputValidationErrors.length > 0 && (
                    <Banner tone="warning" title="Fix these before submitting">
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {outputValidationErrors.map((m) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </Banner>
                  )}

                  <div className="flex flex-wrap gap-2 border-t border-line/60 pt-4">
                    <Button type="submit" loading={saving} disabled={!canSubmitOutput}>
                      Submit output batch
                    </Button>
                    {outputBalanceHasContent(outputForm) && (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() =>
                          setOutputForm((f) => ({
                            ...f,
                            output_lines: [emptyOutputLine()],
                            balance_return_lines: [emptyBalanceReturnLine()],
                          }))
                        }
                      >
                        Clear form
                      </Button>
                    )}
                  </div>
                </form>
              )}
            </CardBody>
          </Card>
          <Card className="mt-5">
            <CardHeader title="Output & balance history" subtitle="Finished output and balance return lines." />
            <CardBody>
              <ProcessingOutputLog batches={allBatches} customerNames={customerNameMap} />
            </CardBody>
          </Card>
        </Tab>

        <Tab id="waste" label="Waste">
          <Card>
            <CardHeader
              title="Waste batch"
              subtitle="Dust, stone, and sack weight are audit-only. Powder posts as stock — pick brand, location, bag type, and quantity."
            />
            <CardBody>
              {completed ? (
                <EmptyState
                  icon={<Scale className="h-8 w-8" />}
                  title="Job completed"
                  description="Waste is read-only. See Summary for all activity or Batch history to void a batch."
                />
              ) : (
                <form onSubmit={submitWasteBatch} className="space-y-6">
                  <ProcessingSection
                    title="Waste"
                    subtitle="Remaining unaccounted quantity is auto-calculated as Misc on the Summary tab."
                    className="border-amber-200/60 bg-amber-50/30 dark:border-amber-800/40 dark:bg-amber-950/15"
                  >
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                      {(
                        [
                          ["dust_kg", "Dust kg"],
                          ["stone_kg", "Stone kg"],
                          ["sack_weight_waste_kg", "Sack weight waste kg"],
                        ] as const
                      ).map(([key, label]) => (
                        <FormField key={key} label={label}>
                          {({ id }) => (
                            <NumberInput
                              id={id}
                              min={0}
                              step="0.01"
                              suffix="kg"
                              placeholder={PH_LOOSE_KG}
                              value={outputForm[key]}
                              onChange={(e) => setOutputForm((f) => ({ ...f, [key]: e.target.value }))}
                            />
                          )}
                        </FormField>
                      ))}
                    </div>
                  </ProcessingSection>

                  <ProcessingSection
                    title="Powder stock"
                    subtitle="Adds saleable powder to inventory at the location you choose. Product master is resolved automatically (generic Powder)."
                    className="border-accent-200/60 bg-accent-50/25 dark:border-accent-800/40 dark:bg-accent-950/15"
                  >
                    <ProcessingLineCard>
                      <FormField label="Brand" required hint="Powder brand only">
                        {() => (
                          <AsyncSearchCombobox
                            value={
                              outputForm.powder_line.brand_id ? Number(outputForm.powder_line.brand_id) : null
                            }
                            onChange={(brandId) =>
                              setOutputForm((f) => ({
                                ...f,
                                powder_line: {
                                  ...f.powder_line,
                                  brand_id: brandId != null ? String(brandId) : "",
                                },
                              }))
                            }
                            searchFn={searchPowderBrands}
                            placeholder="Search powder brand…"
                            emptyText="No matching powder brand"
                          />
                        )}
                      </FormField>
                      <FormField label="Storage location" required>
                        {() => (
                          <AsyncSearchCombobox
                            value={
                              outputForm.powder_line.location_id ? Number(outputForm.powder_line.location_id) : null
                            }
                            onChange={(locationId) =>
                              setOutputForm((f) => ({
                                ...f,
                                powder_line: {
                                  ...f.powder_line,
                                  location_id: locationId != null ? String(locationId) : "",
                                },
                              }))
                            }
                            searchFn={searchLocations}
                            placeholder="Search location…"
                            emptyText="No matching location"
                          />
                        )}
                      </FormField>
                      <FormField label="Bag type" required>
                        {() => (
                          <AsyncSearchCombobox
                            value={
                              outputForm.powder_line.bag_type_id ? Number(outputForm.powder_line.bag_type_id) : null
                            }
                            onChange={(bagTypeId, opt) => {
                              const masterOpt = opt as MasterComboOption | undefined;
                              if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);
                              setOutputForm((f) => ({
                                ...f,
                                powder_line: {
                                  ...f.powder_line,
                                  bag_type_id: bagTypeId != null ? String(bagTypeId) : "",
                                  ...emptyQtyFields(),
                                },
                              }));
                            }}
                            searchFn={searchBagTypes}
                            placeholder="Search bag type…"
                            emptyText="No matching bag type"
                            initialLabel={getBagType(outputForm.powder_line.bag_type_id)?.name}
                          />
                        )}
                      </FormField>
                      {outputForm.powder_line.bag_type_id &&
                        !isLooseBagType(getBagType(outputForm.powder_line.bag_type_id)) && (
                          <FormField label="Bags" required>
                            {({ id }) => (
                              <NumberInput
                                id={id}
                                min={0}
                                step="1"
                                placeholder={PH_BAGS}
                                value={outputForm.powder_line.bag_count}
                                onChange={(e) =>
                                  setOutputForm((f) => ({
                                    ...f,
                                    powder_line: { ...f.powder_line, bag_count: e.target.value },
                                  }))
                                }
                              />
                            )}
                          </FormField>
                        )}
                      {outputForm.powder_line.bag_type_id &&
                        isLooseBagType(getBagType(outputForm.powder_line.bag_type_id)) && (
                          <FormField label="Quantity (kg)" required>
                            {({ id }) => (
                              <NumberInput
                                id={id}
                                min={0}
                                step="0.01"
                                suffix="kg"
                                placeholder={PH_LOOSE_KG}
                                value={outputForm.powder_line.loose_kg}
                                onChange={(e) =>
                                  setOutputForm((f) => ({
                                    ...f,
                                    powder_line: { ...f.powder_line, loose_kg: e.target.value },
                                  }))
                                }
                              />
                            )}
                          </FormField>
                        )}
                    </ProcessingLineCard>
                    {!powderBrandConfigured && bookSettings != null && (
                      <Banner tone="warning" className="mt-4">
                        Add a brand named &quot;Powder&quot; in Masters → Brands before recording powder stock.
                      </Banner>
                    )}
                  </ProcessingSection>

                  {wasteValidationErrors.length > 0 && (
                    <Banner tone="warning" title="Fix these before submitting">
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {wasteValidationErrors.map((m) => (
                          <li key={m}>{m}</li>
                        ))}
                      </ul>
                    </Banner>
                  )}

                  <div className="flex flex-wrap gap-2 border-t border-line/60 pt-4">
                    <Button type="submit" loading={saving} disabled={!canSubmitWaste}>
                      Submit waste batch
                    </Button>
                    {wasteHasContent(outputForm) && (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() =>
                          setOutputForm((f) => ({
                            ...f,
                            dust_kg: "",
                            stone_kg: "",
                            sack_weight_waste_kg: "",
                            powder_line: emptyPowderLine(),
                          }))
                        }
                      >
                        Clear form
                      </Button>
                    )}
                  </div>
                </form>
              )}
            </CardBody>
          </Card>
          <Card className="mt-5">
            <CardHeader title="Waste history" subtitle="Dust, stone, sack, powder, and misc per batch." />
            <CardBody>
              <ProcessingWasteLog batches={allBatches} />
            </CardBody>
          </Card>
        </Tab>

        <Tab id="summary" label="Summary" badge={summary?.batch_count}>
          <div className="space-y-5">
            {summary && (
              <SummaryCard
                summary={summary}
                batches={activeProcessingBatches(allBatches)}
                allocationHint={job.output_allocation_hint}
                inputRulesHint={job.input_rules_hint}
                customerNames={customerNameMap}
              />
            )}
            <Card>
              <CardHeader title="Activity log" subtitle="All inputs, outputs, and waste — newest first." />
              <CardBody>
                <ProcessingActivityLog batches={allBatches} customerNames={customerNameMap} />
              </CardBody>
            </Card>
            {!completed && (
              <Card className="border-accent-200/60 bg-gradient-to-br from-accent-50/40 via-surface to-surface dark:border-accent-800/40 dark:from-accent-950/20">
                <CardBody className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-lg font-semibold text-ink">Ready to close this job?</p>
                    <p className="mt-1 text-sm text-ink-muted">
                      Clear unsaved forms on Input, Output, and Waste tabs. Mass balance must be valid.
                    </p>
                    {!committedMassBalance.isValid && committedMassBalance.errorMessage && (
                      <Banner tone="warning" className="mt-3">
                        {committedMassBalance.errorMessage}
                      </Banner>
                    )}
                  </div>
                  <Button
                    type="button"
                    loading={saving}
                    disabled={!canComplete}
                    onClick={startCompleteProcess}
                    leftIcon={<CheckCircle2 className="h-4 w-4" />}
                  >
                    Complete process
                  </Button>
                </CardBody>
              </Card>
            )}
          </div>
        </Tab>

        <Tab id="batches" label="Batch history" badge={allBatches.length > 0 ? allBatches.length : undefined}>
          <Card>
            <CardHeader
              title="Batch history"
              subtitle="Each submit creates one batch. Select a batch to view details or void — reverses input, output, balance return, and waste together."
            />
            <CardBody>
              <ProcessingBatchHistory
                batches={allBatches}
                customerNames={customerNameMap}
                onVoidBatch={canVoid ? setVoidBatchTarget : undefined}
              />
            </CardBody>
          </Card>
        </Tab>
            </Tabs>

            {summary ? (
              <SummarySidebar
                layout="mobile"
                summary={summary}
                massBalance={committedMassBalance}
                batches={activeProcessingBatches(allBatches)}
              />
            ) : null}
          </div>

          {summary ? <div className="hidden min-h-px min-w-0 lg:col-start-4 lg:block" aria-hidden="true" /> : null}
        </div>

        {summary && fixedSnapshotBox ? (
          <div
            className="pointer-events-none fixed z-30 hidden lg:block"
            style={{
              top: "5rem",
              bottom: "1.5rem",
              left: fixedSnapshotBox.left,
              width: fixedSnapshotBox.width,
            }}
          >
            <div className="pointer-events-auto h-full overflow-y-auto overscroll-contain pr-0.5">
              <SummarySidebar
                layout="desktop"
                summary={summary}
                massBalance={committedMassBalance}
                batches={activeProcessingBatches(allBatches)}
              />
            </div>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={inputMixConfirmOpen}
        onClose={() => setInputMixConfirmOpen(false)}
        onConfirm={async () => {
          setInputMixConfirmOpen(false);
          await submitInputBatchConfirmed();
        }}
        title="Lock output ownership?"
        description={`All outputs will post to ${ownerKeyLabel(singleAllocationOwnerKey, customerLabels)}. You may add more input from this same owner only.`}
        confirmLabel="Continue"
      />

      <ConfirmDialog
        open={completeFlowConfirmOpen}
        onClose={() => setCompleteFlowConfirmOpen(false)}
        onConfirm={() => {
          setCompleteFlowConfirmOpen(false);
          continueCompleteProcess();
        }}
        title="Complete without finished output?"
        description="Fresh input has been recorded but no finished output yet. Complete this job anyway?"
        confirmLabel="Complete anyway"
      />

      <ConfirmDialog
        open={completeBalanceConfirmOpen}
        onClose={() => setCompleteBalanceConfirmOpen(false)}
        onConfirm={() => {
          setCompleteBalanceConfirmOpen(false);
          setError("");
          setSuccess("");
          setCompleteAuthError("");
          setCompleteAuthOpen(true);
        }}
        title="Complete with high balance return?"
        description={
          summary
            ? `${formatQtyKg(Number(summary.net_balance_kg ?? 0))} balance return remains vs ${formatQtyKg(Number(summary.total_fresh_input_kg ?? 0))} fresh input. Complete anyway?`
            : "Balance return remains. Complete anyway?"
        }
        confirmLabel="Complete anyway"
      />

      <VoidConfirmDialog
        open={completeAuthOpen}
        onClose={() => {
          if (saving) return;
          setCompleteAuthError("");
          setCompleteAuthOpen(false);
        }}
        onConfirm={confirmCompleteProcess}
        title="Complete this processing job?"
        description="This locks the job — no further batches can be added. Authorization is required."
        confirmLabel="Complete process"
        cancelLabel="Cancel"
        authError={completeAuthError || undefined}
      />

      <VoidConfirmDialog
        open={voidBatchTarget != null}
        onClose={() => {
          if (saving) return;
          setVoidBatchAuthError("");
          setVoidBatchTarget(null);
        }}
        onConfirm={confirmVoidBatch}
        title={
          voidBatchTarget
            ? `Void batch #${batchNumberFor(voidBatchTarget, allBatches)}?`
            : "Void batch?"
        }
        description="Reverse this entire batch (input, output, balance return, and waste). Stock is restored or removed accordingly. Completed jobs reopen for further batches."
        confirmLabel="Void batch"
        cancelLabel="Cancel"
        authError={voidBatchAuthError || undefined}
      />
    </>
  );
}

function MetricTile({
  label,
  value,
  entryCount,
  tone = "neutral",
  highlight,
  compact,
}: {
  label: string;
  value: string;
  /** Number of lines/batches that contributed to this metric — shown in brackets. */
  entryCount?: number;
  tone?: "neutral" | "primary" | "success" | "warning" | "muted";
  highlight?: boolean;
  compact?: boolean;
}) {
  const toneClass = {
    neutral: "border-line/80 bg-surface/80",
    primary: "border-primary-200/70 bg-primary-50/60 dark:border-primary-800/40 dark:bg-primary-950/30",
    success: "border-accent-200/70 bg-accent-50/60 dark:border-accent-800/40 dark:bg-accent-950/30",
    warning: "border-warning-200/70 bg-warning-50/60 dark:border-warning-800/40 dark:bg-warning-950/30",
    muted: "border-line/60 bg-surface-subtle/60",
  }[tone];

  return (
    <div
      className={cn(
        "border shadow-sm backdrop-blur-[2px]",
        compact ? "rounded-xl p-3" : "rounded-2xl p-4",
        toneClass,
        highlight && "ring-2 ring-primary-400/40 dark:ring-primary-500/30"
      )}
    >
      <p className={cn("font-semibold uppercase tracking-wide text-ink-muted", compact ? "text-[10px]" : "text-xs")}>
        {label}
      </p>
      <p
        className={cn(
          "v2-mono font-bold text-ink",
          compact ? "mt-1 text-lg" : "mt-2 text-xl",
          highlight && "text-primary-800 dark:text-primary-200"
        )}
      >
        {value}
        {entryCount != null && entryCount > 0 ? (
          <span className={cn("ml-1.5 font-semibold text-ink-muted", compact ? "text-sm" : "text-base")}>
            ({entryCount})
          </span>
        ) : null}
      </p>
    </div>
  );
}

function MassBalancePanel({
  balance,
  includesPending = false,
}: {
  balance: ReturnType<typeof computeMassBalance>;
  includesPending?: boolean;
}) {
  const basisKg = balance.massBalanceInputKg;
  const usedPct =
    basisKg > 0 ? Math.min(100, (balance.totalOutflowKg / basisKg) * 100) : 0;
  const warn = balance.allowanceRemainingKg < 0;

  return (
    <div
      className={cn(
        "rounded-2xl border p-4",
        warn
          ? "border-warning-300/70 bg-warning-50/40 dark:border-warning-700/50 dark:bg-warning-950/20"
          : "border-primary-200/60 bg-gradient-to-br from-primary-50/50 via-surface to-violet-50/30 dark:border-primary-800/40 dark:from-primary-950/25 dark:via-surface dark:to-violet-950/15"
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Scale className="h-5 w-5 text-primary-600 dark:text-primary-300" aria-hidden="true" />
        <h4 className="text-base font-semibold text-ink">Mass balance check</h4>
        <span
          className={cn(
            "ml-auto v2-mono text-sm font-semibold",
            warn ? "text-warning-800 dark:text-warning-200" : "text-accent-800 dark:text-accent-300"
          )}
        >
          Allowance remaining: {formatQtyKg(balance.allowanceRemainingKg)}
        </span>
      </div>
      {balance.errorMessage ? (
        <Banner tone="warning" className="mt-3">
          {balance.errorMessage}
        </Banner>
      ) : (
        <p className="mt-2 text-sm text-ink-muted">
          {includesPending
            ? "Includes unsaved entries in the open form. Allowance = fresh + reprocess + 100 − outflow (same in-side as misc)."
            : "Committed batches only. Allowance = fresh + reprocess + 100 − outflow (same in-side as misc)."}
        </p>
      )}
      {basisKg > 0 && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-sm text-ink-muted">
            <span>
              {includesPending
                ? "Outflow vs fresh + reprocess (with this form)"
                : "Outflow vs fresh + reprocess"}
            </span>
            <span className="v2-mono">{usedPct.toFixed(2)}%</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-surface-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                warn ? "bg-warning-500" : "bg-gradient-to-r from-primary-500 to-violet-500"
              )}
              style={{ width: `${usedPct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-ink-subtle">
            Basis {formatQtyKg(basisKg)}
            {balance.reprocessInputKg > 0
              ? ` (fresh ${formatQtyKg(balance.freshInputKg)} + reprocess ${formatQtyKg(balance.reprocessInputKg)})`
              : ""}
            {" · "}
            100 kg tolerance on submit.
          </p>
        </div>
      )}
    </div>
  );
}

function SummaryMetricRow({
  label,
  value,
  entryCount,
  tone = "neutral",
}: {
  label: string;
  value: string;
  entryCount?: number;
  tone?: "neutral" | "primary" | "success" | "warning" | "muted";
}) {
  const toneClass = {
    neutral: "border-line/70 bg-surface/70",
    primary: "border-primary-200/60 bg-primary-50/50 dark:border-primary-800/35 dark:bg-primary-950/25",
    success: "border-accent-200/60 bg-accent-50/50 dark:border-accent-800/35 dark:bg-accent-950/25",
    warning: "border-warning-200/60 bg-warning-50/50 dark:border-warning-800/35 dark:bg-warning-950/25",
    muted: "border-line/50 bg-surface-subtle/50",
  }[tone];

  return (
    <div className={cn("flex flex-col gap-1 rounded-xl border px-3 py-2.5", toneClass)}>
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</span>
      <span className="v2-mono break-words text-base font-bold leading-snug text-ink">
        {value}
        {entryCount != null && entryCount > 0 ? (
          <span className="ml-1.5 text-sm font-semibold text-ink-muted">({entryCount})</span>
        ) : null}
      </span>
    </div>
  );
}

type SnapshotRecentItem = {
  key: string;
  primary: string;
  secondary?: string;
};

/** Compact hover panel — last entries for reference (view only). */
function SnapshotRecentHover({
  title,
  items,
  children,
  className,
}: {
  title: string;
  items: SnapshotRecentItem[];
  children: ReactNode;
  className?: string;
}) {
  const anchorRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const closeTimer = useRef<number | null>(null);

  const clearClose = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const placePanel = () => {
    const el = anchorRef.current;
    if (!el || items.length === 0) return;
    const r = el.getBoundingClientRect();
    const panelW = 260;
    const gap = 10;
    const placeLeft = r.left >= panelW + gap + 12;
    const left = placeLeft
      ? r.left - panelW - gap
      : Math.min(r.right + gap, window.innerWidth - panelW - 12);
    const estimatedH = 36 + items.length * 44;
    const top = Math.min(Math.max(12, r.top), window.innerHeight - estimatedH - 12);
    setPos({ top, left: Math.max(12, left) });
  };

  const show = () => {
    clearClose();
    if (items.length === 0) return;
    placePanel();
    setOpen(true);
  };

  const hide = () => {
    clearClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 80);
  };

  useEffect(() => () => clearClose(), []);

  if (items.length === 0) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      ref={anchorRef}
      className={cn("relative", className)}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      {children}
      {open &&
        createPortal(
          <div
            role="tooltip"
            className="pointer-events-none fixed z-[80] w-[260px] overflow-hidden rounded-lg border border-line/60 bg-surface/95 shadow-[0_8px_30px_rgb(var(--shadow-color)/0.18)] ring-1 ring-black/5 backdrop-blur-md dark:ring-white/10"
            style={{ top: pos.top, left: pos.left }}
          >
            <div className="border-b border-line/50 bg-surface-muted/50 px-3 py-1.5">
              <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                {title}
              </p>
            </div>
            <ul className="divide-y divide-line/40 py-0.5">
              {items.map((item) => (
                <li key={item.key} className="px-3 py-1.5">
                  <p className="v2-mono text-[12px] font-semibold leading-snug text-ink">{item.primary}</p>
                  {item.secondary ? (
                    <p className="mt-0.5 truncate text-[11px] leading-snug text-ink-muted">{item.secondary}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>,
          document.body
        )}
    </div>
  );
}

function formatBrandEntryPrimary(entry: RecentBrandOutputEntry): string {
  if (entry.bagCount > 0) {
    return `${entry.bagCount} bag${entry.bagCount === 1 ? "" : "s"} · ${formatQtyKg(entry.quantityKg)}`;
  }
  return formatQtyKg(entry.quantityKg);
}

function formatBrandEntrySecondary(entry: RecentBrandOutputEntry): string {
  const parts = [
    entry.locationName ?? `Loc #${entry.locationId}`,
    entry.bagTypeName ?? `Bag #${entry.bagTypeId}`,
  ];
  if (Number(entry.looseKg) > 0 && entry.bagCount > 0) {
    parts.push(`${formatQtyKg(entry.looseKg)} loose`);
  }
  parts.push(formatDateTime(entry.operationAt));
  return parts.join(" · ");
}

function formatWasteEntryPrimary(entry: RecentWasteEntry): string {
  return formatQtyKg(entry.totalKg);
}

function formatWasteEntrySecondary(entry: RecentWasteEntry): string {
  const parts: string[] = [];
  if (Number(entry.dustKg) > 0) parts.push(`Dust ${formatQtyKg(entry.dustKg)}`);
  if (Number(entry.stoneKg) > 0) parts.push(`Stone ${formatQtyKg(entry.stoneKg)}`);
  if (Number(entry.sackKg) > 0) parts.push(`Sack ${formatQtyKg(entry.sackKg)}`);
  parts.push(formatDateTime(entry.operationAt));
  return parts.join(" · ");
}

function formatBalanceReturnPrimary(entry: RecentBalanceReturnEntry): string {
  if (entry.bagCount > 0) {
    return `${entry.bagCount} bag${entry.bagCount === 1 ? "" : "s"} · ${formatQtyKg(entry.quantityKg)}`;
  }
  return formatQtyKg(entry.quantityKg);
}

function formatBalanceReturnSecondary(entry: RecentBalanceReturnEntry): string {
  const parts = [
    entry.locationName ?? "Location",
    entry.bagTypeName ?? "Bag type",
  ];
  if (Number(entry.looseKg) > 0 && entry.bagCount > 0) {
    parts.push(`${formatQtyKg(entry.looseKg)} loose`);
  }
  parts.push(formatDateTime(entry.operationAt));
  return parts.join(" · ");
}

function SummarySidebarBody({
  summary,
  batches,
}: {
  summary: ProcessingJobSummary;
  batches: ProcessingBatch[];
}) {
  const counts = computeProcessingEntryCounts(batches);
  const outputLinesByBrand = computeOutputLineCountsByBrand(batches);
  const wasteKg = Number(summary.total_waste_kg ?? 0);
  const powderKg = totalPowderKgFromBatches(batches);
  const wasteDisplayKg = powderKg > 0 ? Math.max(wasteKg - powderKg, 0) : wasteKg;
  const miscKg = Number(summary.total_misc_kg ?? 0);
  const lossKg = Number(summary.total_loss_kg ?? 0);
  const recentWaste = lastWasteEntries(batches, 5);
  const recentMisc = lastMiscEntries(batches, 5);
  const recentPowder = lastPowderEntries(batches, 5);
  const recentBalanceReturns = lastBalanceReturnEntries(batches, 5);
  const latestBalanceReturn = recentBalanceReturns[0] ?? null;

  const freshValue =
    summary.fresh_input_bags && summary.fresh_input_bags > 0
      ? `${summary.fresh_input_bags} bags · ${formatQtyKg(summary.total_fresh_input_kg)}`
      : formatQtyKg(summary.total_fresh_input_kg);

  return (
    <div className="space-y-2.5">
      <SummaryMetricRow label="Fresh in" value={freshValue} entryCount={counts.freshInputLines} tone="primary" />
      <SnapshotRecentHover
        title="Balance return"
        items={recentBalanceReturns.map((entry) => ({
          key: entry.key,
          primary: formatBalanceReturnPrimary(entry),
          secondary: formatBalanceReturnSecondary(entry),
        }))}
      >
        <SummaryMetricRow
          label="Balance return"
          value={formatQtyKg(latestBalanceReturn?.quantityKg ?? 0)}
          entryCount={counts.balanceReturnLines}
          tone={latestBalanceReturn ? "warning" : "neutral"}
        />
      </SnapshotRecentHover>

      <div className="border-t border-line/50 pt-3">
        <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">Output by brand</p>
        {summary.output_by_brand.length > 0 ? (
          <div className="space-y-2">
            {summary.output_by_brand.map((row) => {
              const lineCount = outputLinesByBrand.get(row.brand_id) ?? 0;
              const recent = lastBrandOutputEntries(batches, row.brand_id, 5);
              return (
                <SnapshotRecentHover
                  key={row.brand_id}
                  title={row.brand_name ?? `Brand #${row.brand_id}`}
                  items={recent.map((entry) => ({
                    key: entry.key,
                    primary: formatBrandEntryPrimary(entry),
                    secondary: formatBrandEntrySecondary(entry),
                  }))}
                >
                  <div className="rounded-xl border border-accent-200/50 bg-accent-50/40 px-3 py-2.5 transition hover:border-accent-300/80 dark:border-accent-800/35 dark:bg-accent-950/20 dark:hover:border-accent-700/50">
                    <p className="text-sm font-semibold text-ink">{row.brand_name ?? `Brand #${row.brand_id}`}</p>
                    <p className="v2-mono text-base font-bold text-accent-800 dark:text-accent-300">
                      {formatQtyKg(row.quantity_kg)}
                      {lineCount > 0 ? (
                        <span className="ml-1.5 text-sm font-semibold text-ink-muted">({lineCount})</span>
                      ) : null}
                    </p>
                  </div>
                </SnapshotRecentHover>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No finished output yet.</p>
        )}
      </div>

      <div className="space-y-2.5 border-t border-line/50 pt-3">
        {powderKg > 0 && (
          <SnapshotRecentHover
            title="Powder stock"
            items={recentPowder.map((entry) => ({
              key: entry.key,
              primary: formatQtyKg(entry.powderKg),
              secondary: formatDateTime(entry.operationAt),
            }))}
          >
            <SummaryMetricRow
              label="Powder stock"
              value={formatQtyKg(powderKg)}
              entryCount={counts.powderBatches}
              tone="success"
            />
          </SnapshotRecentHover>
        )}
        <SnapshotRecentHover
          title="Waste"
          items={recentWaste.map((entry) => ({
            key: entry.key,
            primary: formatWasteEntryPrimary(entry),
            secondary: formatWasteEntrySecondary(entry),
          }))}
        >
          <SummaryMetricRow
            label={powderKg > 0 ? "Waste (excl. powder)" : "Waste"}
            value={formatQtyKg(wasteDisplayKg)}
            entryCount={counts.wasteBatches}
            tone="warning"
          />
        </SnapshotRecentHover>
        <SnapshotRecentHover
          title="Misc"
          items={recentMisc.map((entry: RecentMiscEntry) => ({
            key: entry.key,
            primary: formatQtyKg(entry.miscKg),
            secondary: formatDateTime(entry.operationAt),
          }))}
        >
          <SummaryMetricRow label="Misc" value={formatQtyKg(miscKg)} tone="muted" />
        </SnapshotRecentHover>
        <SummaryMetricRow label="Total loss" value={formatQtyKg(lossKg)} tone="warning" />
      </div>
    </div>
  );
}

function SummarySidebar({
  summary,
  massBalance,
  batches,
  layout = "both",
}: {
  summary: ProcessingJobSummary;
  massBalance: ReturnType<typeof computeMassBalance>;
  batches: ProcessingBatch[];
  layout?: "mobile" | "desktop" | "both";
}) {
  const warn = massBalance.allowanceRemainingKg < 0;
  const powderKg = totalPowderKgFromBatches(batches);

  const shellClass = cn(
    "relative overflow-hidden rounded-2xl border v2-glass shadow-soft",
    warn
      ? "border-warning-300/60 bg-gradient-to-b from-warning-50/45 via-surface/95 to-surface dark:border-warning-700/50 dark:from-warning-950/25 dark:via-surface/95 dark:to-surface"
      : "border-primary-200/60 bg-gradient-to-b from-primary-50/40 via-surface/95 to-violet-50/30 dark:border-primary-800/40 dark:from-primary-950/20 dark:via-surface/95 dark:to-violet-950/15"
  );

  const header = (
    <div className="flex items-start justify-between gap-2 border-b border-line/50 px-4 py-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-md">
          <Layers className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-base font-semibold text-ink">Job snapshot</p>
          <p className="text-sm text-ink-muted">Fixed on the right while you scroll</p>
        </div>
      </div>
      {warn ? (
        <Badge tone="warning" size="sm">
          Over allowance
        </Badge>
      ) : powderKg > 0 ? (
        <Badge tone="success" size="sm">
          Powder
        </Badge>
      ) : null}
    </div>
  );

  const body = <SummarySidebarBody summary={summary} batches={batches} />;

  return (
    <>
      {(layout === "mobile" || layout === "both") && (
      <details className={cn("group lg:hidden", shellClass)}>
        <summary className="cursor-pointer list-none px-4 py-3 marker:content-none [&::-webkit-details-marker]:hidden">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-md">
                <Layers className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="text-base font-semibold text-ink">Job snapshot</span>
            </div>
            <span className="text-sm text-ink-muted group-open:hidden">Tap to expand</span>
            <span className="hidden text-sm text-ink-muted group-open:inline">Tap to collapse</span>
          </div>
        </summary>
        <div className="border-t border-line/50 px-4 py-4">{body}</div>
      </details>
      )}

      {(layout === "desktop" || layout === "both") && (
      <aside className={layout === "both" ? "hidden lg:block" : undefined}>
        <div className={shellClass}>
          {header}
          <div className="px-4 py-4">{body}</div>
        </div>
      </aside>
      )}
    </>
  );
}

function wasteAllocationLabel(wa: ProcessingWasteAllocation, customers: Map<number, string>): string {
  if (wa.owner_type === "owned") return "Owned";
  const name = wa.customer_id != null ? customers.get(wa.customer_id) : null;
  return name ? `Job work · ${name}` : "Job work";
}

function aggregateWasteAllocations(batches: ProcessingBatch[]): ProcessingWasteAllocation[] {
  const map = new Map<string, ProcessingWasteAllocation>();
  for (const batch of batches) {
    if (batch.voided_at) continue;
    for (const wa of batch.waste_allocations ?? []) {
      const key = `${wa.owner_type}:${wa.customer_id ?? ""}`;
      const prev = map.get(key);
      if (!prev) {
        map.set(key, { ...wa });
      } else {
        map.set(key, {
          ...prev,
          dust_kg: String(Number(prev.dust_kg) + Number(wa.dust_kg)),
          stone_kg: String(Number(prev.stone_kg) + Number(wa.stone_kg)),
          sack_weight_waste_kg: String(Number(prev.sack_weight_waste_kg) + Number(wa.sack_weight_waste_kg)),
          powder_kg: String(Number(prev.powder_kg ?? 0) + Number(wa.powder_kg ?? 0)),
          miscellaneous_waste_kg: String(Number(prev.miscellaneous_waste_kg) + Number(wa.miscellaneous_waste_kg)),
        });
      }
    }
  }
  return [...map.values()];
}

const WASTE_AUDIT_CATEGORY_LABELS: { key: keyof ProcessingWasteAllocation; label: string }[] = [
  { key: "dust_kg", label: "Dust" },
  { key: "stone_kg", label: "Stone" },
  { key: "sack_weight_waste_kg", label: "Sack weight" },
  { key: "miscellaneous_waste_kg", label: "Misc" },
];

function wasteAuditCategories(wa: ProcessingWasteAllocation): { label: string; kg: number }[] {
  return WASTE_AUDIT_CATEGORY_LABELS.map(({ key, label }) => ({
    label,
    kg: Number(wa[key] ?? 0),
  })).filter((row) => row.kg > 0);
}

function SummaryCard({
  batches,
  allocationHint,
  inputRulesHint,
  customerNames,
}: {
  summary: ProcessingJobSummary;
  batches: ProcessingBatch[];
  allocationHint?: string | null;
  inputRulesHint?: string | null;
  customerNames: Map<number, string>;
}) {
  const wasteSplits = aggregateWasteAllocations(batches);
  const auditWasteSplits = wasteSplits
    .map((wa) => ({ wa, categories: wasteAuditCategories(wa) }))
    .filter((row) => row.categories.length > 0);

  return (
    <Card className="overflow-hidden border-primary-200/60 bg-gradient-to-br from-primary-50/35 via-surface to-violet-50/25 dark:border-primary-800/40 dark:from-primary-950/20">
      <CardHeader
        title="Waste allocation"
        subtitle="Owner split for dust, stone, sack, and misc — totals are in the snapshot panel on the right."
      />
      <CardBody className="space-y-5">
        {allocationHint ? (
          <Banner tone="info">{allocationHint}</Banner>
        ) : null}
        {inputRulesHint && inputRulesHint !== allocationHint ? (
          <Banner tone="info">{inputRulesHint}</Banner>
        ) : null}

        {auditWasteSplits.length > 0 ? (
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">Waste split by owner</p>
            <div className="space-y-2">
              {auditWasteSplits.map(({ wa, categories }) => {
                const total = categories.reduce((sum, row) => sum + row.kg, 0);
                return (
                  <div
                    key={`${wa.owner_type}-${wa.customer_id ?? ""}`}
                    className="rounded-xl border border-warning-200/60 bg-warning-50/30 px-3 py-2.5 dark:border-warning-800/40 dark:bg-warning-950/20"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium text-ink">{wasteAllocationLabel(wa, customerNames)}</span>
                      <span className="v2-mono text-sm font-semibold text-warning-800 dark:text-warning-200">
                        {formatQtyKg(total)}
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                      {categories.map((row) => (
                        <span key={row.label} className="text-sm text-ink-muted">
                          {row.label}
                          {": "}
                          <span className="v2-mono font-medium text-ink">{formatQtyKg(row.kg)}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No owner-level waste split recorded yet.</p>
        )}
      </CardBody>
    </Card>
  );
}

function cellOrDash(value: string | number | null | undefined, mono = false) {
  if (value == null || value === "" || value === 0 || value === "0" || value === "0.000") {
    return <span className="text-sm text-ink-subtle">—</span>;
  }
  return (
    <span className={cn("text-sm text-ink", mono && "v2-mono")}>{typeof value === "number" ? value : value}</span>
  );
}

type InputLogRow = {
  id: string;
  at: string;
  sortAt: number;
  source: string;
  owner: string;
  locationName: string;
  bagTypeName: string;
  bagCount: number;
  looseKg: string;
  quantityKg: string;
};

type OutputLogRow = {
  id: string;
  at: string;
  sortAt: number;
  entryKind: "Output" | "Balance return";
  owner: string;
  brandName: string;
  locationName: string;
  bagTypeName: string;
  bagCount: number;
  looseKg: string;
  quantityKg: string;
};

type WasteLogRow = {
  id: string;
  at: string;
  sortAt: number;
  category: string;
  quantityKg: string;
};

type ProcessingLogGroups = {
  input: InputLogRow[];
  output: OutputLogRow[];
  waste: WasteLogRow[];
};

function lineOwnerLabel(
  ownerType: string | undefined,
  customerId: number | null | undefined,
  customers: Map<number, string>
): string {
  if (ownerType === "job_work") {
    const name = customerId != null ? customers.get(customerId) : null;
    return name ? `Job work · ${name}` : "Job work";
  }
  return "Owned";
}

function batchNumberFor(batch: ProcessingBatch, allBatches: ProcessingBatch[]): number {
  const sorted = [...allBatches].sort(
    (a, b) => new Date(a.operation_at).getTime() - new Date(b.operation_at).getTime() || a.id - b.id
  );
  return sorted.findIndex((b) => b.id === batch.id) + 1;
}

function summarizeBatch(batch: ProcessingBatch): {
  inputKg: number;
  freshInputKg: number;
  reprocessKg: number;
  outputKg: number;
  wasteKg: number;
  parts: string[];
} {
  let freshInputKg = 0;
  let reprocessKg = 0;
  for (const ln of batch.input_lines) {
    const qty = Number(ln.quantity_kg);
    if ((ln.input_source ?? "fresh") === "balance_reprocess") reprocessKg += qty;
    else freshInputKg += qty;
  }
  const inputKg = freshInputKg; // primary "input" = fresh from stock only (matches snapshot)
  const outputKg =
    batch.output_lines.reduce((sum, ln) => sum + Number(ln.quantity_kg), 0) +
    (batch.balance_return_lines ?? []).reduce((sum, ln) => sum + Number(ln.quantity_kg), 0);
  const wasteKg =
    Number(batch.dust_kg) +
    Number(batch.stone_kg) +
    Number(batch.sack_weight_waste_kg) +
    Number(batch.powder_kg ?? 0) +
    Number(batch.miscellaneous_waste_kg);
  const parts: string[] = [];
  if (freshInputKg > 0) parts.push(`Fresh ${formatQtyKg(freshInputKg)}`);
  if (reprocessKg > 0) parts.push(`Reprocess ${formatQtyKg(reprocessKg)}`);
  if (outputKg > 0) parts.push(`Output ${formatQtyKg(outputKg)}`);
  if (wasteKg > 0) parts.push(`Waste ${formatQtyKg(wasteKg)}`);
  return { inputKg, freshInputKg, reprocessKg, outputKg, wasteKg, parts };
}

function buildProcessingLogGroups(
  batches: ProcessingBatch[],
  customers: Map<number, string>
): ProcessingLogGroups {
  const input: InputLogRow[] = [];
  const output: OutputLogRow[] = [];
  const waste: WasteLogRow[] = [];

  for (const batch of batches) {
    if (batch.voided_at) continue;
    const at = batch.operation_at;
    const sortAt = new Date(at).getTime();

    for (const ln of batch.input_lines) {
      const reprocess = (ln.input_source ?? "fresh") === "balance_reprocess";
      input.push({
        id: `input-${batch.id}-${ln.id}`,
        at,
        sortAt,
        source: reprocess ? "Reprocess" : "Fresh",
        owner: ln.owner_type === "job_work" ? "Job work" : "Owned",
        locationName: ln.location_name ?? `Location #${ln.location_id}`,
        bagTypeName: ln.bag_type_name ?? `Bag #${ln.bag_type_id}`,
        bagCount: ln.bag_count,
        looseKg: ln.loose_kg,
        quantityKg: ln.quantity_kg,
      });
    }

    for (const ln of batch.output_lines) {
      output.push({
        id: `output-${batch.id}-${ln.id}`,
        at,
        sortAt,
        entryKind: "Output",
        owner: lineOwnerLabel(ln.owner_type, ln.customer_id, customers),
        brandName: ln.brand_name ?? `Brand #${ln.brand_id}`,
        locationName: ln.location_name ?? `Location #${ln.location_id}`,
        bagTypeName: ln.bag_type_name ?? `Bag #${ln.bag_type_id}`,
        bagCount: ln.bag_count,
        looseKg: ln.loose_kg,
        quantityKg: ln.quantity_kg,
      });
    }

    for (const ln of batch.balance_return_lines ?? []) {
      output.push({
        id: `return-${batch.id}-${ln.id}`,
        at,
        sortAt,
        entryKind: "Balance return",
        owner: lineOwnerLabel(ln.owner_type, ln.customer_id, customers),
        brandName: "—",
        locationName: ln.location_name ?? `Location #${ln.location_id}`,
        bagTypeName: ln.bag_type_name ?? `Bag #${ln.bag_type_id}`,
        bagCount: ln.bag_count,
        looseKg: ln.loose_kg,
        quantityKg: ln.quantity_kg,
      });
    }

    const wasteParts: [string, string][] = [
      ["Dust", batch.dust_kg],
      ["Stone", batch.stone_kg],
      ["Sack weight", batch.sack_weight_waste_kg],
      [
        batch.powder_location_name
          ? `Powder stock @ ${batch.powder_location_name}`
          : "Powder stock",
        batch.powder_kg ?? "0",
      ],
      ["Misc", batch.miscellaneous_waste_kg],
    ];
    for (const [category, kg] of wasteParts) {
      if (Number(kg) <= 0) continue;
      waste.push({
        id: `waste-${batch.id}-${category}`,
        at,
        sortAt,
        category,
        quantityKg: kg,
      });
    }
  }

  const byNewest = <T extends { sortAt: number }>(rows: T[]) =>
    [...rows].sort((a, b) => b.sortAt - a.sortAt);

  return {
    input: byNewest(input),
    output: byNewest(output),
    waste: byNewest(waste),
  };
}

function groupTotalKg<T extends { quantityKg: string }>(rows: T[]): number {
  return rows.reduce((sum, row) => sum + Number(row.quantityKg), 0);
}

function logDayKey(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at.slice(0, 10) || "unknown";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatLogTime(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
}

/** Newest date first; rows within a day keep newest-first order. */
function groupLogRowsByDate<T extends { at: string; sortAt: number }>(
  rows: T[]
): { dayKey: string; label: string; rows: T[]; totalKg: number }[] {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const key = logDayKey(row.at);
    const list = map.get(key);
    if (list) list.push(row);
    else map.set(key, [row]);
  }
  return [...map.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([dayKey, dayRows]) => ({
      dayKey,
      label: formatDate(dayRows[0]?.at),
      rows: dayRows,
      totalKg: groupTotalKg(dayRows),
    }));
}

function LogSection({
  title,
  titleTone,
  totalKg,
  secondaryLabel,
  children,
  emptyLabel,
}: {
  title: string;
  titleTone: string;
  totalKg: number;
  /** Optional muted line (e.g. reprocess) — never mixed into totalKg. */
  secondaryLabel?: string | null;
  children: ReactNode;
  emptyLabel: string;
}) {
  return (
    <section className="rounded-2xl border border-line/80 bg-surface/50">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 px-4 py-3 sm:px-5">
        <h4 className={cn("text-base font-semibold", titleTone)}>{title}</h4>
        <div className="text-right">
          <span className="v2-mono text-sm font-semibold text-ink">
            {totalKg > 0 ? formatQtyKg(totalKg) : emptyLabel}
          </span>
          {secondaryLabel ? (
            <p className="mt-0.5 text-xs font-medium text-ink-muted">{secondaryLabel}</p>
          ) : null}
        </div>
      </div>
      <div className="space-y-3 p-2 sm:p-3">{children}</div>
    </section>
  );
}

function LogDateGroup({
  label,
  totalKg,
  children,
}: {
  label: string;
  totalKg: number;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line/60 bg-surface/80">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/50 bg-surface-muted/40 px-3 py-2">
        <p className="text-sm font-semibold text-ink">{label}</p>
        <span className="v2-mono text-xs font-semibold text-ink-muted">{formatQtyKg(totalKg)}</span>
      </div>
      <div className="p-1">{children}</div>
    </div>
  );
}

const INPUT_COLUMNS: Column<InputLogRow>[] = [
  {
    key: "source",
    header: "Source",
    cell: (r) => (
      <span
        className={cn(
          "text-sm font-medium",
          r.source === "Reprocess" ? "text-ink-muted" : "text-primary-700 dark:text-primary-300"
        )}
      >
        {r.source}
      </span>
    ),
  },
  {
    key: "owner",
    header: "Owner",
    cell: (r) => cellOrDash(r.owner),
  },
  { key: "location", header: "Location", cell: (r) => cellOrDash(r.locationName) },
  { key: "bagType", header: "Bag type", cell: (r) => cellOrDash(r.bagTypeName) },
  { key: "bags", header: "Bags", numeric: true, cell: (r) => cellOrDash(r.bagCount, true) },
  {
    key: "loose",
    header: "Loose (kg)",
    numeric: true,
    cell: (r) =>
      Number(r.looseKg) > 0 ? (
        <span className="v2-mono text-sm text-ink">{formatQtyKg(r.looseKg)}</span>
      ) : (
        <span className="text-sm text-ink-subtle">—</span>
      ),
  },
  {
    key: "total",
    header: "Total (kg)",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm font-semibold text-ink">{formatQtyKg(r.quantityKg)}</span>,
  },
  {
    key: "at",
    header: "Time",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm text-ink-muted">{formatLogTime(r.at)}</span>,
  },
];

const OUTPUT_COLUMNS: Column<OutputLogRow>[] = [
  { key: "kind", header: "Kind", cell: (r) => (
      <span
        className={cn(
          "text-sm font-medium",
          r.entryKind === "Output"
            ? "text-accent-800 dark:text-accent-300"
            : "text-warning-800 dark:text-warning-300"
        )}
      >
        {r.entryKind}
      </span>
    ),
  },
  { key: "owner", header: "Owner", cell: (r) => cellOrDash(r.owner) },
  { key: "brand", header: "Brand", cell: (r) => cellOrDash(r.brandName === "—" ? null : r.brandName) },
  { key: "location", header: "Location", cell: (r) => cellOrDash(r.locationName) },
  { key: "bagType", header: "Bag type", cell: (r) => cellOrDash(r.bagTypeName) },
  { key: "bags", header: "Bags", numeric: true, cell: (r) => cellOrDash(r.bagCount, true) },
  {
    key: "loose",
    header: "Loose (kg)",
    numeric: true,
    cell: (r) =>
      Number(r.looseKg) > 0 ? (
        <span className="v2-mono text-sm text-ink">{formatQtyKg(r.looseKg)}</span>
      ) : (
        <span className="text-sm text-ink-subtle">—</span>
      ),
  },
  {
    key: "total",
    header: "Total (kg)",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm font-semibold text-ink">{formatQtyKg(r.quantityKg)}</span>,
  },
  {
    key: "at",
    header: "Time",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm text-ink-muted">{formatLogTime(r.at)}</span>,
  },
];

const WASTE_COLUMNS: Column<WasteLogRow>[] = [
  {
    key: "category",
    header: "Category",
    cell: (r) => <span className="text-sm font-medium text-warning-700 dark:text-warning-300">{r.category}</span>,
  },
  {
    key: "total",
    header: "Quantity (kg)",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm font-semibold text-ink">{formatQtyKg(r.quantityKg)}</span>,
  },
  {
    key: "at",
    header: "Time",
    numeric: true,
    cell: (r) => <span className="v2-mono text-sm text-ink-muted">{formatLogTime(r.at)}</span>,
  },
];

function useProcessingLogGroups(batches: ProcessingBatch[], customerNames: Map<number, string>) {
  return useMemo(() => buildProcessingLogGroups(batches, customerNames), [batches, customerNames]);
}

function ProcessingActivityLog({
  batches,
  customerNames,
}: {
  batches: ProcessingBatch[];
  customerNames: Map<number, string>;
}) {
  return (
    <div className="space-y-4">
      <ProcessingInputLog batches={batches} customerNames={customerNames} />
      <ProcessingOutputLog batches={batches} customerNames={customerNames} />
      <ProcessingWasteLog batches={batches} />
    </div>
  );
}

function ProcessingInputLog({
  batches,
  customerNames,
}: {
  batches: ProcessingBatch[];
  customerNames: Map<number, string>;
}) {
  const groups = useProcessingLogGroups(batches, customerNames);
  const freshRows = groups.input.filter((r) => r.source === "Fresh");
  const reprocessRows = groups.input.filter((r) => r.source === "Reprocess");
  // Match snapshot "Fresh in": total must be fresh-from-stock only — never add/subtract reprocess.
  const freshTotal = groupTotalKg(freshRows);
  const reprocessTotal = groupTotalKg(reprocessRows);
  const byDate = groupLogRowsByDate(groups.input);
  if (groups.input.length === 0) {
    return <p className="px-3 py-4 text-sm text-ink-muted">No input recorded yet.</p>;
  }
  return (
    <LogSection
      title="Input (fresh from stock)"
      titleTone="text-primary-700 dark:text-primary-300"
      totalKg={freshTotal}
      secondaryLabel={
        reprocessTotal > 0 ? `Reprocess (not in total): ${formatQtyKg(reprocessTotal)}` : null
      }
      emptyLabel="No fresh input"
    >
      {byDate.map((day) => (
        <LogDateGroup key={day.dayKey} label={day.label} totalKg={day.totalKg}>
          <Table
            columns={INPUT_COLUMNS}
            rows={day.rows}
            rowKey={(r) => r.id}
            caption={`Input log ${day.label}`}
            compact
            stickyHeader={false}
          />
        </LogDateGroup>
      ))}
    </LogSection>
  );
}

function ProcessingOutputLog({
  batches,
  customerNames,
}: {
  batches: ProcessingBatch[];
  customerNames: Map<number, string>;
}) {
  const groups = useProcessingLogGroups(batches, customerNames);
  const outputTotal = groupTotalKg(groups.output);
  const byDate = groupLogRowsByDate(groups.output);
  if (groups.output.length === 0) {
    return <p className="px-3 py-4 text-sm text-ink-muted">No output or balance return recorded yet.</p>;
  }
  return (
    <LogSection
      title="Output & balance return"
      titleTone="text-accent-800 dark:text-accent-300"
      totalKg={outputTotal}
      emptyLabel="No output"
    >
      {byDate.map((day) => (
        <LogDateGroup key={day.dayKey} label={day.label} totalKg={day.totalKg}>
          <Table
            columns={OUTPUT_COLUMNS}
            rows={day.rows}
            rowKey={(r) => r.id}
            caption={`Output log ${day.label}`}
            compact
            stickyHeader={false}
          />
        </LogDateGroup>
      ))}
    </LogSection>
  );
}

const EMPTY_CUSTOMER_NAMES = new Map<number, string>();

function ProcessingWasteLog({ batches }: { batches: ProcessingBatch[] }) {
  const groups = useProcessingLogGroups(batches, EMPTY_CUSTOMER_NAMES);
  const wasteTotal = groupTotalKg(groups.waste);
  const byDate = groupLogRowsByDate(groups.waste);
  if (groups.waste.length === 0) {
    return <p className="px-3 py-4 text-sm text-ink-muted">No waste recorded yet.</p>;
  }
  return (
    <LogSection
      title="Waste"
      titleTone="text-warning-700 dark:text-warning-300"
      totalKg={wasteTotal}
      emptyLabel="No waste"
    >
      {byDate.map((day) => (
        <LogDateGroup key={day.dayKey} label={day.label} totalKg={day.totalKg}>
          <Table
            columns={WASTE_COLUMNS}
            rows={day.rows}
            rowKey={(r) => r.id}
            caption={`Waste log ${day.label}`}
            compact
            stickyHeader={false}
          />
        </LogDateGroup>
      ))}
    </LogSection>
  );
}

function batchOptionLabel(batch: ProcessingBatch, allBatches: ProcessingBatch[]): string {
  const number = batchNumberFor(batch, allBatches);
  const { parts } = summarizeBatch(batch);
  const voided = batch.voided_at ? " · Voided" : "";
  return `Batch #${number} · ${formatDateTime(batch.operation_at)} · ${parts.join(" · ") || "Empty"}${voided}`;
}

function BatchDetailSection({
  title,
  titleTone,
  children,
  empty,
}: {
  title: string;
  titleTone: string;
  children: ReactNode;
  empty?: boolean;
}) {
  if (empty) return null;
  return (
    <section className="space-y-2">
      <h4 className={cn("text-sm font-semibold", titleTone)}>{title}</h4>
      <div className="rounded-xl border border-line/70 bg-surface-subtle/30 divide-y divide-line/60">
        {children}
      </div>
    </section>
  );
}

function BatchDetailLine({
  primary,
  secondary,
  qty,
}: {
  primary: string;
  secondary?: string;
  qty: string;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 text-sm">
      <div className="min-w-0">
        <p className="font-medium text-ink">{primary}</p>
        {secondary && <p className="mt-0.5 text-xs text-ink-muted">{secondary}</p>}
      </div>
      <span className="v2-mono shrink-0 font-semibold text-ink">{qty}</span>
    </div>
  );
}

function ProcessingBatchDetailModal({
  batch,
  allBatches,
  customerNames,
  open,
  onClose,
  onVoid,
}: {
  batch: ProcessingBatch | null;
  allBatches: ProcessingBatch[];
  customerNames: Map<number, string>;
  open: boolean;
  onClose: () => void;
  onVoid?: (batch: ProcessingBatch) => void;
}) {
  if (!batch) return null;

  const number = batchNumberFor(batch, allBatches);
  const voided = Boolean(batch.voided_at);
  const wasteParts: [string, string][] = [
    ["Dust", batch.dust_kg],
    ["Stone", batch.stone_kg],
    ["Sack weight", batch.sack_weight_waste_kg],
    [
      batch.powder_location_name
        ? `Powder @ ${[batch.powder_location_name, batch.powder_brand_name, batch.powder_bag_type_name]
            .filter(Boolean)
            .join(" · ")}`
        : "Powder",
      batch.powder_kg ?? "0",
    ],
    ["Misc (auto)", batch.miscellaneous_waste_kg],
  ].filter(([, kg]) => Number(kg) > 0) as [string, string][];

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={
        <span className="flex flex-wrap items-center gap-2">
          Batch #{number}
          {voided && <VoidPill when={batch.voided_at} />}
        </span>
      }
      description={formatDateTime(batch.operation_at)}
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Close
          </Button>
          {!voided && onVoid && (
            <Button
              type="button"
              variant="danger"
              leftIcon={<Ban className="h-4 w-4" />}
              onClick={() => onVoid(batch)}
            >
              Void batch
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-5">
        <BatchDetailSection
          title="Input"
          titleTone="text-primary-700 dark:text-primary-300"
          empty={batch.input_lines.length === 0}
        >
          {batch.input_lines.map((ln) => (
            <BatchDetailLine
              key={ln.id}
              primary={`${(ln.input_source ?? "fresh") === "balance_reprocess" ? "Reprocess" : "Fresh"} · ${ln.owner_type === "job_work" ? "Job work" : "Owned"}`}
              secondary={`${ln.location_name ?? "Location"} · ${ln.bag_type_name ?? "Bag type"}${ln.bag_count > 0 ? ` · ${ln.bag_count} bags` : ""}${Number(ln.loose_kg) > 0 ? ` · ${formatQtyKg(ln.loose_kg)} loose` : ""}`}
              qty={formatQtyKg(ln.quantity_kg)}
            />
          ))}
        </BatchDetailSection>

        <BatchDetailSection
          title="Output"
          titleTone="text-accent-800 dark:text-accent-300"
          empty={batch.output_lines.length === 0}
        >
          {batch.output_lines.map((ln) => (
            <BatchDetailLine
              key={ln.id}
              primary={`${ln.brand_name ?? "Brand"} · ${lineOwnerLabel(ln.owner_type, ln.customer_id, customerNames)}`}
              secondary={`${ln.location_name ?? "Location"} · ${ln.bag_type_name ?? "Bag type"}${ln.bag_count > 0 ? ` · ${ln.bag_count} bags` : ""}${Number(ln.loose_kg) > 0 ? ` · ${formatQtyKg(ln.loose_kg)} loose` : ""}`}
              qty={formatQtyKg(ln.quantity_kg)}
            />
          ))}
        </BatchDetailSection>

        <BatchDetailSection
          title="Balance return"
          titleTone="text-warning-800 dark:text-warning-300"
          empty={(batch.balance_return_lines ?? []).length === 0}
        >
          {(batch.balance_return_lines ?? []).map((ln) => (
            <BatchDetailLine
              key={ln.id}
              primary={lineOwnerLabel(ln.owner_type, ln.customer_id, customerNames)}
              secondary={`${ln.location_name ?? "Location"} · ${ln.bag_type_name ?? "Bag type"}${ln.bag_count > 0 ? ` · ${ln.bag_count} bags` : ""}${Number(ln.loose_kg) > 0 ? ` · ${formatQtyKg(ln.loose_kg)} loose` : ""}`}
              qty={formatQtyKg(ln.quantity_kg)}
            />
          ))}
        </BatchDetailSection>

        <BatchDetailSection title="Waste" titleTone="text-warning-700 dark:text-warning-300" empty={wasteParts.length === 0}>
          {wasteParts.map(([label, kg]) => (
            <BatchDetailLine key={label} primary={label} qty={formatQtyKg(kg)} />
          ))}
        </BatchDetailSection>

        {batch.input_lines.length === 0 &&
          batch.output_lines.length === 0 &&
          (batch.balance_return_lines ?? []).length === 0 &&
          wasteParts.length === 0 && (
            <p className="text-sm text-ink-muted">This batch has no recorded lines.</p>
          )}
      </div>
    </Modal>
  );
}

function ProcessingBatchHistory({
  batches,
  customerNames,
  onVoidBatch,
}: {
  batches: ProcessingBatch[];
  customerNames: Map<number, string>;
  onVoidBatch?: (batch: ProcessingBatch) => void;
}) {
  const sortedBatches = useMemo(
    () =>
      [...batches].sort(
        (a, b) => new Date(b.operation_at).getTime() - new Date(a.operation_at).getTime() || b.id - a.id
      ),
    [batches]
  );

  const [selectedId, setSelectedId] = useState("");
  const [detailBatch, setDetailBatch] = useState<ProcessingBatch | null>(null);

  useEffect(() => {
    if (sortedBatches.length === 0) {
      setSelectedId("");
      return;
    }
    const stillValid = sortedBatches.some((b) => String(b.id) === selectedId);
    if (!stillValid) setSelectedId(String(sortedBatches[0].id));
  }, [sortedBatches, selectedId]);

  const selectedBatch =
    sortedBatches.find((b) => String(b.id) === selectedId) ?? sortedBatches[0] ?? null;

  if (batches.length === 0) {
    return (
      <EmptyState
        icon={<Layers className="h-8 w-8" />}
        title="No batches yet"
        description="Submit input, output, or waste on the other tabs — each submit appears here as one batch."
      />
    );
  }

  return (
    <>
      <div className="space-y-4">
        <FormField label="Select batch" hint={`${sortedBatches.length} batch${sortedBatches.length === 1 ? "" : "es"} · newest first`}>
          <Select
            value={selectedId || String(sortedBatches[0]?.id ?? "")}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {sortedBatches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batchOptionLabel(batch, batches)}
              </option>
            ))}
          </Select>
        </FormField>

        {selectedBatch && (
          <button
            type="button"
            className={cn(
              "w-full rounded-xl border border-line/70 bg-surface p-4 text-left shadow-sm transition-colors",
              "hover:border-primary-300/60 hover:bg-primary-50/20 dark:hover:border-primary-700/40 dark:hover:bg-primary-950/15",
              selectedBatch.voided_at && "opacity-65"
            )}
            onClick={() => setDetailBatch(selectedBatch)}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("text-sm font-semibold text-ink", selectedBatch.voided_at && "line-through")}>
                Batch #{batchNumberFor(selectedBatch, batches)}
              </span>
              <span className="v2-mono text-xs text-ink-muted">{formatDateTime(selectedBatch.operation_at)}</span>
              {selectedBatch.voided_at && <VoidPill when={selectedBatch.voided_at} />}
            </div>
            <p className={cn("mt-2 text-sm text-ink-muted", selectedBatch.voided_at && "line-through")}>
              {summarizeBatch(selectedBatch).parts.join(" · ") || "Empty batch"}
            </p>
            <p className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary-700 dark:text-primary-300">
              <Eye className="h-3.5 w-3.5" />
              Click for full batch details
            </p>
          </button>
        )}

        <div className="flex flex-wrap gap-2">
          {selectedBatch && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              leftIcon={<Eye className="h-4 w-4" />}
              onClick={() => setDetailBatch(selectedBatch)}
            >
              View details
            </Button>
          )}
          {selectedBatch && !selectedBatch.voided_at && onVoidBatch && (
            <Button
              type="button"
              variant="danger"
              size="sm"
              leftIcon={<Ban className="h-3.5 w-3.5" />}
              onClick={() => onVoidBatch(selectedBatch)}
            >
              Void selected batch
            </Button>
          )}
        </div>
      </div>

      <ProcessingBatchDetailModal
        batch={detailBatch}
        allBatches={batches}
        customerNames={customerNames}
        open={detailBatch != null}
        onClose={() => setDetailBatch(null)}
        onVoid={
          onVoidBatch
            ? (batch) => {
                setDetailBatch(null);
                onVoidBatch(batch);
              }
            : undefined
        }
      />
    </>
  );
}
