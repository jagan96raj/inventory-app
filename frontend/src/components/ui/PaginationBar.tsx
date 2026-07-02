import Button from "./Button";
import { cn } from "../../lib/cn";

type Props = {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  className?: string;
};

export default function PaginationBar({ total, limit, offset, onPageChange, className }: Props) {
  if (total === 0) return null;

  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-3 py-3", className)}>
      <p className="text-sm text-ink-muted">
        Showing <span className="font-semibold text-ink">{from}</span>–
        <span className="font-semibold text-ink">{to}</span> of{" "}
        <span className="font-semibold text-ink">{total}</span>
      </p>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!hasPrev}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
        >
          Prev
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={!hasNext}
          onClick={() => onPageChange(offset + limit)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
