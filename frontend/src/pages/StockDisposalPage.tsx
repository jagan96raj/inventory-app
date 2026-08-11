import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { api, idempotencyHeaders, newIdempotencyKey } from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import OperationPageHeader from "../components/OperationPageHeader";
import StockOwnerFields from "../components/operations/StockOwnerFields";
import {
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

export default function StockDisposalPage() {
  const bagTypeCache = useBagTypeCache();
  const [stock, setStock] = useState<StockAtLocation[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);

  const [form, setForm] = useState({
    location_id: "",
    owner_type: "owned" as "owned" | "job_work",
    customer_id: "",
    product_id: "",
    brand_id: "",
    bag_type_id: "",
    ...emptyQtyFields(),
    reason: "",
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
    loadStock(form.location_id);
  }, [form.location_id]);

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
  const canSubmit =
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

  const resetCascade = (step: "location" | "product" | "brand" | "bag_type") => {
    if (step === "location") {
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
          "/api/operations/stock-disposal",
          {
            location_id: Number(form.location_id),
            product_id: Number(form.product_id),
            brand_id: Number(form.brand_id),
            bag_type_id: Number(form.bag_type_id),
            bag_count: isLooseBagType(selectedBagType) ? 0 : parseBagCount(form.bag_count),
            loose_kg: isLooseBagType(selectedBagType) ? parseLooseKg(form.loose_kg) : 0,
            owner_type: form.owner_type,
            customer_id:
              form.owner_type === "job_work" && form.customer_id ? Number(form.customer_id) : null,
            reason: form.reason.trim() || null,
            notes: form.notes.trim() || null,
          },
          { headers: idempotencyHeaders(idemKeyRef.current!) }
        );
        idemKeyRef.current = null;
        setSuccess("Stock disposal recorded.");
        const loc = form.location_id;
        setForm({
          location_id: loc,
          owner_type: form.owner_type,
          customer_id: form.customer_id,
          product_id: "",
          brand_id: "",
          bag_type_id: "",
          ...emptyQtyFields(),
          reason: "",
          notes: "",
        });
        loadStock(loc);
      } catch (err) {
        setError(errMsg(err));
      }
    });
  };

  return (
    <>
      <OperationPageHeader
        title="Stock disposal"
        subtitle="Write off damaged or unusable stock — subtracts inventory only"
        formTo="/operations/stock-disposal"
        historyTo="/histories/stock-disposal"
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

      <Banner tone="warning" className="mb-4" title="Permanent write-off">
        Disposed stock is removed from inventory and cannot be recovered. Double-check quantities before submitting.
      </Banner>

      <Card className="overflow-hidden border-danger-200/50 dark:border-danger-800/40">
        <CardHeader
          title="Record disposal"
          subtitle="Select the stock to write off and optionally note the reason."
        />
        <form onSubmit={submit}>
          <CardBody className="space-y-6">
            <OperationSection
              step={1}
              tone="danger"
              title="Stock to dispose"
              subtitle="Location, product, brand, bag type, and quantity."
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <FormField label="Location" required>
                  {() => (
                    <AsyncSearchCombobox
                      value={form.location_id ? Number(form.location_id) : null}
                      onChange={(id) => {
                        setForm({ ...form, location_id: id != null ? String(id) : "" });
                        resetCascade("location");
                      }}
                      searchFn={searchLocations}
                      placeholder="Search location…"
                      emptyText="No matching location"
                    />
                  )}
                </FormField>
                <StockOwnerFields
                  value={{ owner_type: form.owner_type, customer_id: form.customer_id }}
                  onChange={(v) => setForm((f) => ({ ...f, ...v }))}
                  onOwnerChange={() => resetCascade("location")}
                />
                <FormField label="Product" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={form.product_id}
                      disabled={!form.location_id}
                      onChange={(e) => {
                        setForm({ ...form, product_id: e.target.value });
                        resetCascade("product");
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
                        resetCascade("brand");
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
                        min={1}
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

            <OperationSection step={2} tone="neutral" title="Reason & details">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <FormField label="Reason">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={form.reason}
                      placeholder="e.g. Damaged bags, moisture loss"
                      onChange={(e) => setForm({ ...form, reason: e.target.value })}
                    />
                  )}
                </FormField>
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
            <div className="flex items-center gap-2 text-sm text-danger-700 dark:text-danger-300">
              <Trash2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              {qtyKg > 0 ? `${formatQtyKg(qtyKg)} will be written off` : "Select stock to dispose"}
            </div>
            <Button
              type="submit"
              variant="danger"
              loading={submitting}
              disabled={submitDisabled || !canSubmit}
              leftIcon={<Trash2 className="h-4 w-4" />}
            >
              {submitting ? "Saving…" : "Submit disposal"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </>
  );
}
