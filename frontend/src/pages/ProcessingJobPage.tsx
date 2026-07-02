import { FormEvent, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
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
  jobWorkApi,
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
import Modal from "../components/ui/Modal";
import { VoidPill } from "../components/ui/StatusPill";
import SegmentedControl from "../components/ui/SegmentedControl";
import { cn } from "../lib/cn";
import { calcPreviewTotalKg, isLooseBagType } from "../lib/bagType";
import { formatDateTime, formatQtyKg } from "../lib/format";
import { computeMassBalance, jobAvailableReprocessKg, jobSummary, totalOutputKg, activeProcessingBatches } from "../lib/processingSummary";
import { usePermissions } from "../lib/permissions";
import {
  formatAvailableStock,
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

type InputLineForm = {
  key: string;
  input_source: ProcessingInputSource;
  owner_type: "owned" | "job_work";
  customer_id: string;
  job_work_order_id: string;
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
};

const emptyInputLine = (): InputLineForm => ({
  key: crypto.randomUUID(),
  input_source: "fresh",
  owner_type: "owned",
  customer_id: "",
  job_work_order_id: "",
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
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const bagTypeCache = useBagTypeCache();
  const getBagType = bagTypeCache.get;
  const [customerLabels, setCustomerLabels] = useState<CustomerLabelLookup>({});
  const [stockByLocation, setStockByLocation] = useState<Record<string, StockAtLocation[]>>({});
  const [jwOrdersByCustomer, setJwOrdersByCustomer] = useState<Record<string, { id: number; job_number: string }[]>>({});
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
  const [jobLoadDone, setJobLoadDone] = useState(false);
  const [outputAllocationMode, setOutputAllocationMode] = useState<OutputAllocationMode>("proportional");
  const [singleAllocationOwnerKey, setSingleAllocationOwnerKey] = useState("owned");
  const inputBatchIdemRef = useRef<string | null>(null);
  const outputBatchIdemRef = useRef<string | null>(null);
  const wasteBatchIdemRef = useRef<string | null>(null);
  const completeIdemRef = useRef<string | null>(null);

  const { canVoid } = usePermissions();
  const summary = useMemo(() => (job ? jobSummary(job) : null), [job]);
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
        job_work_order_id: "",
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

  const loadJwOrdersForCustomer = useCallback((customerId: string) => {
    if (!customerId || jwOrdersByCustomer[customerId]) return;
    jobWorkApi
      .list({ customer_id: Number(customerId), status: "open", limit: 100 })
      .then((page) => {
        setJwOrdersByCustomer((prev) => ({
          ...prev,
          [customerId]: page.items.map((o) => ({ id: o.id, job_number: o.job_number })),
        }));
      })
      .catch(() => {});
  }, [jwOrdersByCustomer]);

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
          job_work_order_id:
            ln.owner_type === "job_work" && ln.job_work_order_id ? Number(ln.job_work_order_id) : null,
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
    if (!job) return [] as { available: string; warning: string }[];
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
      const reserved = reservedStockFromSiblingLines(
        bt,
        inputForm.input_lines,
        idx,
        (i) =>
          inputForm.input_lines[i].location_id === ln.location_id &&
          inputForm.input_lines[i].bag_type_id === ln.bag_type_id &&
          inputForm.input_lines[i].owner_type === ln.owner_type &&
          inputForm.input_lines[i].customer_id === ln.customer_id
      );
      const available = row && bt ? formatAvailableStock(bt, row) : "";
      const warning = stockExceedsMessageWithReserved(
        bt,
        ln.bag_count,
        ln.loose_kg,
        row,
        reserved.bagCount,
        reserved.looseKg
      );
      const reprocessWarning =
        ln.input_source === "balance_reprocess" && warning
          ? `Returned balance may have been sold; stock here: ${available || "none"}`
          : warning;
      return { available, warning: reprocessWarning };
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
      const ownerLabel = ownerKeyLabel(singleAllocationOwnerKey, customerLabels);
      const ok = window.confirm(
        `All outputs will post to ${ownerLabel}. You may add more input from ${ownerLabel} only.`
      );
      if (!ok) return;
    }

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
      const ok = window.confirm(
        "Fresh input has been recorded but no finished output yet. Complete this job anyway?"
      );
      if (!ok) return;
    }

    if (netBalance > 0.001 && totalFresh > 0 && netBalance / totalFresh > 0.05) {
      const ok = window.confirm(
        `${formatQtyKg(netBalance)} net unclean balance remains vs ${formatQtyKg(totalFresh)} fresh input. Complete anyway?`
      );
      if (!ok) return;
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
        <PageHeader eyebrow="Processing job" title="Loading job…" />
        <div className="space-y-4">
          <Skeleton className="h-28 w-full rounded-2xl" />
          <Skeleton className="h-12 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </div>
      </>
    );
  }

  if (!job) {
    return (
      <>
        <PageHeader eyebrow="Processing job" title="Could not load job" />
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
                <Button variant="ghost">All jobs</Button>
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

  return (
    <>
      <PageHeader
        eyebrow="Processing job"
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span>
              {job.input_product_name} · {job.input_brand_name}
            </span>
            <Badge tone={jobStatusTone(job.status)} size="md">
              {job.status}
            </Badge>
          </span>
        }
        subtitle={
          job.completed_at
            ? `Completed ${formatDateTime(job.completed_at)}`
            : "Record input and output batches, then complete when mass balance is valid."
        }
        actions={
          <Link to="/operations/processing">
            <Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
              All jobs
            </Button>
          </Link>
        }
      />

      {summary && <SummaryStrip summary={summary} massBalance={committedMassBalance} />}

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {success && (
        <Banner tone="success" className="mb-4" onClose={() => setSuccess("")}>
          {success}
        </Banner>
      )}

      <Tabs value={activeTab} onChange={(id) => setActiveTab(id as TabId)} variant="pill" className="mb-2">
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
                                  <p className="text-sm text-ink-muted">Available: {stockInfo.available}</p>
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
                                        job_work_order_id: "",
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
                              <>
                                <FormField label="Customer" required>
                                  {() => (
                                    <AsyncSearchCombobox
                                      value={ln.customer_id ? Number(ln.customer_id) : null}
                                      disabled={Boolean(lockedInputOwner)}
                                      onChange={(customerId, opt) => {
                                        if (lockedInputOwner) return;
                                        const v = customerId != null ? String(customerId) : "";
                                        if (v) {
                                          loadJwOrdersForCustomer(v);
                                          if (opt?.label) {
                                            setCustomerLabels((prev) => ({
                                              ...prev,
                                              [Number(v)]: opt.label,
                                            }));
                                          }
                                        }
                                        setInputForm((f) => {
                                          const lines = [...f.input_lines];
                                          lines[idx] = {
                                            ...lines[idx],
                                            customer_id: v,
                                            job_work_order_id: "",
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
                                <FormField label="Job work order" hint="Optional link to an open order">
                                  {({ id }) => (
                                    <Select
                                      id={id}
                                      value={ln.job_work_order_id}
                                      disabled={!ln.customer_id}
                                      onChange={(e) => {
                                        const v = e.target.value;
                                        setInputForm((f) => {
                                          const lines = [...f.input_lines];
                                          lines[idx] = { ...lines[idx], job_work_order_id: v };
                                          return { ...f, input_lines: lines };
                                        });
                                      }}
                                    >
                                      <option value="">None</option>
                                      {(jwOrdersByCustomer[ln.customer_id] ?? []).map((o) => (
                                        <option key={o.id} value={o.id}>
                                          {o.job_number}
                                        </option>
                                      ))}
                                    </Select>
                                  )}
                                </FormField>
                              </>
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
                  <MassBalancePanel balance={outputPendingMassBalance} />

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
                                      lines[idx] = { ...lines[idx], brand_id: v };
                                      return { ...f, output_lines: lines };
                                    });
                                  }}
                                  searchFn={searchBrands}
                                  placeholder="Search brand…"
                                  emptyText="No matching brand"
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
                                      lines[idx] = { ...lines[idx], location_id: v };
                                      return { ...f, output_lines: lines };
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
                                      const lines = [...f.output_lines];
                                      lines[idx] = { ...lines[idx], bag_type_id: v, ...emptyQtyFields() };
                                      return { ...f, output_lines: lines };
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

                  {!outputPendingMassBalance.isValid && outputPendingMassBalance.errorMessage && (
                    <Banner tone="danger">{outputPendingMassBalance.errorMessage}</Banner>
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
                  <MassBalancePanel balance={wastePendingMassBalance} />
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

                  {!wastePendingMassBalance.isValid && wastePendingMassBalance.errorMessage && (
                    <Banner tone="danger">{wastePendingMassBalance.errorMessage}</Banner>
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
  tone = "neutral",
  highlight,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "primary" | "success" | "warning" | "muted";
  highlight?: boolean;
}) {
  const toneClass = {
    neutral: "border-line/80 bg-surface",
    primary: "border-primary-200/70 bg-primary-50/50 dark:border-primary-800/40 dark:bg-primary-950/25",
    success: "border-accent-200/70 bg-accent-50/50 dark:border-accent-800/40 dark:bg-accent-950/25",
    warning: "border-warning-200/70 bg-warning-50/50 dark:border-warning-800/40 dark:bg-warning-950/25",
    muted: "border-line/60 bg-surface-subtle/50",
  }[tone];

  return (
    <div
      className={cn(
        "rounded-2xl border p-4 shadow-sm",
        toneClass,
        highlight && "ring-2 ring-primary-400/40 dark:ring-primary-500/30"
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={cn("mt-2 v2-mono text-xl font-bold text-ink", highlight && "text-primary-800 dark:text-primary-200")}>
        {value}
      </p>
    </div>
  );
}

function MassBalancePanel({ balance }: { balance: ReturnType<typeof computeMassBalance> }) {
  const usedPct =
    balance.freshInputKg > 0
      ? Math.min(100, (balance.totalOutflowKg / balance.freshInputKg) * 100)
      : 0;
  const warn = balance.allowanceRemainingKg < 0;

  return (
    <div
      className={cn(
        "rounded-2xl border p-5",
        warn
          ? "border-warning-300/70 bg-warning-50/40 dark:border-warning-700/50 dark:bg-warning-950/20"
          : "border-primary-200/60 bg-gradient-to-br from-primary-50/50 via-surface to-violet-50/30 dark:border-primary-800/40 dark:from-primary-950/25 dark:via-surface dark:to-violet-950/15"
      )}
    >
      <div className="mb-4 flex items-center gap-2">
        <Scale className="h-5 w-5 text-primary-600 dark:text-primary-300" aria-hidden="true" />
        <h4 className="text-lg font-semibold text-ink">Mass balance preview</h4>
      </div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricTile label="Fresh input (job)" value={formatQtyKg(balance.freshInputKg)} tone="primary" />
        <MetricTile label="Total outflow" value={formatQtyKg(balance.totalOutflowKg)} />
        <MetricTile
          label="Allowance remaining"
          value={formatQtyKg(balance.allowanceRemainingKg)}
          tone={warn ? "warning" : "success"}
          highlight={warn}
        />
      </div>
      {balance.freshInputKg > 0 && (
        <div>
          <div className="mb-1 flex justify-between text-sm text-ink-muted">
            <span>Outflow vs input</span>
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
          <p className="mt-2 text-xs text-ink-subtle">100 kg tolerance band enforced on submit.</p>
        </div>
      )}
    </div>
  );
}

function SummaryStrip({
  summary,
  massBalance,
}: {
  summary: ProcessingJobSummary;
  massBalance: ReturnType<typeof computeMassBalance>;
}) {
  const outputKg = totalOutputKg(summary);
  const netBalance = Number(summary.net_balance_kg);
  const warn = massBalance.allowanceRemainingKg < 0;

  return (
    <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricTile
        label="Fresh in"
        value={`${summary.fresh_input_bags > 0 ? `${summary.fresh_input_bags} bags · ` : ""}${formatQtyKg(summary.total_fresh_input_kg)}`}
        tone="primary"
      />
      <MetricTile label="Output" value={formatQtyKg(outputKg)} tone="success" />
      <MetricTile
        label="Net unclean"
        value={formatQtyKg(netBalance)}
        tone={netBalance > 0 ? "warning" : "neutral"}
        highlight={netBalance > 0}
      />
      <MetricTile
        label="Batches"
        value={String(summary.batch_count)}
        tone={warn ? "warning" : "neutral"}
      />
    </div>
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

function totalPowderKgFromBatches(batches: ProcessingBatch[]): number {
  return activeProcessingBatches(batches).reduce((sum, batch) => sum + Number(batch.powder_kg ?? 0), 0);
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

function powderStorageLabelsFromBatches(batches: ProcessingBatch[]): string[] {
  const labels = new Set<string>();
  for (const batch of activeProcessingBatches(batches)) {
    if (Number(batch.powder_kg) <= 0) continue;
    if (batch.powder_location_name) {
      const parts = [batch.powder_location_name, batch.powder_brand_name, batch.powder_bag_type_name].filter(Boolean);
      labels.add(parts.join(" · "));
    }
  }
  return [...labels];
}

function SummaryCard({
  summary,
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
  const wasteKg = Number(summary.total_waste_kg);
  const powderKg = totalPowderKgFromBatches(batches);
  const wasteExclPowderKg = Math.max(wasteKg - powderKg, 0);
  const miscKg = Number(summary.total_misc_kg);
  const lossKg = Number(summary.total_loss_kg);
  const wasteSplits = aggregateWasteAllocations(batches);
  const auditWasteSplits = wasteSplits
    .map((wa) => ({ wa, categories: wasteAuditCategories(wa) }))
    .filter((row) => row.categories.length > 0);
  const powderStorageLabels = powderStorageLabelsFromBatches(batches);

  return (
    <Card className="overflow-hidden border-primary-200/60 bg-gradient-to-br from-primary-50/35 via-surface to-violet-50/25 dark:border-primary-800/40 dark:from-primary-950/20">
      <CardHeader
        title="At a glance"
        subtitle={`${summary.batch_count} batch${summary.batch_count === 1 ? "" : "es"} committed`}
      />
      <CardBody className="space-y-5">
        {allocationHint ? (
          <Banner tone="info">{allocationHint}</Banner>
        ) : null}
        {inputRulesHint && inputRulesHint !== allocationHint ? (
          <Banner tone="info">{inputRulesHint}</Banner>
        ) : null}
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">Output by brand</p>
          {summary.output_by_brand.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {summary.output_by_brand.map((row) => (
                <span
                  key={row.brand_id}
                  className="inline-flex items-center gap-2 rounded-xl border border-accent-200/60 bg-accent-50/40 px-3 py-2.5 text-base dark:border-accent-800/40 dark:bg-accent-950/20"
                >
                  <span className="font-semibold text-ink">{row.brand_name ?? `Brand #${row.brand_id}`}</span>
                  <span className="v2-mono font-bold text-accent-800 dark:text-accent-300">
                    {formatQtyKg(row.quantity_kg)}
                  </span>
                  {row.bag_count > 0 && (
                    <span className="text-sm text-ink-muted">· {row.bag_count} bags</span>
                  )}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-base text-ink-muted">No finished output recorded yet.</p>
          )}
        </div>

        <div
          className={cn(
            "grid grid-cols-1 gap-3",
            powderKg > 0 ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-3"
          )}
        >
          <MetricTile
            label={powderKg > 0 ? "Waste (excl. powder)" : "Waste"}
            value={formatQtyKg(powderKg > 0 ? wasteExclPowderKg : wasteKg)}
            tone="warning"
          />
          {powderKg > 0 && (
            <MetricTile label="Powder stock" value={formatQtyKg(powderKg)} tone="success" highlight />
          )}
          <MetricTile label="Misc" value={formatQtyKg(miscKg)} tone="muted" />
          <MetricTile label="Total loss" value={formatQtyKg(lossKg)} tone="warning" highlight={lossKg > 0} />
        </div>

        {powderKg > 0 && (
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Powder added to inventory
            </p>
            <div className="rounded-xl border border-accent-200/60 bg-accent-50/35 px-3 py-2.5 dark:border-accent-800/40 dark:bg-accent-950/20">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-ink">Consolidated powder pile</span>
                <span className="v2-mono text-sm font-semibold text-accent-800 dark:text-accent-300">
                  {formatQtyKg(powderKg)}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-muted">
                {powderStorageLabels.length > 0 ? (
                  <>
                    Stored at{" "}
                    {powderStorageLabels.map((label, i) => (
                      <span key={label}>
                        {i > 0 ? "; " : ""}
                        <span className="font-medium text-ink">{label}</span>
                      </span>
                    ))}
                  </>
                ) : (
                  "Location recorded on each waste batch with powder."
                )}
              </p>
              <p className="mt-1 text-xs text-ink-subtle">
                Entered on the Waste tab for mass balance; unlike dust, stone, and sack weight, powder posts as
                saleable stock at that location.
              </p>
            </div>
          </div>
        )}

        {auditWasteSplits.length > 0 && (
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

function summarizeBatch(batch: ProcessingBatch): { inputKg: number; outputKg: number; wasteKg: number; parts: string[] } {
  const inputKg = batch.input_lines.reduce((sum, ln) => sum + Number(ln.quantity_kg), 0);
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
  if (inputKg > 0) parts.push(`Input ${formatQtyKg(inputKg)}`);
  if (outputKg > 0) parts.push(`Output ${formatQtyKg(outputKg)}`);
  if (wasteKg > 0) parts.push(`Waste ${formatQtyKg(wasteKg)}`);
  return { inputKg, outputKg, wasteKg, parts };
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

function LogSection({
  title,
  titleTone,
  totalKg,
  children,
  emptyLabel,
}: {
  title: string;
  titleTone: string;
  totalKg: number;
  children: ReactNode;
  emptyLabel: string;
}) {
  return (
    <section className="rounded-2xl border border-line/80 bg-surface/50">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 px-4 py-3 sm:px-5">
        <h4 className={cn("text-base font-semibold", titleTone)}>{title}</h4>
        <span className="v2-mono text-sm font-semibold text-ink">
          {totalKg > 0 ? formatQtyKg(totalKg) : emptyLabel}
        </span>
      </div>
      <div className="p-1 sm:p-2">{children}</div>
    </section>
  );
}

const INPUT_COLUMNS: Column<InputLogRow>[] = [
  {
    key: "at",
    header: "Date & time",
    cell: (r) => <span className="v2-mono text-sm text-ink">{formatDateTime(r.at)}</span>,
  },
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
];

const OUTPUT_COLUMNS: Column<OutputLogRow>[] = [
  {
    key: "at",
    header: "Date & time",
    cell: (r) => <span className="v2-mono text-sm text-ink">{formatDateTime(r.at)}</span>,
  },
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
];

const WASTE_COLUMNS: Column<WasteLogRow>[] = [
  {
    key: "at",
    header: "Date & time",
    cell: (r) => <span className="v2-mono text-sm text-ink">{formatDateTime(r.at)}</span>,
  },
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
  const inputTotal = groupTotalKg(groups.input);
  if (groups.input.length === 0) {
    return <p className="px-3 py-4 text-sm text-ink-muted">No input recorded yet.</p>;
  }
  return (
    <LogSection
      title="Input"
      titleTone="text-primary-700 dark:text-primary-300"
      totalKg={inputTotal}
      emptyLabel="No input"
    >
      <Table columns={INPUT_COLUMNS} rows={groups.input} rowKey={(r) => r.id} caption="Input log" compact />
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
      <Table columns={OUTPUT_COLUMNS} rows={groups.output} rowKey={(r) => r.id} caption="Output log" compact />
    </LogSection>
  );
}

const EMPTY_CUSTOMER_NAMES = new Map<number, string>();

function ProcessingWasteLog({ batches }: { batches: ProcessingBatch[] }) {
  const groups = useProcessingLogGroups(batches, EMPTY_CUSTOMER_NAMES);
  const wasteTotal = groupTotalKg(groups.waste);
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
      <Table columns={WASTE_COLUMNS} rows={groups.waste} rowKey={(r) => r.id} caption="Waste log" compact />
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
