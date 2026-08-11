import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapPin, RotateCcw, Truck } from "lucide-react";
import { api, EXPECTED_BILL_VERSION_HEADER, idempotencyHeadersOptionalAuth, newIdempotencyKey } from "../api/client";
import { isAuthPasswordError, isBackdatedDate } from "../lib/backdateAuth";
import BackdateAuthDialog from "./ui/BackdateAuthDialog";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { calcPreviewTotalKg } from "../lib/bagType";
import { formatQtyKg, localIsoDate, validateDateNotFuture } from "../lib/format";
import BusinessDateField from "./ui/BusinessDateField";
import {
  deliverExceedsRemainingMessage,
  returnExceedsMessage,
  stockExceedsMessage,
} from "../lib/stockWarning";
import type { StockAtLocation } from "../lib/stockAtLocation";
import { cn } from "../lib/cn";
import {
  FulfillmentContextCard,
  FulfillmentParentEntryCard,
  FulfillmentReceiveEntryPicker,
  type ReceiveEntry,
} from "./FulfillmentActionPanels";
import Modal from "./ui/Modal";
import Button from "./ui/Button";
import Banner from "./ui/Banner";
import FormField from "./ui/FormField";
import Input from "./ui/Input";
import NumberInput from "./ui/NumberInput";
import AsyncSearchCombobox from "./ui/AsyncSearchCombobox";
import { searchLocations } from "../lib/masterSearch";
import Skeleton from "./ui/Skeleton";

export type FulfillmentActionMode = "deliver" | "return";

type FulfillmentLineDetail = {
  line_id: number;
  bill_id: number;
  bill_version: number;
  bill_number: string;
  bill_type: string;
  customer_name: string;
  location_id?: number | null;
  location_name?: string | null;
  bill_location_id?: number | null;
  bill_location_name?: string | null;
  parent_entry_id?: number | null;
  parent_entry?: ReceiveEntry | null;
  returnable_kg?: string;
  returnable_bags?: number;
  return_deliver_entries?: ReceiveEntry[];
  product_name: string;
  brand_name: string;
  bag_type_name: string;
  is_loose: boolean;
  weight_per_bag_kg: string;
  ordered_bags: number;
  bags_delivered: number;
  ordered_kg: string;
  fulfilled_kg: string;
  remaining_kg: string;
  remaining_bags: number;
  stock_bags: number;
  stock_kg: string;
  line_delivery_status: string;
};

type Props = {
  open: boolean;
  mode: FulfillmentActionMode | null;
  lineId: number | null;
  parentEntryId?: number | null;
  onClose: () => void;
  onSuccess: () => void;
};

const emptyForm = () => ({
  location_id: "",
  bag_count: "",
  loose_kg: "",
  vehicle_no: "",
  fulfilled_date: localIsoDate(),
});

export default function FulfillmentActionDialog({
  open,
  mode,
  lineId,
  parentEntryId: parentEntryIdProp,
  onClose,
  onSuccess,
}: Props) {
  const [line, setLine] = useState<FulfillmentLineDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemKeyRef = useRef<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [pickedParentId, setPickedParentId] = useState<number | null>(null);
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");

  const parentEntryId = pickedParentId ?? parentEntryIdProp ?? null;
  const isDeliver = mode === "deliver";
  const isReturn = mode === "return";

  const loadLine = useCallback(() => {
    if (!open || !lineId) return;
    setLoading(true);
    setError("");
    const qs =
      isReturn && parentEntryId != null ? `?parent_entry_id=${parentEntryId}` : "";
    api
      .get<FulfillmentLineDetail>(`/api/fulfillment/lines/${lineId}${qs}`)
      .then((data) => {
        setLine(data);
        setForm((f) => {
          const next = { ...emptyForm(), vehicle_no: f.vehicle_no };
          if (data.bill_type === "sales" && data.bill_location_id) {
            next.location_id = String(data.bill_location_id);
          }
          return next;
        });
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [open, lineId, isReturn, parentEntryId]);

  useEffect(() => {
    if (!open) {
      setLine(null);
      setError("");
      setForm(emptyForm());
      setPickedParentId(null);
      return;
    }
    loadLine();
  }, [open, loadLine]);

  const isPurchase = line?.bill_type === "purchase";
  const isSales = line?.bill_type === "sales";
  const salesLocationName =
    line?.bill_location_name ??
    line?.location_name ??
    (line?.bill_location_id ? `Location #${line.bill_location_id}` : "");

  const qtyThisEvent = useMemo(() => {
    if (!line) return 0;
    return calcPreviewTotalKg(line, form.bag_count, form.loose_kg);
  }, [line, form]);

  const maxBags = isDeliver
    ? (line?.remaining_bags ?? 0)
    : isPurchase
      ? (line?.returnable_bags ?? 0)
      : (line?.bags_delivered ?? 0);

  const maxKg = isDeliver
    ? Number(line?.remaining_kg ?? 0)
    : isPurchase
      ? Number(line?.returnable_kg ?? 0)
      : Number(line?.fulfilled_kg ?? 0);

  const stockBags = line?.stock_bags ?? 0;
  const locationReady = isPurchase && isDeliver ? Boolean(form.location_id) : isSales && isReturn ? Boolean(form.location_id) : true;

  const salesStockLine = useMemo((): StockAtLocation | undefined => {
    if (!line || !isSales || !isDeliver) return undefined;
    return {
      product_id: 0,
      brand_id: 0,
      bag_type_id: 0,
      bag_count: stockBags,
      loose_kg: line.stock_kg,
      total_quantity_kg: line.stock_kg,
    };
  }, [line, isSales, isDeliver, stockBags]);

  const qtyWarning = useMemo(() => {
    if (!line) return "";
    if (isDeliver) {
      const stock = isSales ? stockExceedsMessage(line, form.bag_count, form.loose_kg, salesStockLine) : "";
      const remaining = deliverExceedsRemainingMessage(line, form.bag_count, form.loose_kg, maxKg, maxBags);
      return stock || remaining;
    }
    return returnExceedsMessage(line, form.bag_count, form.loose_kg, maxKg, maxBags);
  }, [line, isDeliver, isSales, form, salesStockLine, maxKg, maxBags]);

  const showEntryPicker =
    isReturn &&
    isPurchase &&
    parentEntryId == null &&
    (line?.return_deliver_entries?.length ?? 0) > 0;

  const showForm = line && !showEntryPicker;

  const blockSubmit = Boolean(qtyWarning) || qtyThisEvent <= 0 || !locationReady;

  const title = isDeliver
    ? isPurchase
      ? "Receive stock"
      : "Deliver stock"
    : "Return stock";

  const submitLabel = isDeliver
    ? isPurchase
      ? "Save receive"
      : "Save delivery"
    : "Save return";

  const qtyFieldLabel = isDeliver
    ? isPurchase
      ? "How much are you receiving?"
      : "How much are you delivering?"
    : "How much are you returning?";

  const postFulfillment = async (authorizationPassword?: string) => {
    if (!line || !idemKeyRef.current) return;
    await api.post(
      "/api/fulfillment",
      {
        bill_line_id: line.line_id,
        entry_type: isDeliver ? "deliver" : "return",
        quantity_kg: qtyThisEvent,
        bag_count: line.is_loose ? 0 : Number(form.bag_count),
        loose_kg: line.is_loose ? qtyThisEvent : 0,
        location_id:
          isPurchase && isDeliver
            ? Number(form.location_id)
            : isSales && isReturn
              ? Number(form.location_id)
              : undefined,
        parent_entry_id: isReturn && isPurchase ? Number(parentEntryId) : undefined,
        vehicle_no: form.vehicle_no || null,
        expected_version: line.bill_version,
        fulfilled_date: form.fulfilled_date,
      },
      { headers: idempotencyHeadersOptionalAuth(idemKeyRef.current, authorizationPassword) }
    );
    idemKeyRef.current = null;
    onSuccess();
    onClose();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!line || !showForm || blockSubmit) return;

    if (isReturn && isPurchase && parentEntryId == null) {
      setError("Select a prior receive entry to return from");
      idemKeyRef.current = null;
      return;
    }
    if (isReturn && isSales && !form.location_id) {
      setError("Select where returned stock will be stored");
      idemKeyRef.current = null;
      return;
    }
    if (qtyThisEvent > maxKg) {
      setError(
        isDeliver
          ? `Cannot deliver more than ${formatQtyKg(maxKg)} remaining on this line`
          : `Return cannot exceed ${formatQtyKg(maxKg)} for this entry`
      );
      idemKeyRef.current = null;
      return;
    }
    if (!line.is_loose && Number(form.bag_count) > maxBags) {
      setError(
        isDeliver
          ? `Cannot deliver more than ${maxBags} bag(s) remaining`
          : `Cannot return more than ${maxBags} bag(s) for this entry`
      );
      idemKeyRef.current = null;
      return;
    }

    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    const dateError = validateDateNotFuture(form.fulfilled_date);
    if (dateError) {
      setError(dateError);
      idemKeyRef.current = null;
      return;
    }
    if (isBackdatedDate(form.fulfilled_date)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }
    setError("");
    await guardedSubmit(async () => {
      try {
        await postFulfillment();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error");
      }
    });
  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    await guardedSubmit(async () => {
      try {
        await postFulfillment(authorizationPassword);
        setBackdateAuthOpen(false);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Error";
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

  const parentReceivedLabel =
    line?.parent_entry && line.is_loose
      ? formatQtyKg(line.parent_entry.delivered_kg)
      : line?.parent_entry
        ? `${line.parent_entry.delivered_bags} bags · ${formatQtyKg(line.parent_entry.delivered_kg)}`
        : "—";

  const parentReturnableLabel = line?.is_loose
    ? formatQtyKg(line?.returnable_kg ?? "0")
    : `${line?.returnable_bags ?? 0} bags · ${formatQtyKg(line?.returnable_kg ?? "0")}`;

  const modalDescription =
    line && !loading
      ? `${line.bill_number} · ${line.customer_name}`
      : "Loading line details…";

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      size="xl"
      title={title}
      description={modalDescription}
      headerIcon={isReturn ? <RotateCcw className="h-5 w-5" /> : <Truck className="h-5 w-5" />}
      headerTone="accent"
      bodyClassName="space-y-4"
      footer={
        showForm ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-ink-muted">
              {isDeliver ? "Remaining after this" : "Left after this return"}:{" "}
              <span className="v2-mono font-semibold text-ink">
                {line?.is_loose
                  ? formatQtyKg(Math.max(maxKg - qtyThisEvent, 0))
                  : `${Math.max(maxBags - Number(form.bag_count || 0), 0)} bags`}
              </span>
            </p>
            <Button
              type="submit"
              form="fulfillment-action-form"
              loading={submitting}
              disabled={submitDisabled || blockSubmit}
              variant={isReturn ? "danger" : "primary"}
              leftIcon={isReturn ? <RotateCcw className="h-4 w-4" /> : <Truck className="h-4 w-4" />}
              className={cn(isPurchase && isDeliver && "from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700")}
            >
              {submitting ? "Saving…" : submitLabel}
            </Button>
          </div>
        ) : undefined
      }
    >
      {error && (
        <Banner tone="danger" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {qtyWarning && <Banner tone="warning">{qtyWarning}</Banner>}

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      )}

      {!loading && line && isSales && isDeliver && salesLocationName && (
        <div className="rounded-2xl border-2 border-primary-400/70 bg-gradient-to-r from-primary-100/95 via-primary-50/80 to-primary-50/60 px-5 py-4 dark:border-primary-500/50 dark:from-primary-950/55 dark:via-primary-950/35 dark:to-primary-950/25">
          <p className="text-xs font-semibold uppercase tracking-wider text-primary-700 dark:text-primary-300">
            Billed from this location
          </p>
          <p className="mt-1.5 flex items-center gap-2.5 text-xl font-bold text-primary-900 dark:text-primary-50">
            <MapPin className="h-5 w-5 shrink-0 text-primary-600 dark:text-primary-300" aria-hidden="true" />
            {salesLocationName}
          </p>
          {line.stock_kg != null && (
            <p className="mt-2 text-sm text-primary-800/85 dark:text-primary-200/85">
              Stock on hand here:{" "}
              <span className="v2-mono font-semibold">
                {line.is_loose
                  ? formatQtyKg(line.stock_kg)
                  : `${line.stock_bags} bags · ${formatQtyKg(line.stock_kg)}`}
              </span>
            </p>
          )}
        </div>
      )}

      {!loading && showEntryPicker && (
        <FulfillmentReceiveEntryPicker
          isLoose={line.is_loose}
          entries={line.return_deliver_entries!}
          onSelectEntry={(entryId) => setPickedParentId(entryId)}
        />
      )}

      {!loading && showForm && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)] xl:items-start">
          <div className="space-y-4">
            <FulfillmentContextCard
              line={line}
              mode={isDeliver ? "deliver" : "return"}
              salesLocationName={isReturn && isSales ? salesLocationName : undefined}
              highlightBillLocation={isSales && isDeliver}
              returnableKg={isReturn && isPurchase ? line.returnable_kg : undefined}
              returnableBags={isReturn && isPurchase ? line.returnable_bags : undefined}
            />

            {isReturn && isPurchase && line.parent_entry && (
              <FulfillmentParentEntryCard
                locationName={line.location_name ?? "—"}
                fulfilledAt={line.parent_entry.fulfilled_at}
                receivedLabel={parentReceivedLabel}
                returnableLabel={parentReturnableLabel}
              />
            )}
          </div>

          <div className="space-y-4">
            {isReturn && isSales && line.bill_location_name && (
              <div className="rounded-xl border border-primary-200/70 bg-primary-50/50 px-4 py-3 text-sm text-primary-900 dark:border-primary-800/40 dark:bg-primary-950/30 dark:text-primary-100">
                Originally billed from <strong>{line.bill_location_name}</strong>. Choose where returned
                stock is stored — it can differ.
              </div>
            )}

            <form id="fulfillment-action-form" onSubmit={submit} className="space-y-4 rounded-2xl border border-line/80 bg-surface-subtle/40 p-4 sm:p-5">
              <p className="text-base font-semibold text-ink">
                {isDeliver ? (isPurchase ? "Receive details" : "Delivery details") : "Return details"}
              </p>

              <BusinessDateField
                value={form.fulfilled_date}
                onChange={(fulfilled_date) => setForm((f) => ({ ...f, fulfilled_date }))}
              />

              {isPurchase && isDeliver && (
                <FormField label="Receive at location" required hint="Stock will be added here.">
                  {() => (
                    <AsyncSearchCombobox
                      value={form.location_id ? Number(form.location_id) : null}
                      onChange={(id) =>
                        setForm({ ...form, location_id: id != null ? String(id) : "" })
                      }
                      searchFn={searchLocations}
                      placeholder="Search location…"
                      emptyText="No matching location"
                    />
                  )}
                </FormField>
              )}

              {isReturn && isSales && (
                <FormField label="Store return at" required>
                  {() => (
                    <AsyncSearchCombobox
                      value={form.location_id ? Number(form.location_id) : null}
                      onChange={(id) =>
                        setForm({ ...form, location_id: id != null ? String(id) : "" })
                      }
                      searchFn={searchLocations}
                      placeholder="Search location…"
                      emptyText="No matching location"
                      initialLabel={
                        form.location_id && line?.bill_location_id === Number(form.location_id)
                          ? salesLocationName
                          : undefined
                      }
                    />
                  )}
                </FormField>
              )}

              {line.is_loose ? (
                <FormField label={qtyFieldLabel} required hint={`Maximum ${formatQtyKg(maxKg)}.`}>
                  {({ id }) => (
                    <NumberInput
                      id={id}
                      min={0}
                      max={maxKg}
                      step={0.001}
                      suffix="kg"
                      value={form.loose_kg}
                      placeholder="e.g. 500"
                      onChange={(e) => setForm({ ...form, loose_kg: e.target.value, bag_count: "" })}
                      required
                    />
                  )}
                </FormField>
              ) : (
                <FormField
                  label={qtyFieldLabel}
                  required
                  hint={`Maximum ${maxBags} bags (${formatQtyKg(maxKg)}). Kg is calculated automatically.`}
                >
                  {({ id }) => (
                    <NumberInput
                      id={id}
                      min={0}
                      max={maxBags}
                      step={1}
                      value={form.bag_count}
                      placeholder="e.g. 10"
                      onChange={(e) => setForm({ ...form, bag_count: e.target.value, loose_kg: "" })}
                      required
                    />
                  )}
                </FormField>
              )}

              {!line.is_loose && qtyThisEvent > 0 && (
                <div className="rounded-xl border border-line/80 bg-surface px-4 py-3 text-sm">
                  <span className="text-ink-muted">This entry: </span>
                  <span className="v2-mono font-bold text-ink">{formatQtyKg(String(qtyThisEvent))}</span>
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Vehicle number" hint="Optional">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={form.vehicle_no}
                      placeholder="e.g. TN 09 AB 1234"
                      onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })}
                    />
                  )}
                </FormField>
              </div>
            </form>
          </div>
        </div>
      )}
    </Modal>
    <BackdateAuthDialog
      open={backdateAuthOpen}
      onClose={() => setBackdateAuthOpen(false)}
      onConfirm={confirmBackdateAuth}
      dateLabel={form.fulfilled_date}
      authError={backdateAuthError || undefined}
    />
  </>
  );
}
