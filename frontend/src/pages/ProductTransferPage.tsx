import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { api, idempotencyHeaders, newIdempotencyKey } from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import OperationPageHeader from "../components/OperationPageHeader";
import StockOwnerFields from "../components/operations/StockOwnerFields";
import {
  LocationFlowHint,
  OperationSection,
  QtyPreview,
  StockAvailabilityHint,
} from "../components/operations/OperationFormBlocks";
import Banner from "../components/ui/Banner";
import Button from "../components/ui/Button";
import FormField from "../components/ui/FormField";
import Input from "../components/ui/Input";
import NumberInput from "../components/ui/NumberInput";
import Select from "../components/ui/Select";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import { Card, CardBody, CardFooter, CardHeader } from "../components/ui/Card";
import { calcPreviewTotalKg, isLooseBagType } from "../lib/bagType";
import { formatQtyKg } from "../lib/format";
import { stockExceedsMessage } from "../lib/stockWarning";
import {
  clearQtyOnBagTypeChange,
  emptyQtyFields,
  PH_BAGS,
  PH_LOOSE_KG,
  parseBagCount,
  parseLooseKg,
} from "../lib/qtyInput";
import { searchLocations } from "../lib/masterSearch";
import {
  bagTypesFromStock,
  brandsFromStock,
  filterStockForOwner,
  productsFromStock,
  stockOwnerFilter,
  stockRow,
  type StockAtLocation,
} from "../lib/stockAtLocation";

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Error";
}

export default function ProductTransferPage() {
  const bagTypeCache = useBagTypeCache();
  const [stock, setStock] = useState<StockAtLocation[]>([]);
  const [fromLocationLabel, setFromLocationLabel] = useState("");
  const [toLocationLabel, setToLocationLabel] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);

  const [form, setForm] = useState({
    from_location_id: "",
    to_location_id: "",
    owner_type: "owned" as "owned" | "job_work",
    customer_id: "",
    product_id: "",
    brand_id: "",
    bag_type_id: "",
    ...emptyQtyFields(),
    notes: "",
  });

  const loadStock = (locationId: string) => {
    if (!locationId) {
      setStock([]);
      return;
    }
    api
      .get<StockAtLocation[]>(`/api/inventory/stock-at-location?location_id=${locationId}`)
      .then(setStock)
      .catch(() => setStock([]));
  };

  useEffect(() => {
    loadStock(form.from_location_id);
  }, [form.from_location_id]);

  const ownerFilter = useMemo(
    () => stockOwnerFilter(form.owner_type, form.customer_id),
    [form.owner_type, form.customer_id]
  );
  const filteredStock = useMemo(
    () => filterStockForOwner(stock, ownerFilter),
    [stock, ownerFilter]
  );

  const productOptions = useMemo(() => productsFromStock(filteredStock), [filteredStock]);
  const brandOptions = useMemo(() => brandsFromStock(filteredStock, form.product_id), [filteredStock, form.product_id]);
  const bagTypeOptions = useMemo(
    () => bagTypesFromStock(filteredStock, form.product_id, form.brand_id),
    [filteredStock, form.product_id, form.brand_id]
  );

  const selectedBagType = bagTypeCache.get(form.bag_type_id);
  const stockLine = stockRow(
    filteredStock,
    form.product_id,
    form.brand_id,
    form.bag_type_id,
    ownerFilter
  );
  const qtyKg = calcPreviewTotalKg(selectedBagType, form.bag_count, form.loose_kg);
  const stockWarning = useMemo(
    () => stockExceedsMessage(selectedBagType, form.bag_count, form.loose_kg, stockLine),
    [selectedBagType, form.bag_count, form.loose_kg, stockLine]
  );

  const locationsDiffer =
    form.from_location_id && form.to_location_id && form.from_location_id !== form.to_location_id;
  const canSubmit =
    locationsDiffer &&
    qtyKg > 0 &&
    Boolean(form.bag_type_id) &&
    !stockWarning &&
    (form.owner_type !== "job_work" || Boolean(form.customer_id));

  const availableText =
    stockLine && selectedBagType
      ? isLooseBagType(selectedBagType)
        ? formatQtyKg(stockLine.loose_kg)
        : `${stockLine.bag_count} bags (${formatQtyKg(stockLine.total_quantity_kg)})`
      : undefined;

  const resetFromCascade = (step: "from_location" | "product" | "brand" | "bag_type") => {
    if (step === "from_location") {
      setForm((f) => ({
        ...f,
        product_id: "",
        brand_id: "",
        bag_type_id: "",
        ...emptyQtyFields(),
      }));
    } else if (step === "product") {
      setForm((f) => ({ ...f, brand_id: "", bag_type_id: "", ...emptyQtyFields() }));
    } else if (step === "brand") {
      setForm((f) => ({ ...f, bag_type_id: "", ...emptyQtyFields() }));
    } else {
      setForm((f) => ({ ...f, ...emptyQtyFields() }));
    }
  };

  const onBagTypeChange = (bagTypeId: string) => {
    setForm((f) => ({
      ...f,
      bag_type_id: bagTypeId,
      ...clearQtyOnBagTypeChange(),
    }));
    void bagTypeCache.ensure(bagTypeId);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    setError("");
    setSuccess("");
    await guardedSubmit(async () => {
      try {
        await api.post(
          "/api/operations/product-transfer",
          {
            product_id: Number(form.product_id),
            brand_id: Number(form.brand_id),
            bag_type_id: Number(form.bag_type_id),
            from_location_id: Number(form.from_location_id),
            to_location_id: Number(form.to_location_id),
            bag_count: isLooseBagType(selectedBagType) ? 0 : parseBagCount(form.bag_count),
            loose_kg: isLooseBagType(selectedBagType) ? parseLooseKg(form.loose_kg) : 0,
            owner_type: form.owner_type,
            customer_id:
              form.owner_type === "job_work" && form.customer_id ? Number(form.customer_id) : null,
            notes: form.notes.trim() || null,
          },
          { headers: idempotencyHeaders(idemKeyRef.current!) }
        );
        idemKeyRef.current = null;
        setSuccess("Product transfer recorded.");
        const fromLoc = form.from_location_id;
        setForm({
          from_location_id: fromLoc,
          to_location_id: "",
          owner_type: form.owner_type,
          customer_id: form.customer_id,
          product_id: "",
          brand_id: "",
          bag_type_id: "",
          ...emptyQtyFields(),
          notes: "",
        });
        loadStock(fromLoc);
      } catch (err) {
        setError(errMsg(err));
      }
    });
  };

  return (
    <>
      <OperationPageHeader
        title="Product transfer"
        subtitle="Move stock between locations — same product, brand and bag type"
        formTo="/operations/product-transfer"
        historyTo="/histories/product-transfer"
        mode="form"
      />

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

      <Card className="overflow-hidden">
        <CardHeader
          title="Record transfer"
          subtitle="Stock leaves the source godown and appears at the destination with the same product details."
        />
        <form onSubmit={submit}>
          <CardBody className="space-y-6">
            <OperationSection
              step={1}
              tone="primary"
              title="Locations"
              subtitle="Choose where stock is moving from and to."
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField label="From location" required>
                  {() => (
                    <AsyncSearchCombobox
                      value={form.from_location_id ? Number(form.from_location_id) : null}
                      onChange={(id, opt) => {
                        setForm({ ...form, from_location_id: id != null ? String(id) : "" });
                        setFromLocationLabel(opt?.label ?? "");
                        resetFromCascade("from_location");
                      }}
                      searchFn={searchLocations}
                      placeholder="Search source location…"
                      emptyText="No matching location"
                      initialLabel={fromLocationLabel || undefined}
                    />
                  )}
                </FormField>
                <FormField label="To location" required>
                  {() => (
                    <AsyncSearchCombobox
                      value={form.to_location_id ? Number(form.to_location_id) : null}
                      onChange={(id, opt) => {
                        setForm({ ...form, to_location_id: id != null ? String(id) : "" });
                        setToLocationLabel(opt?.label ?? "");
                      }}
                      searchFn={searchLocations}
                      placeholder="Search destination…"
                      emptyText="No matching location"
                      initialLabel={toLocationLabel || undefined}
                    />
                  )}
                </FormField>
              </div>
              <LocationFlowHint
                fromName={fromLocationLabel || undefined}
                toName={toLocationLabel || undefined}
                valid={Boolean(locationsDiffer)}
              />
            </OperationSection>

            <OperationSection
              step={2}
              tone="violet"
              title="Stock details"
              subtitle="Product, brand, bag type, and quantity to move."
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <StockOwnerFields
                  value={{ owner_type: form.owner_type, customer_id: form.customer_id }}
                  onChange={(v) => setForm((f) => ({ ...f, ...v }))}
                  onOwnerChange={() => resetFromCascade("from_location")}
                />
                <FormField label="Product" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={form.product_id}
                      disabled={!form.from_location_id}
                      onChange={(e) => {
                        setForm({ ...form, product_id: e.target.value });
                        resetFromCascade("product");
                      }}
                      required
                    >
                      <option value="">Select product</option>
                      {productOptions.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Brand" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={form.brand_id}
                      disabled={!form.product_id}
                      onChange={(e) => {
                        setForm({ ...form, brand_id: e.target.value });
                        resetFromCascade("brand");
                      }}
                      required
                    >
                      <option value="">Select brand</option>
                      {brandOptions.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                <FormField label="Bag type" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={form.bag_type_id}
                      disabled={!form.brand_id}
                      onChange={(e) => onBagTypeChange(e.target.value)}
                      required
                    >
                      <option value="">Select bag type</option>
                      {bagTypeOptions.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                {selectedBagType && !isLooseBagType(selectedBagType) && (
                  <FormField label="Bags" required>
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0}
                        step={1}
                        max={stockLine?.bag_count ?? undefined}
                        value={form.bag_count}
                        placeholder={PH_BAGS}
                        onChange={(e) => setForm({ ...form, bag_count: e.target.value, loose_kg: "" })}
                        required
                      />
                    )}
                  </FormField>
                )}
                {selectedBagType && isLooseBagType(selectedBagType) && (
                  <FormField label="Loose kg" required>
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0.001}
                        step="0.001"
                        suffix="kg"
                        max={stockLine ? Number(stockLine.loose_kg) : undefined}
                        value={form.loose_kg}
                        placeholder={PH_LOOSE_KG}
                        onChange={(e) => setForm({ ...form, loose_kg: e.target.value, bag_count: "" })}
                        required
                      />
                    )}
                  </FormField>
                )}
                {qtyKg > 0 && <QtyPreview kg={qtyKg} />}
              </div>
              <StockAvailabilityHint available={availableText} warning={stockWarning} />
            </OperationSection>

            <OperationSection step={3} tone="neutral" title="Details">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField label="Notes">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={form.notes}
                      placeholder="Optional note"
                      onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    />
                  )}
                </FormField>
              </div>
            </OperationSection>
          </CardBody>
          <CardFooter className="sticky bottom-0 z-20 flex flex-col gap-3 border-t border-line/60 bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <ArrowLeftRight className="h-4 w-4 shrink-0" aria-hidden="true" />
              {qtyKg > 0 ? `${formatQtyKg(qtyKg)} will transfer` : "Select stock and quantity"}
            </div>
            <Button type="submit" loading={submitting} disabled={submitDisabled || !canSubmit}>
              {submitting ? "Saving…" : "Submit transfer"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </>
  );
}
