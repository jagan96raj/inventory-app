import { Fragment, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import Skeleton from "./Skeleton";

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  width?: string;
  numeric?: boolean;
};

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  caption?: string;
  loading?: boolean;
  loadingRows?: number;
  empty?: ReactNode;
  rowClassName?: (row: T, index: number) => string | undefined;
  zebra?: boolean;
  compact?: boolean;
  stickyHeader?: boolean;
  onRowClick?: (row: T, index: number) => void;
  className?: string;
  headerClassName?: string;
};

export default function Table<T>({
  columns,
  rows,
  rowKey,
  caption,
  loading = false,
  loadingRows = 5,
  empty,
  rowClassName,
  zebra,
  compact,
  stickyHeader = false,
  onRowClick,
  className,
  headerClassName,
}: Props<T>) {
  const alignClass = (a?: Column<T>["align"]) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className={cn("overflow-x-auto rounded-2xl border border-line/80 bg-surface-subtle/70", className)}>
      <table className="v2-data-table w-full min-w-[40rem] text-base">
        {caption && <caption className="sr-only">{caption}</caption>}
        <colgroup>
          {columns.map((c) => (
            <col key={c.key} style={c.width ? { width: c.width } : undefined} />
          ))}
        </colgroup>
        <thead
          className={cn(
            "bg-surface-muted text-base font-semibold uppercase tracking-wide text-primary-800/90 dark:bg-surface-muted dark:text-primary-200/90",
            stickyHeader && "sticky top-16 z-10",
            headerClassName
          )}
        >
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cn(
                  "whitespace-nowrap border-b border-line px-4 py-3 align-middle",
                  alignClass(c.align ?? (c.numeric ? "right" : "left")),
                  c.className
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: loadingRows }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-b border-line/80 last:border-0">
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn("px-5 py-4 align-middle text-base", compact && "py-3")}
                    >
                      <Skeleton className="h-5" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.length === 0
              ? (
                  <tr>
                    <td colSpan={columns.length} className="px-5 py-12 text-center">
                      {empty ?? <span className="text-base text-ink-muted">No results</span>}
                    </td>
                  </tr>
                )
              : (
                  <Fragment>
                    {rows.map((row, idx) => (
                      <tr
                        key={rowKey(row, idx)}
                        onClick={onRowClick ? () => onRowClick(row, idx) : undefined}
                        className={cn(
                          "border-b border-line/70 last:border-0 transition-colors",
                          zebra && idx % 2 === 1 && "bg-surface-subtle/50",
                          onRowClick && "cursor-pointer hover:bg-surface-muted",
                          rowClassName?.(row, idx)
                        )}
                      >
                        {columns.map((c) => (
                          <td
                            key={c.key}
                            className={cn(
                              "px-5 py-4 align-middle text-base text-ink",
                              compact && "py-3",
                              alignClass(c.align ?? (c.numeric ? "right" : "left")),
                              c.numeric && "v2-mono tabular-nums whitespace-nowrap",
                              c.className
                            )}
                          >
                            {c.cell(row, idx)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                )}
        </tbody>
      </table>
    </div>
  );
}
