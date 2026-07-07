import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { PackagePlus, Undo2 } from "lucide-react";
import {
  jobWorkApi,
  newIdempotencyKey,
  type BagType,
  type JobWorkFulfillmentLine,
  type JwReturnLocation,
} from "../api/client";
import { useSubmitGuard } from "../hooks/useSubmitGuard";
import { calcPreviewTotalKg, isLooseBagType } from "../lib/bagType";
import { formatQtyKg, localIsoDate, validateDateNotFuture } from "../lib/format";
import { isAuthPasswordError, isBackdatedDate } from "../lib/backdateAuth";
import BusinessDateField from "./ui/BusinessDateField";
import BackdateAuthDialog from "./ui/BackdateAuthDialog";
import { formatJwPrimaryQty, jwNetReceivedQty, jwRemainingReceiveQty } from "../lib/jwQty";
import { searchLocations } from "../lib/masterSearch";
import { parseBagCount, parseLooseKg, PH_BAGS, PH_LOOSE_KG } from "../lib/qtyInput";
import Banner from "./ui/Banner";
import Button from "./ui/Button";
import FormField from "./ui/FormField";
import Input from "./ui/Input";
import Modal from "./ui/Modal";
import NumberInput from "./ui/NumberInput";
import Select from "./ui/Select";
import Textarea from "./ui/Textarea";
import AsyncSearchCombobox from "./ui/AsyncSearchCombobox";
import { toast } from "./ui/Toaster";

export type JobWorkFulfillmentMode = "receive" | "return";

type Props = {
  open: boolean;
  mode: JobWorkFulfillmentMode;
  line: JobWorkFulfillmentLine | null;
  onClose: () => void;
  onSuccess: () => void;
};

const emptyForm = () => ({
  location_id: "",
  bag_count: "",
  loose_kg: "",
  vehicle_no: "",
  notes: "",
  received_date: localIsoDate(),
});

export default function JobWorkFulfillmentActionDialog({ open, mode, line, onClose, onSuccess }: Props) {
  const [form, setForm] = useState(emptyForm());
  const [error, setError] = useState("");
  const [backdateAuthOpen, setBackdateAuthOpen] = useState(false);
  const [backdateAuthError, setBackdateAuthError] = useState("");
  const { submitting, guardedSubmit, submitDisabled } = useSubmitGuard();
  const idemRef = useRef<string | null>(null);

  const isReceive = mode === "receive";
  const returnLocations = line?.return_locations ?? [];

  useEffect(() => {
    if (!open) return;
    idemRef.current = null;
    setError("");
    if (isReceive) {
      setForm(emptyForm());
    } else {
      const defaultLoc = returnLocations.length === 1 ? String(returnLocations[0].location_id) : "";
      setForm({ ...emptyForm(), location_id: defaultLoc });
    }
  }, [open, isReceive, line?.line_id, returnLocations.length]);

  const bagType = useMemo((): BagType | undefined => {
    if (!line) return undefined;
    return {
      id: line.bag_type_id,
      name: line.bag_type_name ?? `Bag type #${line.bag_type_id}`,
      weight_per_bag_kg: line.weight_per_bag_kg ?? "0",
      is_loose: line.is_loose,
    };
  }, [line]);

  const previewKg = calcPreviewTotalKg(bagType, form.bag_count, form.loose_kg);

  const selectedReturnLocation = useMemo((): JwReturnLocation | undefined => {
    if (isReceive || !form.location_id) return undefined;
    return returnLocations.find((loc) => String(loc.location_id) === form.location_id);
  }, [form.location_id, isReceive, returnLocations]);

  const saveFulfillment = async (authorizationPassword?: string) => {
    if (!line || !idemRef.current) return;
    const bags = isLooseBagType(bagType) ? 0 : parseBagCount(form.bag_count);
    const loose = isLooseBagType(bagType) ? parseLooseKg(form.loose_kg) : 0;
    if (isReceive) {
      await jobWorkApi.receive(
        {
          line_id: line.line_id,
          location_id: Number(form.location_id),
          bag_count: bags,
          loose_kg: loose,
          vehicle_no: form.vehicle_no.trim() || null,
          notes: form.notes.trim() || null,
          received_date: form.received_date,
        },
        idemRef.current,
        authorizationPassword
      );
      toast.success("Material received");
    } else {
      await jobWorkApi.returnToCustomer(
        {
          line_id: line.line_id,
          location_id: Number(form.location_id),
          bag_count: bags,
          loose_kg: loose,
          notes: form.notes.trim() || null,
          received_date: form.received_date,
        },
        idemRef.current,
        authorizationPassword
      );
      toast.success("Returned to customer");
    }
    idemRef.current = null;
    onSuccess();
    onClose();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!line) return;
    if (!form.location_id) {
      setError(isReceive ? "Select a location" : "No return location available");
      return;
    }
    if (previewKg <= 0) {
      setError("Enter a quantity greater than zero");
      return;
    }
    if (!isReceive && selectedReturnLocation) {
      const bags = isLooseBagType(bagType) ? 0 : parseBagCount(form.bag_count);
      const loose = isLooseBagType(bagType) ? parseLooseKg(form.loose_kg) : 0;
      if (isLooseBagType(bagType)) {
        if (loose > Number(selectedReturnLocation.returnable_loose_kg)) {
          setError(`Cannot return more than ${formatQtyKg(selectedReturnLocation.returnable_loose_kg)} at this location`);
          return;
        }
      } else if (bags > selectedReturnLocation.returnable_bags) {
        setError(`Cannot return more than ${selectedReturnLocation.returnable_bags} bag(s) at this location`);
        return;
      }
    }
    if (!idemRef.current) idemRef.current = newIdempotencyKey();
    const dateError = validateDateNotFuture(form.received_date);
    if (dateError) {
      setError(dateError);
      return;
    }
    if (isBackdatedDate(form.received_date)) {
      setBackdateAuthError("");
      setBackdateAuthOpen(true);
      return;
    }
    setError("");
    await guardedSubmit(async () => {
      try {
        await saveFulfillment();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save");
      }
    });
  };

  const confirmBackdateAuth = async (authorizationPassword: string) => {
    setBackdateAuthError("");
    await guardedSubmit(async () => {
      try {
        await saveFulfillment(authorizationPassword);
        setBackdateAuthOpen(false);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not save";
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

  const locationLocked = !isReceive && returnLocations.length === 1;
  const noReturnLocations = !isReceive && returnLocations.length === 0;

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title={isReceive ? "Receive job work material" : "Return to customer"}
      description={
        line
          ? `${line.product_name} · ${line.brand_name} · ${line.bag_type_name}`
          : undefined
      }
      size="md"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="jw-fulfillment-action"
            loading={submitting}
            disabled={submitDisabled || noReturnLocations}
            leftIcon={isReceive ? <PackagePlus className="h-4 w-4" /> : <Undo2 className="h-4 w-4" />}
          >
            {isReceive ? "Receive" : "Return"}
          </Button>
        </div>
      }
    >
      <form id="jw-fulfillment-action" onSubmit={submit} className="space-y-4">
        {error && <Banner tone="danger">{error}</Banner>}
        {noReturnLocations && (
          <Banner tone="warning">No stock at received locations to return.</Banner>
        )}
        {line && (
          <p className="text-sm text-ink-muted">
            {isReceive ? "Remaining to receive" : "Received (net)"}:{" "}
            <span className="v2-mono font-semibold text-ink">
              {formatJwPrimaryQty(
                isReceive ? jwRemainingReceiveQty(line) : jwNetReceivedQty(line)
              )}
            </span>
          </p>
        )}
        <BusinessDateField
          value={form.received_date}
          onChange={(received_date) => setForm((f) => ({ ...f, received_date }))}
        />
        {isReceive ? (
          <FormField label="Location" required>
            {() => (
              <AsyncSearchCombobox
                value={form.location_id ? Number(form.location_id) : null}
                onChange={(id) => setForm({ ...form, location_id: id != null ? String(id) : "" })}
                searchFn={searchLocations}
                placeholder="Search location…"
                emptyText="No matching location"
              />
            )}
          </FormField>
        ) : locationLocked ? (
          <FormField label="Return from location" required>
            {({ id }) => (
              <Input
                id={id}
                readOnly
                value={returnLocations[0]?.location_name ?? `Location #${returnLocations[0]?.location_id}`}
              />
            )}
          </FormField>
        ) : (
          <FormField label="Return from location" required hint="Only locations where material was received.">
            {({ id }) => (
              <Select
                id={id}
                value={form.location_id}
                onChange={(e) => setForm({ ...form, location_id: e.target.value })}
                required
                disabled={noReturnLocations}
              >
                <option value="">Choose location</option>
                {returnLocations.map((loc) => (
                  <option key={loc.location_id} value={loc.location_id}>
                    {loc.location_name ?? `Location #${loc.location_id}`}
                    {loc.returnable_bags > 0
                      ? ` · ${loc.returnable_bags} bags`
                      : ` · ${formatQtyKg(loc.returnable_kg)}`}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
        )}
        {selectedReturnLocation && (
          <p className="text-sm text-ink-muted">
            Available at this location:{" "}
            <span className="v2-mono font-semibold text-ink">
              {isLooseBagType(bagType)
                ? formatQtyKg(selectedReturnLocation.returnable_loose_kg)
                : `${selectedReturnLocation.returnable_bags} bags · ${formatQtyKg(selectedReturnLocation.returnable_kg)}`}
            </span>
          </p>
        )}
        {bagType && !isLooseBagType(bagType) && (
          <FormField label="Bags" required>
            {({ id }) => (
              <NumberInput
                id={id}
                min={0}
                step={1}
                placeholder={PH_BAGS}
                value={form.bag_count}
                onChange={(e) => setForm({ ...form, bag_count: e.target.value, loose_kg: "" })}
              />
            )}
          </FormField>
        )}
        {bagType && isLooseBagType(bagType) && (
          <FormField label="Loose kg" required>
            {({ id }) => (
              <NumberInput
                id={id}
                min={0}
                step="0.001"
                suffix="kg"
                placeholder={PH_LOOSE_KG}
                value={form.loose_kg}
                onChange={(e) => setForm({ ...form, loose_kg: e.target.value, bag_count: "" })}
              />
            )}
          </FormField>
        )}
        {previewKg > 0 && (
          <p className="text-sm text-ink-muted">
            Quantity: <span className="v2-mono font-semibold text-ink">{formatQtyKg(previewKg)}</span>
          </p>
        )}
        {isReceive && (
          <FormField label="Vehicle no.">
            {({ id }) => (
              <Input id={id} value={form.vehicle_no} onChange={(e) => setForm({ ...form, vehicle_no: e.target.value })} />
            )}
          </FormField>
        )}
        <FormField label="Notes">
          {({ id }) => (
            <Textarea id={id} rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          )}
        </FormField>
      </form>
    </Modal>
    <BackdateAuthDialog
      open={backdateAuthOpen}
      onClose={() => setBackdateAuthOpen(false)}
      onConfirm={confirmBackdateAuth}
      dateLabel={form.received_date}
      authError={backdateAuthError || undefined}
    />
    </>
  );
}
