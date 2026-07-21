import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Package, Plus, UserPlus } from "lucide-react";
import {
  api,
  idempotencyHeadersOptionalAuth,
  newIdempotencyKey,
  type BagType,
  type Bill,
  type Customer,
} from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import { isLooseBagType, calcPreviewTotalKg } from "../lib/bagType";
import { formatInr, formatQtyKg } from "../lib/format";
import { isAuthPasswordError, isBackdatedDate } from "../lib/backdateAuth";
import BackdateAuthDialog from "../components/ui/BackdateAuthDialog";
import {
  exceedsAvailableStock,
  formatRemainingStockAfterReserved,
  reservedStockFromEarlierLines,
  reservedStockFromSiblingLines,
  stockExceedsMessageWithReserved,
} from "../lib/stockWarning";
import {
  fetchBagTypesByIds,
  searchBagTypes,
  searchBrands,
  searchCustomers,
  searchLocations,
  searchProducts,
  type MasterComboOption,
} from "../lib/masterSearch";
import { deliveryStatusLabel, statusBadgeClass } from "../lib/statusLabels";
import { stockRow, type StockAtLocation, bagTypesFromStock, brandsFromStock, filterStockForOwner, jobWorkCustodiansAtLocation, productsFromStock, stockOwnerFilter } from "../lib/stockAtLocation";
import PageHeader from "../components/ui/PageHeader";
import V13Button from "../components/ui/Button";
import V13Banner from "../components/ui/Banner";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import FormField from "../components/ui/FormField";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import AddCustomerDialog from "../components/AddCustomerDialog";
import Textarea from "../components/ui/Textarea";
import ConfirmDialog from "../components/ui/ConfirmDialog";

type LineForm = {
  line_id?: number;
  product_id: string;
  brand_id: string;
  bag_type_id: string;
  ordered_bags: string;
  ordered_loose_kg: string;
  rate_per_kg: string;
  stock_source: "owned" | "job_work";
};

type StockRow = StockAtLocation;

const emptyLine = (): LineForm => ({
  product_id: "",
  brand_id: "",
  bag_type_id: "",
  ordered_bags: "",
  ordered_loose_kg: "",
  rate_per_kg: "",
  stock_source: "owned",
});

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Error";
}

function localIsoDate(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function orderedQtyKg(line: LineForm, bt: BagType | undefined): number {
  return calcPreviewTotalKg(bt, line.ordered_bags, line.ordered_loose_kg);
}

function resetLineFrom(line: LineForm, step: "product" | "brand" | "bag_type" | "rate"): LineForm {
  if (step === "product") {
    return { ...emptyLine(), stock_source: line.stock_source };
  }
  if (step === "brand") {
    return { ...line, brand_id: "", bag_type_id: "", ordered_bags: "", ordered_loose_kg: "", rate_per_kg: "" };
  }
  if (step === "bag_type") {
    return { ...line, bag_type_id: "", ordered_bags: "", ordered_loose_kg: "", rate_per_kg: "" };
  }
  return { ...line, rate_per_kg: "", ordered_bags: "", ordered_loose_kg: "" };
}

function isDuplicateLine(lines: LineForm[], idx: number, isSales: boolean): boolean {
  if (isSales) return false;
  const line = lines[idx];
  if (!line.product_id || !line.brand_id || !line.bag_type_id) return false;
  return lines.some(
    (l, i) =>
      i !== idx &&
      l.product_id === line.product_id &&
      l.brand_id === line.brand_id &&
      l.bag_type_id === line.bag_type_id
  );
}

function linePayload(
  line: LineForm,
  getBagType: (id: string) => BagType | undefined,
  isSales: boolean
) {
  const bt = getBagType(line.bag_type_id);
  const base = {
    product_id: Number(line.product_id),
    brand_id: Number(line.brand_id),
    bag_type_id: Number(line.bag_type_id),
    ordered_bags: isLooseBagType(bt) ? 0 : Number(line.ordered_bags),
    ordered_loose_kg: isLooseBagType(bt) ? Number(line.ordered_loose_kg) : 0,
    rate_per_kg: Number(line.rate_per_kg),
  };
  if (!isSales) return base;
  return {
    ...base,
    stock_source: line.stock_source,
    line_charge_type: line.stock_source === "job_work" ? "processing_charge" : "product_sale",
  };
}

export default function BillFormPage({
  billType,
  edit: editMode = false,
}: {
  billType: "sales" | "purchase";
  edit?: boolean;
}) {
  const { id } = useParams();
  const navigate = useNavigate();
  const listPath = billType === "sales" ? "/sales-bills" : "/purchase-bills";
  const isSales = billType === "sales";
  const bagsLabel = isSales ? "Bags sold" : "Bags purchased";

  const [bill, setBill] = useState<Bill | null>(null);
  const [loading, setLoading] = useState(editMode);
  const bagTypeCache = useBagTypeCache();
  const [selectedCustomerLabel, setSelectedCustomerLabel] = useState("");
  const [previewBillNumber, setPreviewBillNumber] = useState("");
  const [stock, setStock] = useState<StockRow[]>([]);
  const [stockLoading, setStockLoading] = useState(false);
  const [error, setError] = useState("");
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);
  const [addCustomerOpen, setAddCustomerOpen] = useState(false);
  const [pendingCustomerChange, setPendingCustomerChange] = useState<string | null>(null);
  const [pendingLocationChange, setPendingLocationChange] = useState<string | null>(null);
  const maxBillDate = useMemo(() => localIsoDate(), []);
  const [billDate, setBillDate] = useState(() => localIsoDate());

  const idemKey = () => {
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    return idemKeyRef.current;
  };
  const clearIdemKey = () => {
    idemKeyRef.current = null;
  };

  const [header, setHeader] = useState({ customer_id: "", location_id: "" });
  const [discountPercent, setDiscountPercent] = useState("");
  const [adjustment, setAdjustment] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineForm[]>([emptyLine()]);

  const headerReady = isSales
    ? Boolean(header.customer_id && header.location_id)
    : Boolean(header.customer_id);
  const linesEnabled = !editMode && headerReady;

  useEffect(() => {
    if (!editMode || !id) return;
    setLoading(true);
    api
      .get<Bill>(`/api/bills/${id}`)
      .then((b) => {
        if (b.status !== "finalized") {
          setError("Only finalized bills can be edited");
          return;
        }
        if (b.bill_type !== billType) {
          setError("Bill type mismatch");
          return;
        }
        setBill(b);
        setHeader({
          customer_id: String(b.customer_id),
          location_id: b.location_id != null ? String(b.location_id) : "",
        });
        setDiscountPercent(b.discount_percent);
        setAdjustment(b.adjustment);
        setNotes(b.notes ?? "");
        setLines(
          b.lines.map((l) => ({
            line_id: l.id,
            product_id: String(l.product_id),
            brand_id: String(l.brand_id),
            bag_type_id: String(l.bag_type_id),
            ordered_bags: String(l.ordered_bags),
            ordered_loose_kg: l.ordered_loose_kg,
            rate_per_kg: l.rate_per_kg,
            stock_source: l.stock_source ?? "owned",
          }))
        );
      })
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false));
  }, [editMode, id, billType]);

  useEffect(() => {
    if (!bill?.lines.length) return;
    fetchBagTypesByIds(bill.lines.map((l) => l.bag_type_id)).then(bagTypeCache.rememberMany);
  }, [bill, bagTypeCache.rememberMany]);

  useEffect(() => {
    if (editMode) return;
    api
      .get<{ bill_number: string }>(`/api/bills/next-number?bill_type=${billType}`)
      .then((r) => setPreviewBillNumber(r.bill_number))
      .catch(() => setPreviewBillNumber(billType === "sales" ? "S-000001" : "P-000001"));
  }, [billType, editMode]);

  useEffect(() => {
    if (!isSales || editMode || !header.location_id) {
      setStock([]);
      return;
    }
    setStockLoading(true);
    api
      .get<StockRow[]>(`/api/inventory/stock-at-location?location_id=${header.location_id}`)
      .then(setStock)
      .catch(() => setStock([]))
      .finally(() => setStockLoading(false));
  }, [header.location_id, editMode, isSales]);

  const getBagType = bagTypeCache.get;

  const totals = useMemo(() => {
    let totalAmount = 0;
    for (const line of lines) {
      if (!line.product_id || !line.brand_id || !line.bag_type_id) continue;
      const bt = getBagType(line.bag_type_id);
      const qty = orderedQtyKg(line, bt);
      totalAmount += qty * (Number(line.rate_per_kg) || 0);
    }
    const discPct = Number(discountPercent) || 0;
    const discountAmount = (totalAmount * discPct) / 100;
    const adj = Number(adjustment) || 0;
    const finalPayable = totalAmount - discountAmount - adj;
    return { totalAmount, discountAmount, finalPayable };
  }, [lines, getBagType, discountPercent, adjustment]);

  const amountPaid = editMode && bill ? Number(bill.amount_paid) || 0 : 0;
  const amountDue = useMemo(
    () => Math.max(totals.finalPayable - amountPaid, 0),
    [totals.finalPayable, amountPaid]
  );

  const productsBilledCount = useMemo(
    () => lines.filter((l) => l.product_id && l.brand_id && l.bag_type_id).length,
    [lines]
  );

  const handleCustomerChange = (customerId: string) => {
    if (
      header.customer_id &&
      customerId !== header.customer_id &&
      lines.some((l) => l.product_id || l.brand_id || l.bag_type_id)
    ) {
      setPendingCustomerChange(customerId);
      return;
    }
    setHeader((h) => ({ ...h, customer_id: customerId }));
  };

  const handleCustomerCreated = (customer: Customer) => {
    setSelectedCustomerLabel(customer.name);
    handleCustomerChange(String(customer.id));
  };

  const jobWorkCustodians = useMemo(
    () => (isSales ? jobWorkCustodiansAtLocation(stock) : []),
    [isSales, stock]
  );

  const selectedCustomerName = useMemo(
    () => (editMode && bill?.customer_name ? bill.customer_name : selectedCustomerLabel),
    [editMode, bill?.customer_name, selectedCustomerLabel]
  );

  const handleLocationChange = (newLocationId: string) => {
    // Purchase bills have no location field — only sales confirms location changes.
    const prev = header.location_id;
    if (
      isSales &&
      prev &&
      newLocationId !== prev &&
      lines.some((l) => l.product_id || l.brand_id || l.bag_type_id)
    ) {
      setPendingLocationChange(newLocationId);
      return;
    }
    setHeader({ ...header, location_id: newLocationId });
  };

  const updateLine = (idx: number, next: LineForm) => {
    const n = [...lines];
    n[idx] = next;
    setLines(n);
  };

  const validateTotals = (): string | null => {
    if (Number(adjustment) < 0) return "Adjustment must be zero or greater";
    if (totals.finalPayable < 0) return "Final payable cannot be negative";
    return null;
  };

  const validateCreateLines = (): string | null => {
    const complete = lines.filter((l) => l.product_id && l.brand_id && l.bag_type_id);
    if (!complete.length) return "Add at least one complete line";
    for (let i = 0; i < lines.length; i++) {
      if (isDuplicateLine(lines, i, isSales)) return "Duplicate line: same product, brand, and bag type";
    }
    let hasPositiveQty = false;
    for (const line of complete) {
      const bt = getBagType(line.bag_type_id);
      if (!bt) return "Invalid bag type on a line";
      const qty = orderedQtyKg(line, bt);
      if (qty < 0) return "Quantity cannot be negative";
      if (qty > 0) hasPositiveQty = true;
      if (!line.rate_per_kg || Number(line.rate_per_kg) < 0) return "Enter rate per kg on each line";
    }
    if (!hasPositiveQty) return "At least one line must have quantity greater than zero";
    return null;
  };

  const stockWarnings = useMemo(() => {
    if (billType !== "sales" || !headerReady) return [] as string[];
    const warnings: string[] = [];
    const seenBuckets = new Set<string>();

    lines.forEach((line) => {
      if (!line.product_id || !line.brand_id || !line.bag_type_id) return;
      const bucketKey = `${line.product_id}|${line.brand_id}|${line.bag_type_id}|${line.stock_source}`;
      if (seenBuckets.has(bucketKey)) return;
      seenBuckets.add(bucketKey);

      const bt = getBagType(line.bag_type_id);
      const owner = stockOwnerFilter(line.stock_source, header.customer_id);
      const scopedStock = filterStockForOwner(stock, owner);
      const row = stockRow(scopedStock, line.product_id, line.brand_id, line.bag_type_id, owner);
      const sourceLabel = line.stock_source === "job_work" ? "job work" : "owned";
      const label = row?.product_name ?? `Product #${line.product_id}`;

      let totalBags = 0;
      let totalLooseKg = 0;
      for (const ln of lines) {
        if (
          ln.product_id !== line.product_id ||
          ln.brand_id !== line.brand_id ||
          ln.bag_type_id !== line.bag_type_id ||
          ln.stock_source !== line.stock_source
        ) {
          continue;
        }
        if (!ln.product_id || !ln.brand_id || !ln.bag_type_id) continue;
        const lnBt = getBagType(ln.bag_type_id);
        if (isLooseBagType(lnBt)) {
          totalLooseKg += Number(ln.ordered_loose_kg) || 0;
        } else {
          totalBags += Number(ln.ordered_bags) || 0;
        }
      }

      const totalKg = calcPreviewTotalKg(bt, totalBags, totalLooseKg);
      if (totalKg <= 0) return;

      if (!row || exceedsAvailableStock(bt, totalBags, totalLooseKg, row)) {
        warnings.push(`${label}: insufficient ${sourceLabel} stock at this location`);
      }
    });
    return warnings;
  }, [billType, headerReady, lines, getBagType, stock, header.customer_id]);

  const buildCreatePayload = () => {
    const payload: Record<string, unknown> = {
      bill_type: billType,
      customer_id: Number(header.customer_id),
      bill_date: billDate,
      discount_percent: Number(discountPercent),
      adjustment: Number(adjustment),
      notes: notes.trim() || null,
      lines: lines
        .filter((l) => l.product_id && l.brand_id && l.bag_type_id)
        .map((l) => linePayload(l, getBagType, isSales)),
    };
    if (isSales) {
      payload.location_id = Number(header.location_id);
    }
    return payload;
  };

  const buildEditPayload = () => ({
    expected_version: bill?.version,
    discount_percent: Number(discountPercent),
    adjustment: Number(adjustment),
    notes: notes.trim() || null,
    lines: (bill?.lines ?? []).map((bl, idx) => {
      const lf = lines[idx];
      const bt = getBagType(String(bl.bag_type_id));
      const base = { id: bl.id, rate_per_kg: Number(lf.rate_per_kg) };
      if (isLooseBagType(bt)) {
        return { ...base, ordered_loose_kg: Number(lf.ordered_loose_kg) };
      }
      return { ...base, ordered_bags: Number(lf.ordered_bags) };
    }),
  });

  const validateEditLines = (): string | null => {
    if (!bill) return "Bill not loaded";
    let hasPositiveQty = false;
    for (let i = 0; i < bill.lines.length; i++) {
      const bl = bill.lines[i];
      const lf = lines[i];
      const bt = getBagType(String(bl.bag_type_id));
      const qty = orderedQtyKg(lf, bt);
      const floor = Number(bl.delivered_quantity_kg ?? 0);
      if (qty < 0) return `Quantity cannot be negative on line ${i + 1}`;
      if (qty > 0) hasPositiveQty = true;
      if (qty < floor) {
        return `Cannot reduce qty below delivered (${formatQtyKg(floor)}); return first`;
      }
      if (Number(lf.rate_per_kg) < 0) return "Enter rate per kg on each line";
    }
    if (!hasPositiveQty) return "At least one line must have quantity greater than zero";
    const totalsErr = validateTotals();
    if (totalsErr) return totalsErr;
    if (totals.finalPayable < amountPaid) {
      return "Final payable cannot be less than amount already paid";
    }
    return null;
  };

  const totalsInvalid =
    Number(adjustment) < 0 || totals.finalPayable < 0 || (editMode && totals.finalPayable < amountPaid);

  const submitEdit = async () => {
    if (!bill) return;
    setError("");
    const lineErr = validateEditLines();
    if (lineErr) {
      setError(lineErr);
      clearIdemKey();
      return;
    }
    await guardedSubmit(async () => {
      try {
        const updated = await api.patch<Bill>(`/api/bills/${bill.id}`, buildEditPayload(), {
          headers: idempotencyHeadersOptionalAuth(idemKey()),
        });
        clearIdemKey();
        setBill(updated);
        navigate(listPath);
      } catch (err) {
        setError(errMsg(err));
      }
    });
  };

  const postCreateBill = async (authorizationPassword?: string) => {
    await api.post<Bill>("/api/bills", buildCreatePayload(), {
      headers: idempotencyHeadersOptionalAuth(idemKey(), authorizationPassword),
    });
    clearIdemKey();
    navigate(listPath);
  };

  const submitCreate = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!headerReady) {
      setError(isSales ? "Select customer and location" : "Select customer");
      clearIdemKey();
      return;
    }
    if (billDate > maxBillDate) {
      setError("Bill date cannot be in the future");
      clearIdemKey();
      return;
    }
    const lineErr = validateCreateLines();
    if (lineErr) {
      setError(lineErr);
      clearIdemKey();
      return;
    }
    const totalsErr = validateTotals();
    if (totalsErr) {
      setError(totalsErr);
      clearIdemKey();
      return;
    }
    if (stockWarnings.length > 0) {
      setError(stockWarnings[0]);
      clearIdemKey();
      return;
    }
    if (isBackdatedDate(billDate)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }
    await guardedSubmit(async () => {
      try {
        await postCreateBill();
      } catch (err) {
        setError(errMsg(err));
      }
    });
  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    await guardedSubmit(async () => {
      try {
        await postCreateBill(authorizationPassword);
        setBackdateAuthOpen(false);
      } catch (err) {
        const msg = errMsg(err);
        if (isAuthPasswordError(msg)) {
          setBackdateAuthError(msg);
        } else {
          setError(msg);
          setBackdateAuthOpen(false);
        }
        throw err;
      }
    });
  };

  const renderCreateLine = (line: LineForm, idx: number) => {
    const owner = stockOwnerFilter(line.stock_source, header.customer_id);
    const scopedStock = isSales ? filterStockForOwner(stock, owner) : stock;
    const productOptions = isSales ? productsFromStock(scopedStock) : [];
    const brandOptions = isSales ? brandsFromStock(scopedStock, line.product_id) : [];
    const bagOptions = isSales
      ? bagTypesFromStock(scopedStock, line.product_id, line.brand_id)
      : [];
    const inv = isSales
      ? stockRow(
          scopedStock,
          line.product_id,
          line.brand_id,
          line.bag_type_id,
          stockOwnerFilter(line.stock_source, header.customer_id)
        )
      : undefined;
    const bt = getBagType(line.bag_type_id);
    const s1 = Boolean(line.product_id);
    const s2 = s1 && Boolean(line.brand_id);
    const s3 = s2 && Boolean(line.bag_type_id);
    const s4 = s3 && line.rate_per_kg !== "" && Number(line.rate_per_kg) >= 0;
    const lineStockLines = lines.map((l) => ({
      bag_count: l.ordered_bags,
      loose_kg: l.ordered_loose_kg,
    }));
    const sameBucket = (i: number) =>
      lines[i].product_id === line.product_id &&
      lines[i].brand_id === line.brand_id &&
      lines[i].bag_type_id === line.bag_type_id &&
      lines[i].stock_source === line.stock_source;
    const reservedEarlier = reservedStockFromEarlierLines(bt, lineStockLines, idx, sameBucket);
    const reservedSiblings = reservedStockFromSiblingLines(bt, lineStockLines, idx, sameBucket);
    const hasEarlierReserved = reservedEarlier.bagCount > 0 || reservedEarlier.looseKg > 0;
    const remainingDisplay =
      inv && bt ? formatRemainingStockAfterReserved(bt, inv, reservedEarlier.bagCount, reservedEarlier.looseKg) : "";
    const exceedMsg = stockExceedsMessageWithReserved(
      bt,
      line.ordered_bags,
      line.ordered_loose_kg,
      inv,
      reservedSiblings.bagCount,
      reservedSiblings.looseKg
    );
    const qtyKg = orderedQtyKg(line, bt);
    const dup = !isSales && isDuplicateLine(lines, idx, isSales);
    const productDisabled =
      !linesEnabled || (isSales && (stockLoading || scopedStock.length === 0));
    const productPlaceholder = !linesEnabled
      ? isSales
        ? "Select location first"
        : "Select customer first"
      : isSales && scopedStock.length === 0
        ? line.stock_source === "job_work"
          ? "No job work stock for this customer at this location"
          : "No owned stock at this location"
        : "Select product";
    const cascade = (
      label: string,
      value: string,
      disabled: boolean,
      ph: string,
      opts: { id: number; label: string }[],
      onPick: (v: string) => void
    ) => (
      <label key={label}>
        {label}
        <select value={value} disabled={disabled} onChange={(e) => onPick(e.target.value)}>
          <option value="">{ph}</option>
          {opts.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    );
    const purchaseProductField = (
      <label key="product">
        Product
        <AsyncSearchCombobox
          value={line.product_id ? Number(line.product_id) : null}
          onChange={(id) =>
            updateLine(idx, {
              ...resetLineFrom(line, "product"),
              product_id: id != null ? String(id) : "",
            })
          }
          searchFn={searchProducts}
          placeholder="Search product…"
          emptyText="No matching product"
          disabled={!linesEnabled}
        />
      </label>
    );
    const purchaseBrandField = (
      <label key="brand">
        Brand
        <AsyncSearchCombobox
          value={line.brand_id ? Number(line.brand_id) : null}
          onChange={(id) =>
            updateLine(idx, {
              ...resetLineFrom({ ...line, product_id: line.product_id }, "brand"),
              brand_id: id != null ? String(id) : "",
            })
          }
          searchFn={searchBrands}
          placeholder="Search brand…"
          emptyText="No matching brand"
          disabled={!linesEnabled || !s1}
        />
      </label>
    );
    const purchaseBagTypeField = (
      <label key="bag-type">
        Bag type
        <AsyncSearchCombobox
          value={line.bag_type_id ? Number(line.bag_type_id) : null}
          onChange={(id, opt) => {
            const bagOpt = opt as MasterComboOption | undefined;
            if (bagOpt?.bagType) bagTypeCache.remember(bagOpt.bagType);
            updateLine(idx, {
              ...resetLineFrom({ ...line, brand_id: line.brand_id }, "bag_type"),
              bag_type_id: id != null ? String(id) : "",
            });
          }}
          searchFn={searchBagTypes}
          placeholder="Search bag type…"
          emptyText="No matching bag type"
          disabled={!linesEnabled || !s2}
        />
      </label>
    );

    return (
      <div key={idx} className="bill-form-line line-block" style={{ opacity: linesEnabled ? 1 : 0.55 }}>
        {dup && <p className="error">Duplicate product / brand / bag type on this bill</p>}
        <div className="form-grid">
          {isSales && (
            <label>
              Stock source
              <select
                value={line.stock_source}
                disabled={!linesEnabled}
                onChange={(e) =>
                  updateLine(idx, {
                    ...emptyLine(),
                    stock_source: e.target.value as "owned" | "job_work",
                  })
                }
              >
                <option value="owned">Owned stock</option>
                <option value="job_work">Job work (customer custody)</option>
              </select>
            </label>
          )}
          {isSales &&
            line.stock_source === "job_work" &&
            !stockLoading &&
            headerReady &&
            scopedStock.length === 0 &&
            jobWorkCustodians.length > 0 && (
              <p className="col-span-full text-sm text-amber-800 dark:text-amber-200">
                {selectedCustomerName
                  ? `No job work stock for ${selectedCustomerName} at this location.`
                  : "No job work stock for the selected customer at this location."}{" "}
                Custody stock here belongs to: {jobWorkCustodians.map((c) => c.name).join(", ")} — select
                that customer on the bill.
              </p>
            )}
          {isSales ? (
            <>
              {cascade(
                "Product",
                line.product_id,
                productDisabled,
                productPlaceholder,
                productOptions,
                (v) => updateLine(idx, { ...resetLineFrom(line, "product"), product_id: v })
              )}
              {cascade(
                "Brand",
                line.brand_id,
                !linesEnabled || !s1,
                s1 ? "Select brand" : "Select product first",
                brandOptions,
                (v) =>
                  updateLine(idx, {
                    ...resetLineFrom({ ...line, product_id: line.product_id }, "brand"),
                    brand_id: v,
                  })
              )}
              {cascade(
                "Bag type",
                line.bag_type_id,
                !linesEnabled || !s2,
                s2 ? "Select bag type" : "Select brand first",
                bagOptions,
                (v) => {
                  if (v) void bagTypeCache.ensure(v);
                  updateLine(idx, {
                    ...resetLineFrom({ ...line, brand_id: line.brand_id }, "bag_type"),
                    bag_type_id: v,
                  });
                }
              )}
            </>
          ) : (
            <>
              {purchaseProductField}
              {purchaseBrandField}
              {purchaseBagTypeField}
            </>
          )}
          {isLooseBagType(bt) ? (
            <label>
              Loose kg
              <input
                type="number"
                min="0"
                step="0.001"
                value={line.ordered_loose_kg}
                disabled={!linesEnabled || !s3}
                placeholder="Enter kg"
                onChange={(e) => updateLine(idx, { ...line, ordered_loose_kg: e.target.value, ordered_bags: "" })}
              />
            </label>
          ) : (
            <label>
              {bagsLabel}
              <input
                type="number"
                min="0"
                step="1"
                value={line.ordered_bags}
                disabled={!linesEnabled || !s3}
                placeholder="Enter bags"
                onChange={(e) => updateLine(idx, { ...line, ordered_bags: e.target.value, ordered_loose_kg: "" })}
              />
            </label>
          )}
          <label>
            Rate / kg (₹)
            <input
              type="number"
              min="0"
              step="0.01"
              value={line.rate_per_kg}
              placeholder="Rate per kg"
              disabled={!linesEnabled || !s3}
              onChange={(e) => updateLine(idx, { ...line, rate_per_kg: e.target.value })}
            />
          </label>
        </div>
        {inv && s3 && (
          <div className="stock-hint">
            {hasEarlierReserved ? "Remaining" : "Available"} (
            {line.stock_source === "job_work" ? "job work" : "owned"}): {remainingDisplay}
            {isSales && exceedMsg && (
              <span className="stock-warning"> — {exceedMsg.replace(" — cannot submit", "")}</span>
            )}
          </div>
        )}
        {s4 && qtyKg > 0 && (
          <p className="hint">
            {formatQtyKg(String(qtyKg))} × {formatInr(line.rate_per_kg)}/kg = {formatInr(String(qtyKg * (Number(line.rate_per_kg) || 0)))}
          </p>
        )}
        {linesEnabled && (s1 || s2 || s3) && (
          <button type="button" className="btn" style={{ marginTop: 8 }} onClick={() => updateLine(idx, emptyLine())}>
            Clear line
          </button>
        )}
      </div>
    );
  };

  const renderEditLine = (line: LineForm, idx: number) => {
    const bl = bill?.lines[idx];
    const bt = getBagType(line.bag_type_id);
    const qtyKg = orderedQtyKg(line, bt);
    const floor = Number(bl?.delivered_quantity_kg ?? 0);
    const bagsDelivered = bl?.bags_delivered ?? 0;

    return (
      <div key={idx} className="bill-form-line line-block">
        <p>
          <strong>{bl?.product_name}</strong> · {bl?.brand_name} · {bl?.bag_type_name}
        </p>
        {bl && (
          <p className="hint">
            <span className={statusBadgeClass("delivery", bl.line_delivery_status)}>
              {deliveryStatusLabel(bl.line_delivery_status)}
            </span>
            {" · "}
            Delivered {formatQtyKg(floor)}
            {bagsDelivered > 0 && !isLooseBagType(bt) && ` (${bagsDelivered} bags)`}
          </p>
        )}
        <div className="form-grid">
          {isLooseBagType(bt) ? (
            <label>
              Loose kg
              <input
                type="number"
                min="0"
                step="0.001"
                value={line.ordered_loose_kg}
                placeholder="Enter kg"
                onChange={(e) => updateLine(idx, { ...line, ordered_loose_kg: e.target.value })}
              />
            </label>
          ) : (
            <>
              <label>
                {bagsLabel}
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={line.ordered_bags}
                  placeholder="Enter bags"
                  onChange={(e) => updateLine(idx, { ...line, ordered_bags: e.target.value })}
                />
              </label>
              <label>
                Total ordered qty (kg)
                <input type="text" readOnly value={formatQtyKg(String(qtyKg))} />
              </label>
            </>
          )}
          <label>
            Rate / kg (₹)
            <input
              type="number"
              min="0"
              step="0.01"
              value={line.rate_per_kg}
              placeholder="Rate per kg"
              onChange={(e) => updateLine(idx, { ...line, rate_per_kg: e.target.value })}
            />
          </label>
          <label>
            Bags delivered
            <input type="text" readOnly value={String(bagsDelivered)} />
          </label>
          <label>
            Qty delivered (kg)
            <input type="text" readOnly value={formatQtyKg(floor)} />
          </label>
          <label>
            Delivery status
            <input type="text" readOnly value={deliveryStatusLabel(bl?.line_delivery_status ?? "not_delivered")} />
          </label>
        </div>
        {qtyKg > 0 && qtyKg < floor && (
          <p className="error">Below delivered minimum — return first or increase qty</p>
        )}
        {qtyKg === 0 && floor === 0 && (
          <p className="hint">Set bags/kg to 0 to drop this product from the bill total (line stays for history).</p>
        )}
      </div>
    );
  };

  if (editMode && loading) {
    return <p className="hint">Loading bill…</p>;
  }

  return (
    <>
      <PageHeader
        eyebrow={billType === "sales" ? "Sales bill" : "Purchase bill"}
        title={
          <span className="flex items-center gap-2">
            {editMode && bill ? (
              <span className="v2-mono">{bill.bill_number}</span>
            ) : (
              <span>New bill</span>
            )}
            {!editMode && previewBillNumber && (
              <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700 dark:bg-primary-900/40 dark:text-primary-200">
                preview: <span className="v2-mono">{previewBillNumber}</span>
              </span>
            )}
          </span>
        }
        subtitle={
          editMode
            ? "Edit quantities and rates — customer balance adjusted on save (replacement)."
            : "Fill in header, lines, and totals on one page. Submit to finalize. Stock moves only on fulfillment."
        }
        actions={
          <Link to={listPath}>
            <V13Button variant="secondary" leftIcon={<ArrowLeft className="h-4 w-4" />}>
              Back
            </V13Button>
          </Link>
        }
      />
      {error && (
        <V13Banner tone="danger" className="mb-4">
          {error}
        </V13Banner>
      )}
      {!editMode && stockWarnings.length > 0 && (
        <div className="card card--plain" style={{ borderColor: "var(--return-accent)" }}>
          {stockWarnings.map((w) => (
            <p key={w} className="stock-warning">
              Warning: {w} — you can still submit this bill.
            </p>
          ))}
        </div>
      )}

      <div className="space-y-6">
        <Card>
          <CardHeader title="Bill header" />
          <CardBody className="space-y-4">
            <div className="form-grid bill-form-grid">
              {!editMode && (
                <label>
                  Bill number
                  <input type="text" readOnly value={previewBillNumber || "Auto on submit"} />
                </label>
              )}
              {editMode && bill && (
                <label>
                  Bill number
                  <input type="text" readOnly value={bill.bill_number} />
                </label>
              )}
              {editMode && bill ? (
                <label>
                  Bill date
                  <input type="text" readOnly value={bill.bill_date} />
                </label>
              ) : (
                <label>
                  Bill date
                  <input
                    type="date"
                    value={billDate}
                    max={maxBillDate}
                    onChange={(e) => setBillDate(e.target.value)}
                    required
                  />
                  {isBackdatedDate(billDate) ? (
                    <span className="mt-1 block text-xs text-ink-muted">
                      Past date — authorization password required on save.
                    </span>
                  ) : null}
                </label>
              )}
              <div style={{ gridColumn: "1 / -1" }}>
                {!editMode ? (
                  <FormField label="Customer" required htmlFor="bill-customer">
                    {() => (
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
                        <AsyncSearchCombobox
                          className="min-w-0 flex-1"
                          value={header.customer_id ? Number(header.customer_id) : null}
                          onChange={(id, opt) => {
                            setSelectedCustomerLabel(opt?.label ?? "");
                            handleCustomerChange(id != null ? String(id) : "");
                          }}
                          searchFn={searchCustomers}
                          placeholder="Search name or phone…"
                          emptyText="No matching customer"
                        />
                        <V13Button
                          type="button"
                          variant="secondary"
                          className="shrink-0"
                          leftIcon={<UserPlus className="h-4 w-4" />}
                          onClick={() => setAddCustomerOpen(true)}
                        >
                          Add customer
                        </V13Button>
                      </div>
                    )}
                  </FormField>
                ) : (
                  <label>
                    Customer
                    <input type="text" readOnly value={bill?.customer_name ?? "—"} />
                  </label>
                )}
              </div>
              {isSales && (
                editMode && bill ? (
                  <label>
                    Location
                    <input type="text" readOnly value={bill.location_name ?? "—"} />
                  </label>
                ) : (
                  <FormField label="Location" required>
                    {() => (
                      <AsyncSearchCombobox
                        value={header.location_id ? Number(header.location_id) : null}
                        onChange={(id) => handleLocationChange(id != null ? String(id) : "")}
                        searchFn={searchLocations}
                        placeholder="Search location…"
                        emptyText="No matching location"
                      />
                    )}
                  </FormField>
                )
              )}
            </div>
            {editMode && bill && (
              <p className="text-sm text-ink-muted">
                {billType === "purchase" ? "Credit" : "Debit"} balance after save reflects replacement of this
                bill&apos;s final payable
              </p>
            )}
            {!editMode && isSales && header.location_id && (
              <p className="text-sm text-ink-muted">
                {stockLoading
                  ? "Loading inventory at location…"
                  : stock.length
                    ? `${stock.length} stock row(s) at this location — job work lines show only that customer's custody stock`
                    : "No stock at this location; add inventory first"}
              </p>
            )}
            {!editMode && !isSales && (
              <p className="text-sm text-ink-muted">
                Purchase lines use product, brand, and bag type from masters — stock is added when you receive on fulfillment.
              </p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Line items"
            subtitle={
              !editMode && !headerReady
                ? isSales
                  ? "Select customer and location above first."
                  : "Select a customer above first."
                : "Product → brand → bag type → rate → quantity."
            }
          />
          <CardBody className="space-y-6">
            {!editMode && !headerReady && (
              <p className="text-base text-ink-muted">
                {isSales ? "Confirm customer and location in the header section." : "Select customer in the header section."}
              </p>
            )}
            {!editMode && isSales && headerReady && !stockLoading && !stock.length && (
              <p className="text-base text-ink-muted">No stock at this location; add inventory first</p>
            )}
            {!editMode && lines.map((line, idx) => renderCreateLine(line, idx))}
            {editMode && lines.map((line, idx) => renderEditLine(line, idx))}
            {!editMode && linesEnabled && (
              <V13Button
                type="button"
                variant="secondary"
                leftIcon={<Plus className="h-4 w-4" />}
                onClick={() => setLines([...lines, emptyLine()])}
              >
                Add line
              </V13Button>
            )}
          </CardBody>
        </Card>

        <div className="flex items-center justify-between gap-3 rounded-2xl border border-line/80 bg-surface-subtle/60 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2.5 text-ink">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-200">
              <Package className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm font-semibold text-ink">Products billed</p>
          </div>
          <p className="v2-mono text-2xl font-bold tabular-nums text-ink">{productsBilledCount}</p>
        </div>

        <Card className="border-primary-200/60 bg-gradient-to-br from-primary-50/30 via-surface to-surface dark:border-primary-800/40 dark:from-primary-950/20">
          <CardHeader title="Totals & submit" subtitle="Review discount, adjustment, and final payable." />
          <CardBody className="space-y-6">
            <div className="form-grid bill-form-grid">
              <label>
                Total amount
                <input type="text" readOnly value={formatInr(String(totals.totalAmount))} />
              </label>
              <label>
                Discount %
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={discountPercent}
                  placeholder="0"
                  onChange={(e) => setDiscountPercent(e.target.value)}
                />
              </label>
              <label>
                Adjustment (₹ off)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={adjustment}
                  placeholder="0"
                  onChange={(e) => setAdjustment(e.target.value)}
                />
              </label>
              {totals.discountAmount > 0 && (
                <p className="text-base text-ink-muted">Discount −{formatInr(String(totals.discountAmount))}</p>
              )}
              <label className="totals-final">
                Final payable
                <input
                  type="text"
                  readOnly
                  value={formatInr(String(Math.max(totals.finalPayable, 0)))}
                />
              </label>
              {totals.finalPayable < 0 && (
                <p className="form-error">Final payable cannot be negative — reduce adjustment or discount.</p>
              )}
              {editMode && bill && (
                <>
                  <label>
                    Amount paid
                    <input type="text" readOnly value={formatInr(bill.amount_paid)} />
                  </label>
                  <label>
                    Amount due
                    <input type="text" readOnly value={formatInr(String(amountDue))} />
                  </label>
                </>
              )}
            </div>

            <FormField label="Notes" hint="Optional — shown on bill detail and print.">
              {({ id }) => (
                <Textarea
                  id={id}
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Any notes for this bill…"
                  maxLength={1000}
                />
              )}
            </FormField>

            <div className="flex flex-wrap justify-end gap-3 border-t border-line/60 pt-4">
              {editMode ? (
                bill && (
                  <V13Button
                    type="button"
                    size="lg"
                    disabled={submitDisabled || totalsInvalid}
                    loading={submitting}
                    onClick={submitEdit}
                  >
                    {submitting ? "Saving…" : "Save changes"}
                  </V13Button>
                )
              ) : (
                <V13Button
                  type="button"
                  size="lg"
                  disabled={submitDisabled || totalsInvalid}
                  loading={submitting}
                  onClick={submitCreate}
                >
                  {submitting ? "Saving…" : "Submit bill"}
                </V13Button>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      <AddCustomerDialog
        open={addCustomerOpen}
        onClose={() => setAddCustomerOpen(false)}
        onCreated={handleCustomerCreated}
      />

      <BackdateAuthDialog
        open={backdateAuthOpen}
        onClose={() => setBackdateAuthOpen(false)}
        onConfirm={confirmBackdateAuth}
        dateLabel={billDate}
        authError={backdateAuthError || undefined}
      />
      <ConfirmDialog
        open={pendingCustomerChange != null}
        onClose={() => setPendingCustomerChange(null)}
        onConfirm={() => {
          if (pendingCustomerChange == null) return;
          setLines([emptyLine()]);
          setHeader((h) => ({ ...h, customer_id: pendingCustomerChange }));
          setPendingCustomerChange(null);
        }}
        title="Change customer?"
        description="Changing customer clears all line rows. Continue?"
        confirmLabel="Change customer"
      />
      <ConfirmDialog
        open={pendingLocationChange != null}
        onClose={() => setPendingLocationChange(null)}
        onConfirm={() => {
          if (pendingLocationChange == null) return;
          setLines([emptyLine()]);
          setHeader((h) => ({ ...h, location_id: pendingLocationChange }));
          setPendingLocationChange(null);
        }}
        title="Change location?"
        description="Changing location clears all line rows (each bill is tied to one location). Continue?"
        confirmLabel="Change location"
      />
    </>
  );
}
