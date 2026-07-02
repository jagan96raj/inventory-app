import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Package, Plus, Trash2 } from "lucide-react";
import { api, idempotencyHeaders, newIdempotencyKey } from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { useBagTypeCache } from "../hooks/useBagTypeCache";
import OperationPageHeader from "../components/OperationPageHeader";
import StockOwnerFields from "../components/operations/StockOwnerFields";
import {
  OperationBalanceBar,
  OperationLineCard,
  OperationSection,
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
import { searchBagTypes, searchLocations, type MasterComboOption } from "../lib/masterSearch";
import {
  bagTypesFromStock,
  brandsFromStock,
  filterStockForOwner,
  productsFromStock,
  stockOwnerFilter,
  stockRow,
  type StockAtLocation,
} from "../lib/stockAtLocation";

type ToLineForm = {
  key: string;
  to_bag_type_id: string;
  bag_count: string;
  loose_kg: string;
};

const emptyToLine = (): ToLineForm => ({
  key: crypto.randomUUID(),
  to_bag_type_id: "",
  ...emptyQtyFields(),
});

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Error";
}

export default function BagChangePage() {
  const bagTypeCache = useBagTypeCache();
  const [stock, setStock] = useState<StockAtLocation[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);
  const [lossManual, setLossManual] = useState(false);

  const [header, setHeader] = useState({
    location_id: "",
    owner_type: "owned" as "owned" | "job_work",
    customer_id: "",
    product_id: "",
    brand_id: "",
    from_bag_type_id: "",
    from_bag_count: "",
    from_loose_kg: "",
    quantity_loss_kg: "",
    notes: "",
  });
  const [toLines, setToLines] = useState<ToLineForm[]>([emptyToLine()]);

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
    loadStock(header.location_id);
  }, [header.location_id]);

  const ownerFilter = useMemo(
    () => stockOwnerFilter(header.owner_type, header.customer_id),
    [header.owner_type, header.customer_id]
  );
  const filteredStock = useMemo(
    () => filterStockForOwner(stock, ownerFilter),
    [stock, ownerFilter]
  );

  const productOptions = useMemo(() => productsFromStock(filteredStock), [filteredStock]);
  const brandOptions = useMemo(
    () => brandsFromStock(filteredStock, header.product_id),
    [filteredStock, header.product_id]
  );
  const fromBagTypeOptions = useMemo(
    () => bagTypesFromStock(filteredStock, header.product_id, header.brand_id),
    [filteredStock, header.product_id, header.brand_id]
  );

  const fromBagType = bagTypeCache.get(header.from_bag_type_id);
  const fromRow = stockRow(
    filteredStock,
    header.product_id,
    header.brand_id,
    header.from_bag_type_id,
    ownerFilter
  );

  const fromKg = useMemo(
    () => calcPreviewTotalKg(fromBagType, header.from_bag_count, header.from_loose_kg),
    [fromBagType, header.from_bag_count, header.from_loose_kg]
  );

  const toLineKgs = useMemo(
    () =>
      toLines.map((ln) => {
        const bt = bagTypeCache.get(ln.to_bag_type_id);
        return calcPreviewTotalKg(bt, ln.bag_count, ln.loose_kg);
      }),
    [toLines, bagTypeCache.list]
  );

  const toSumKg = useMemo(() => toLineKgs.reduce((a, b) => a + b, 0), [toLineKgs]);

  useEffect(() => {
    if (lossManual) return;
    const loss = Math.max(0, fromKg - toSumKg);
    setHeader((h) => ({ ...h, quantity_loss_kg: loss > 0 ? loss.toFixed(3) : "" }));
  }, [fromKg, toSumKg, lossManual]);

  const lossKg = Number(header.quantity_loss_kg) || 0;
  const fromStockWarning = useMemo(
    () => stockExceedsMessage(fromBagType, header.from_bag_count, header.from_loose_kg, fromRow),
    [fromBagType, header.from_bag_count, header.from_loose_kg, fromRow]
  );
  const balanced = fromKg > 0 && Math.abs(fromKg - (toSumKg + lossKg)) < 0.001;
  const toLinesValid = toLines.every((ln) => {
    const bt = bagTypeCache.get(ln.to_bag_type_id);
    if (!bt) return false;
    const kg = calcPreviewTotalKg(bt, ln.bag_count, ln.loose_kg);
    return kg > 0;
  });

  const availableText =
    fromRow && fromBagType
      ? isLooseBagType(fromBagType)
        ? formatQtyKg(fromRow.loose_kg)
        : `${fromRow.bag_count} bags (${formatQtyKg(fromRow.total_quantity_kg)})`
      : undefined;

  const resetCascade = (step: "location" | "product" | "brand" | "from_bag") => {
    if (step === "location") {
      setHeader((h) => ({
        ...h,
        product_id: "",
        brand_id: "",
        from_bag_type_id: "",
        ...emptyQtyFields(),
      }));
    } else if (step === "product") {
      setHeader((h) => ({
        ...h,
        brand_id: "",
        from_bag_type_id: "",
        ...emptyQtyFields(),
      }));
    } else if (step === "brand") {
      setHeader((h) => ({
        ...h,
        from_bag_type_id: "",
        ...emptyQtyFields(),
      }));
    } else {
      setHeader((h) => ({ ...h, ...emptyQtyFields() }));
    }
    setLossManual(false);
  };

  const onFromBagTypeChange = (bagTypeId: string) => {
    setHeader((h) => ({
      ...h,
      from_bag_type_id: bagTypeId,
      ...clearQtyOnBagTypeChange(),
    }));
    void bagTypeCache.ensure(bagTypeId);
    setLossManual(false);
  };

  const updateToLine = (key: string, patch: Partial<ToLineForm>) => {
    setToLines((lines) =>
      lines.map((ln) => {
        if (ln.key !== key) return ln;
        const next = { ...ln, ...patch };
        if (patch.to_bag_type_id !== undefined) {
          Object.assign(next, clearQtyOnBagTypeChange());
        }
        return next;
      })
    );
    setLossManual(false);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (header.owner_type === "job_work" && !header.customer_id) return;
    if (!balanced || fromStockWarning) return;
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    setError("");
    setSuccess("");
    await guardedSubmit(async () => {
      try {
        await api.post(
          "/api/operations/bag-change",
          {
            location_id: Number(header.location_id),
            product_id: Number(header.product_id),
            brand_id: Number(header.brand_id),
            from_bag_type_id: Number(header.from_bag_type_id),
            from_bag_count: isLooseBagType(fromBagType) ? 0 : parseBagCount(header.from_bag_count),
            from_loose_kg: isLooseBagType(fromBagType) ? parseLooseKg(header.from_loose_kg) : 0,
            quantity_loss_kg: lossKg,
            owner_type: header.owner_type,
            customer_id:
              header.owner_type === "job_work" && header.customer_id
                ? Number(header.customer_id)
                : null,
            notes: header.notes.trim() || null,
            to_lines: toLines.map((ln) => {
              const bt = bagTypeCache.get(ln.to_bag_type_id)!;
              return {
                to_bag_type_id: Number(ln.to_bag_type_id),
                bag_count: isLooseBagType(bt) ? 0 : parseBagCount(ln.bag_count),
                loose_kg: isLooseBagType(bt) ? parseLooseKg(ln.loose_kg) : 0,
              };
            }),
          },
          { headers: idempotencyHeaders(idemKeyRef.current!) }
        );
        idemKeyRef.current = null;
        setSuccess("Bag change recorded.");
        setHeader({
          location_id: header.location_id,
          owner_type: header.owner_type,
          customer_id: header.customer_id,
          product_id: "",
          brand_id: "",
          from_bag_type_id: "",
          from_bag_count: "",
          from_loose_kg: "",
          quantity_loss_kg: "",
          notes: "",
        });
        setToLines([emptyToLine()]);
        setLossManual(false);
        loadStock(header.location_id);
      } catch (err) {
        setError(errMsg(err));
      }
    });
  };

  return (
    <>
      <OperationPageHeader
        title="Bag change"
        subtitle="Repack stock from one bag type into multiple target lines — loss kg must balance"
        formTo="/operations/bag-change"
        historyTo="/histories/bag-change"
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
          title="Record bag change"
          subtitle="Subtract from one bag type and add to one or more target bag types at the same location."
        />
        <form onSubmit={submit}>
          <CardBody className="space-y-6">
            <OperationSection
              step={1}
              tone="primary"
              title="From stock"
              subtitle="Pick location, product, brand, and the bag type you are repacking from."
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <FormField label="Location" required>
                  {() => (
                    <AsyncSearchCombobox
                      value={header.location_id ? Number(header.location_id) : null}
                      onChange={(id) => {
                        setHeader({ ...header, location_id: id != null ? String(id) : "" });
                        resetCascade("location");
                      }}
                      searchFn={searchLocations}
                      placeholder="Search location…"
                      emptyText="No matching location"
                    />
                  )}
                </FormField>
                <StockOwnerFields
                  value={{ owner_type: header.owner_type, customer_id: header.customer_id }}
                  onChange={(v) => setHeader((h) => ({ ...h, ...v }))}
                  onOwnerChange={() => resetCascade("location")}
                />
                <FormField label="Product" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={header.product_id}
                      disabled={!header.location_id}
                      onChange={(e) => {
                        setHeader({ ...header, product_id: e.target.value });
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
                      value={header.brand_id}
                      disabled={!header.product_id}
                      onChange={(e) => {
                        setHeader({ ...header, brand_id: e.target.value });
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
                <FormField label="From bag type" required>
                  {({ id }) => (
                    <Select
                      id={id}
                      value={header.from_bag_type_id}
                      disabled={!header.brand_id}
                      onChange={(e) => onFromBagTypeChange(e.target.value)}
                      required
                    >
                      <option value="">Select bag type</option>
                      {fromBagTypeOptions.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.label}
                        </option>
                      ))}
                    </Select>
                  )}
                </FormField>
                {fromBagType && !isLooseBagType(fromBagType) && (
                  <FormField label="From bags" required>
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0}
                        step={1}
                        max={fromRow?.bag_count ?? undefined}
                        value={header.from_bag_count}
                        placeholder={PH_BAGS}
                        onChange={(e) => {
                          setHeader({ ...header, from_bag_count: e.target.value, from_loose_kg: "" });
                          setLossManual(false);
                        }}
                        required
                      />
                    )}
                  </FormField>
                )}
                {fromBagType && isLooseBagType(fromBagType) && (
                  <FormField label="From loose kg" required>
                    {({ id }) => (
                      <NumberInput
                        id={id}
                        min={0.001}
                        step="0.001"
                        suffix="kg"
                        max={fromRow ? Number(fromRow.loose_kg) : undefined}
                        value={header.from_loose_kg}
                        placeholder={PH_LOOSE_KG}
                        onChange={(e) => {
                          setHeader({ ...header, from_loose_kg: e.target.value, from_bag_count: "" });
                          setLossManual(false);
                        }}
                        required
                      />
                    )}
                  </FormField>
                )}
                {fromKg > 0 && (
                  <FormField label="From quantity kg">
                    {({ id }) => (
                      <Input id={id} readOnly value={fromKg.toFixed(3)} className="v2-mono" />
                    )}
                  </FormField>
                )}
              </div>
              <StockAvailabilityHint available={availableText} warning={fromStockWarning} />
            </OperationSection>

            <OperationSection
              step={2}
              tone="emerald"
              title="To lines"
              subtitle="Add one or more destination bag types. Total kg plus loss must equal from kg."
            >
              <div className="space-y-4">
                {toLines.map((ln, idx) => {
                  const bt = bagTypeCache.get(ln.to_bag_type_id);
                  return (
                    <OperationLineCard
                      key={ln.key}
                      lineLabel={`Line ${idx + 1}`}
                      footer={
                        toLines.length > 1 ? (
                          <div className="mt-3 flex justify-end">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              leftIcon={<Trash2 className="h-4 w-4" />}
                              onClick={() => setToLines((lines) => lines.filter((x) => x.key !== ln.key))}
                            >
                              Remove line
                            </Button>
                          </div>
                        ) : undefined
                      }
                    >
                      <FormField label="To bag type" required>
                        {() => (
                          <AsyncSearchCombobox
                            value={ln.to_bag_type_id ? Number(ln.to_bag_type_id) : null}
                            onChange={(id, opt) => {
                              const masterOpt = opt as MasterComboOption | undefined;
                              if (masterOpt?.bagType) bagTypeCache.remember(masterOpt.bagType);
                              updateToLine(ln.key, {
                                to_bag_type_id: id != null ? String(id) : "",
                              });
                            }}
                            searchFn={searchBagTypes}
                            placeholder="Search bag type…"
                            emptyText="No matching bag type"
                          />
                        )}
                      </FormField>
                      {bt && !isLooseBagType(bt) && (
                        <FormField label="Bags" required>
                          {({ id }) => (
                            <NumberInput
                              id={id}
                              min={0}
                              step={1}
                              value={ln.bag_count}
                              placeholder={PH_BAGS}
                              onChange={(e) =>
                                updateToLine(ln.key, { bag_count: e.target.value, loose_kg: "" })
                              }
                              required
                            />
                          )}
                        </FormField>
                      )}
                      {bt && isLooseBagType(bt) && (
                        <FormField label="Loose kg" required>
                          {({ id }) => (
                            <NumberInput
                              id={id}
                              min={0.001}
                              step="0.001"
                              suffix="kg"
                              value={ln.loose_kg}
                              placeholder={PH_LOOSE_KG}
                              onChange={(e) =>
                                updateToLine(ln.key, { loose_kg: e.target.value, bag_count: "" })
                              }
                              required
                            />
                          )}
                        </FormField>
                      )}
                      <FormField label="Line kg">
                        {({ id }) => (
                          <Input
                            id={id}
                            readOnly
                            value={toLineKgs[idx]?.toFixed(3) ?? "0"}
                            className="v2-mono"
                          />
                        )}
                      </FormField>
                    </OperationLineCard>
                  );
                })}
              </div>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                leftIcon={<Plus className="h-4 w-4" />}
                onClick={() => setToLines((lines) => [...lines, emptyToLine()])}
              >
                Add line
              </Button>
            </OperationSection>

            <OperationSection step={3} tone="violet" title="Loss & balance">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_2fr]">
                <FormField label="Loss kg" hint="Auto-calculated unless you edit manually">
                  {({ id }) => (
                    <NumberInput
                      id={id}
                      min={0}
                      step="0.001"
                      suffix="kg"
                      value={header.quantity_loss_kg}
                      onChange={(e) => {
                        setLossManual(true);
                        setHeader({ ...header, quantity_loss_kg: e.target.value });
                      }}
                    />
                  )}
                </FormField>
                <OperationBalanceBar
                  fromKg={fromKg}
                  toKg={toSumKg}
                  lossKg={lossKg}
                  balanced={balanced}
                />
              </div>
            </OperationSection>

            <OperationSection step={4} tone="neutral" title="Details">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField label="Notes">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={header.notes}
                      placeholder="Optional note"
                      onChange={(e) => setHeader({ ...header, notes: e.target.value })}
                    />
                  )}
                </FormField>
              </div>
            </OperationSection>
          </CardBody>
          <CardFooter className="flex flex-col gap-3 border-t border-line/60 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm text-ink-muted">
              <Package className="h-4 w-4 shrink-0" aria-hidden="true" />
              {balanced ? "Mass balanced" : "Adjust quantities until from = to + loss"}
            </div>
            <Button
              type="submit"
              loading={submitting}
              disabled={
                submitDisabled ||
                !balanced ||
                !toLinesValid ||
                !header.from_bag_type_id ||
                Boolean(fromStockWarning) ||
                (header.owner_type === "job_work" && !header.customer_id)
              }
            >
              Submit bag change
            </Button>
          </CardFooter>
        </form>
      </Card>
    </>
  );
}
