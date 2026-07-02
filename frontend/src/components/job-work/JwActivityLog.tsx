import { Trash2 } from "lucide-react";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import JwQtyCell from "../JwQtyCell";
import { formatDateTime } from "../../lib/format";
import { formatJwPrimaryQty } from "../../lib/jwQty";
import { cn } from "../../lib/cn";

export type JwActivityReceipt = {
  id: number;
  line_id: number;
  location_id: number;
  location_name?: string | null;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  entry_type?: "receive" | "return";
  received_at: string;
  voided_at?: string | null;
  lineLabel?: string;
  is_loose?: boolean;
};

type Props = {
  items: JwActivityReceipt[];
  emptyMessage?: string;
  onVoidReceive?: (receipt: JwActivityReceipt) => void;
};

function entryBadge(entryType: "receive" | "return" | undefined) {
  if (entryType === "return") {
    return (
      <Badge tone="warning" size="sm">
        Returned
      </Badge>
    );
  }
  return (
    <Badge tone="info" size="sm">
      Received
    </Badge>
  );
}

export default function JwActivityLog({
  items,
  emptyMessage = "No receive or return activity yet.",
  onVoidReceive,
}: Props) {
  const sorted = [...items].sort(
    (a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
  );

  if (sorted.length === 0) {
    return <p className="text-sm text-ink-muted">{emptyMessage}</p>;
  }

  return (
    <div className="space-y-2">
      {sorted.map((r) => {
        const isReturn = r.entry_type === "return";
        const canVoid = !isReturn && !r.voided_at && onVoidReceive;
        return (
          <div
            key={r.id}
            className={cn(
              "flex flex-col gap-2 rounded-xl border border-line/60 p-3 sm:flex-row sm:items-center sm:justify-between",
              r.voided_at && "opacity-60"
            )}
          >
            <div className="min-w-0 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                {entryBadge(r.entry_type)}
                {r.lineLabel ? (
                  <span className="text-sm font-medium text-ink">{r.lineLabel}</span>
                ) : null}
              </div>
              <p className="text-sm text-ink">
                <JwQtyCell
                  qty={{
                    is_loose: Boolean(r.is_loose),
                    bags: r.bag_count,
                    loose_kg: r.loose_kg,
                    kg: r.quantity_kg,
                  }}
                />
              </p>
              <p className="text-xs text-ink-muted">
                {r.location_name ?? `Location #${r.location_id}`} · {formatDateTime(r.received_at)}
              </p>
              {r.voided_at ? (
                <Badge tone="muted" size="sm">
                  Voided
                </Badge>
              ) : null}
            </div>
            {canVoid ? (
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Trash2 className="h-4 w-4" />}
                onClick={() => onVoidReceive?.(r)}
              >
                Void
              </Button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function activityQtyLabel(r: JwActivityReceipt): string {
  return formatJwPrimaryQty({
    is_loose: Boolean(r.is_loose),
    bags: r.bag_count,
    loose_kg: r.loose_kg,
    kg: r.quantity_kg,
  });
}
