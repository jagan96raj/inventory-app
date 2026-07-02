import {
  formatJwKgSubline,
  formatJwPrimaryQty,
  type JwQtyFields,
} from "../lib/jwQty";
import { cn } from "../lib/cn";

type Props = {
  qty: JwQtyFields;
  emphasize?: boolean;
  className?: string;
};

export default function JwQtyCell({ qty, emphasize = false, className }: Props) {
  const sub = !qty.is_loose ? formatJwKgSubline(qty.kg) : null;
  return (
    <div className={cn("text-right", className)}>
      <div className={cn("v2-mono tabular-nums", emphasize ? "font-semibold text-ink" : "font-medium text-ink")}>
        {formatJwPrimaryQty(qty)}
      </div>
      {sub ? <div className="mt-0.5 text-xs tabular-nums text-ink-muted">{sub}</div> : null}
    </div>
  );
}
