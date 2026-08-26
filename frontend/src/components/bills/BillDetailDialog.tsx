import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Expand,
  Eye,
  IndianRupee,
  Minimize2,
  Pencil,
  Printer,
  Receipt,
} from "lucide-react";
import { api, type Bill, type BillListItem } from "../../api/client";
import { billDueAmount } from "../../lib/billAmounts";
import { formatBagsKgLabel, sumOrderedBagsKg } from "../../lib/billQty";
import { formatDate, formatInr, formatQtyKg } from "../../lib/format";
import Modal from "../ui/Modal";
import Button from "../ui/Button";
import IconButton from "../ui/IconButton";
import Badge from "../ui/Badge";
import { PaymentPill } from "../ui/StatusPill";
import Banner from "../ui/Banner";
import { cn } from "../../lib/cn";

function fulfillmentLabel(status: string, isSales: boolean): string {
  const s = status.toLowerCase();
  if (s === "delivered") return isSales ? "Delivered" : "Received";
  if (s === "partial") return "Partial";
  return isSales ? "Not delivered" : "Not received";
}

export default function BillDetailDialog({
  open,
  billId,
  billType,
  listItem,
  onClose,
  onChanged,
}: {
  open: boolean;
  billId: number | null;
  billType: "sales" | "purchase";
  listItem?: BillListItem | null;
  onClose: () => void;
  /** Called when dialog closes so the list can refresh (e.g. after edit/void elsewhere). */
  onChanged?: () => void;
}) {
  const navigate = useNavigate();
  const [bill, setBill] = useState<Bill | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [maximized, setMaximized] = useState(false);

  const base = billType === "sales" ? "/sales-bills" : "/purchase-bills";
  const isSales = billType === "sales";

  useEffect(() => {
    if (!open) {
      setBill(null);
      setError("");
      setMaximized(false);
      return;
    }
    if (billId == null) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .get<Bill>(`/api/bills/${billId}?_=${Date.now()}`)
      .then((b) => {
        if (!cancelled) setBill(b);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, billId]);

  const handleClose = () => {
    onClose();
    onChanged?.();
  };

  const bagsKg = useMemo(() => {
    if (bill?.lines?.length) return sumOrderedBagsKg(bill.lines);
    if (listItem) {
      return {
        bags: Number(listItem.total_ordered_bags) || 0,
        kg: Number(listItem.total_ordered_kg) || 0,
      };
    }
    return { bags: 0, kg: 0 };
  }, [bill, listItem]);

  const due = bill
    ? Number(bill.due_amount ?? bill.amount_due ?? 0) ||
      Math.max(Number(bill.grand_total) - Number(bill.amount_paid), 0)
    : listItem
      ? billDueAmount(listItem)
      : 0;
  const isVoided = bill?.status === "voided";
  const numberLabel = bill?.bill_number ?? listItem?.bill_number ?? "Bill";

  const go = (path: string) => {
    handleClose();
    navigate(path);
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      size={maximized ? "full" : "xl"}
      headerTone="accent"
      headerIcon={<Receipt className="h-5 w-5" />}
      title={<span className="v2-mono">{numberLabel}</span>}
      description={
        bill || listItem
          ? `${(bill ?? listItem)!.customer_name ?? "—"} · ${formatDate((bill ?? listItem)!.bill_date)}`
          : undefined
      }
      headerActions={
        <IconButton
          label={maximized ? "Restore size" : "Maximize"}
          size="sm"
          onClick={() => setMaximized((v) => !v)}
        >
          {maximized ? <Minimize2 /> : <Expand />}
        </IconButton>
      }
      footer={
        <>
          <Button variant="secondary" leftIcon={<Eye className="h-4 w-4" />} onClick={() => go(`${base}/${billId}`)}>
            Open full page
          </Button>
          <Button
            variant="secondary"
            leftIcon={<Pencil className="h-4 w-4" />}
            disabled={isVoided || billId == null}
            onClick={() => billId != null && go(`${base}/${billId}/edit`)}
          >
            Edit
          </Button>
          {due > 0 && !isVoided && (
            <Button
              leftIcon={<IndianRupee className="h-4 w-4" />}
              onClick={() => billId != null && go(`${base}/${billId}/payment`)}
            >
              Pay
            </Button>
          )}
          <Button
            variant="secondary"
            leftIcon={<Printer className="h-4 w-4" />}
            disabled={billId == null}
            onClick={() => {
              if (billId == null) return;
              window.open(`${base}/${billId}/print`, "_blank", "noopener,noreferrer");
            }}
          >
            Print
          </Button>
        </>
      }
    >
      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}
      {loading && !bill ? (
        <p className="text-sm text-ink-muted">Loading bill…</p>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            {(bill || listItem) && (
              <PaymentPill status={(bill ?? listItem)!.payment_status} />
            )}
            {(bill || listItem) && (
              <Badge tone="neutral" size="sm">
                {fulfillmentLabel((bill ?? listItem)!.order_delivery_status, isSales)}
              </Badge>
            )}
            {bill?.status && (
              <Badge tone={isVoided ? "danger" : "info"} size="sm">
                {bill.status}
              </Badge>
            )}
            {isSales && (bill?.location_name || listItem?.location_name) && (
              <span className="text-sm text-ink-muted">
                {bill?.location_name ?? listItem?.location_name}
              </span>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-line/80 bg-surface-subtle/60 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Final payable</p>
              <p className="v2-mono text-lg font-bold text-ink">
                {formatInr(bill?.final_payable ?? bill?.grand_total ?? listItem?.final_payable ?? listItem?.grand_total ?? 0)}
              </p>
            </div>
            <div className="rounded-xl border border-line/80 bg-surface-subtle/60 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Paid</p>
              <p className="v2-mono text-lg font-semibold text-ink">
                {formatInr(bill?.amount_paid ?? listItem?.amount_paid ?? 0)}
              </p>
            </div>
            <div className="rounded-xl border border-line/80 bg-surface-subtle/60 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Due</p>
              <p
                className={cn(
                  "v2-mono text-lg font-semibold",
                  due > 0 ? "text-danger-700 dark:text-danger-300" : "text-ink"
                )}
              >
                {due > 0 ? formatInr(due) : "Settled"}
              </p>
            </div>
            <div className="rounded-xl border border-line/80 bg-surface-subtle/60 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-subtle">Ordered</p>
              <p className="v2-mono text-lg font-semibold text-ink">{formatBagsKgLabel(bagsKg.bags, bagsKg.kg)}</p>
            </div>
          </div>

          {bill?.notes?.trim() && (
            <div className="rounded-xl border border-line/70 bg-amber-50/50 px-4 py-3 dark:bg-amber-950/20">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Notes</p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-ink">{bill.notes.trim()}</p>
            </div>
          )}

          {bill && bill.lines.length > 0 && (
            <div className="overflow-x-auto rounded-2xl border border-line/80">
              <table className="v2-data-table min-w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left">Product</th>
                    <th className="text-right">Qty</th>
                    <th className="text-right">Rate/kg</th>
                    <th className="text-right">Line total</th>
                  </tr>
                </thead>
                <tbody>
                  {bill.lines.map((line) => (
                    <tr key={line.id}>
                      <td>
                        <span className="font-medium text-ink">
                          {line.product_name ?? "—"}
                          {line.brand_name ? ` · ${line.brand_name}` : ""}
                        </span>
                        {line.bag_type_name && (
                          <span className="mt-0.5 block text-ink-muted">{line.bag_type_name}</span>
                        )}
                      </td>
                      <td className="text-right tabular-nums">
                        {line.is_loose
                          ? formatQtyKg(line.ordered_quantity_kg)
                          : `${line.ordered_bags} bags · ${formatQtyKg(line.ordered_quantity_kg)}`}
                      </td>
                      <td className="text-right tabular-nums">{formatInr(line.rate_per_kg)}</td>
                      <td className="text-right font-medium tabular-nums">{formatInr(line.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
