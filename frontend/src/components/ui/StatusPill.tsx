import Badge, { type Tone } from "./Badge";
import {
  deliveryStatusLabel,
  normalizeDeliveryStatus,
  normalizePaymentStatus,
  paymentStatusLabel,
} from "../../lib/statusLabels";

const PAYMENT_TONE: Record<string, Tone> = {
  paid: "success",
  partial: "warning",
  unpaid: "danger",
};

const DELIVERY_TONE: Record<string, Tone> = {
  delivered: "success",
  partial: "warning",
  not_delivered: "muted",
};

export function PaymentPill({ status }: { status: string }) {
  const norm = normalizePaymentStatus(status);
  return (
    <Badge tone={PAYMENT_TONE[norm] ?? "neutral"} dot size="sm">
      {paymentStatusLabel(norm)}
    </Badge>
  );
}

export function DeliveryPill({ status }: { status: string }) {
  const norm = normalizeDeliveryStatus(status);
  return (
    <Badge tone={DELIVERY_TONE[norm] ?? "neutral"} dot size="sm">
      {deliveryStatusLabel(norm)}
    </Badge>
  );
}

export function VoidPill({ when }: { when?: string | null }) {
  return (
    <Badge tone="danger" size="sm">
      Voided{when ? ` · ${new Date(when).toLocaleDateString("en-IN")}` : ""}
    </Badge>
  );
}
