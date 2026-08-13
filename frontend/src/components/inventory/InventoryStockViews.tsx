import { ChevronDown, ChevronRight, MapPin, Pencil, TriangleAlert } from "lucide-react";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import CustomerDetailLink from "../CustomerDetailLink";
import EmptyState from "../ui/EmptyState";
import IconButton from "../ui/IconButton";
import Skeleton from "../ui/Skeleton";
import { formatQtyKg } from "../../lib/format";
import {
  locationTotalKg,
  ownerTotalKg,
  type InvRow,
  type LocationGroup,
  type OwnerGroup,
  type ProductGroup,
} from "../../lib/inventoryGrouping";
import { cn } from "../../lib/cn";

const CELL = "px-4 py-2.5 align-middle text-sm";
const NUM = cn(CELL, "text-right");
const HEAD = "px-4 py-2.5 align-middle whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-ink-muted";
const HEAD_LEFT = cn(HEAD, "text-left");
const HEAD_NUM = cn(HEAD, "text-right");
const HEAD_CENTER = cn(HEAD, "text-center");
const NUM_TEXT = "inline-block min-w-[5.5rem] whitespace-nowrap text-right tabular-nums v2-mono text-sm";
const BAG_TEXT = "inline-block min-w-[2.25rem] whitespace-nowrap text-right tabular-nums text-sm";
const LOW_SLOT = "inline-flex h-4 w-4 shrink-0 items-center justify-center";

const BAG_HEAD_INNER = "inline-block min-w-[2.25rem] whitespace-nowrap text-right tabular-nums";
const NUM_HEAD_INNER = "inline-block min-w-[5.5rem] whitespace-nowrap text-right tabular-nums";

function BagsHeader() {
  return (
    <th scope="col" className={HEAD_NUM}>
      <div className="flex justify-end">
        <span className={BAG_HEAD_INNER}>Bags</span>
      </div>
    </th>
  );
}

function LooseKgHeader() {
  return (
    <th scope="col" className={HEAD_NUM}>
      <div className="flex justify-end">
        <span className={NUM_HEAD_INNER}>Loose kg</span>
      </div>
    </th>
  );
}

function TotalKgHeader() {
  return (
    <th scope="col" className={HEAD_NUM}>
      <div className="flex items-center justify-end gap-2">
        <span className="shrink-0 whitespace-nowrap tabular-nums v2-mono text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Total kg
        </span>
        <span className={LOW_SLOT} aria-hidden="true" />
      </div>
    </th>
  );
}

function ActionsHeader() {
  return (
    <th scope="col" className={cn(HEAD_CENTER, "w-[5rem] min-w-[5rem]")}>
      <span className="inline-block whitespace-nowrap">Actions</span>
    </th>
  );
}

function BagsCell({ count }: { count: number }) {
  return (
    <td className={NUM}>
      <div className="flex justify-end">
        <span className={BAG_TEXT}>{count}</span>
      </div>
    </td>
  );
}

function LooseKgCell({ kg }: { kg: string | number }) {
  return (
    <td className={NUM}>
      <div className="flex justify-end">
        <span className={NUM_TEXT}>{formatQtyKg(kg)}</span>
      </div>
    </td>
  );
}

function TotalKgCell({ kg, low }: { kg: string | number; low: boolean }) {
  return (
    <td className={NUM}>
      <div className="flex items-center justify-end gap-2">
        <span className="shrink-0 whitespace-nowrap tabular-nums v2-mono text-sm font-semibold">
          {formatQtyKg(kg)}
        </span>
        <span
          className={LOW_SLOT}
          title={low ? lowStockHint() : undefined}
          aria-hidden={!low}
        >
          {low ? (
            <TriangleAlert
              className="h-4 w-4 text-warning-600 dark:text-warning-400"
              aria-label="Low stock"
            />
          ) : null}
        </span>
      </div>
    </td>
  );
}

/** Low-stock warning when total kg on a line is below this threshold. */
export const LOW_KG_THRESHOLD = 500;

export function isLowStock(row: InvRow): boolean {
  return Number(row.total_quantity_kg) < LOW_KG_THRESHOLD;
}

function lowStockHint(): string {
  return `Low stock — below ${LOW_KG_THRESHOLD.toLocaleString("en-IN")} kg`;
}

type ProductTableProps = {
  products: ProductGroup[];
  onEdit: (row: InvRow) => void;
  className?: string;
};

function ProductGroupedTable({ products, onEdit, className }: ProductTableProps) {
  return (
    <>
      <div className={cn("hidden overflow-x-auto lg:block", className)}>
        <table className="v2-data-table inventory-stock-table w-full min-w-[44rem] text-sm">
          <colgroup>
            <col className="w-[20%]" />
            <col className="w-[14%]" />
            <col className="w-[14%]" />
            <col style={{ width: "4.5rem" }} />
            <col style={{ width: "6.75rem" }} />
            <col style={{ width: "11rem" }} />
            <col style={{ width: "5rem" }} />
          </colgroup>
          <thead className="bg-surface-subtle/80">
            <tr>
              <th scope="col" className={HEAD_LEFT}>
                Product
              </th>
              <th scope="col" className={HEAD_LEFT}>
                Brand
              </th>
              <th scope="col" className={HEAD_LEFT}>
                Bag type
              </th>
              <BagsHeader />
              <LooseKgHeader />
              <TotalKgHeader />
              <ActionsHeader />
            </tr>
          </thead>
          <tbody>
            {products.map((product, productIdx) =>
              product.rows.map((row, rowIdx) => {
                const low = isLowStock(row);
                const isFirst = rowIdx === 0;
                const isLastRow = rowIdx === product.rows.length - 1;
                const isLastProduct = productIdx === products.length - 1;
                return (
                  <tr
                    key={row.id}
                    className={cn(
                      low && "bg-amber-50/80 dark:bg-amber-950/20",
                      !isLastRow && "border-b border-line/25",
                      isLastRow && !isLastProduct && "border-b-2 border-line/50"
                    )}
                  >
                    {isFirst ? (
                      <td
                        rowSpan={product.rows.length}
                        className={cn(
                          CELL,
                          "border-r border-line/40 bg-surface-subtle/40 align-top font-semibold text-ink"
                        )}
                        title={product.productName}
                      >
                        <span className="line-clamp-4">{product.productName}</span>
                      </td>
                    ) : null}
                    <td className={cn(CELL, "truncate")} title={row.brand_name ?? undefined}>
                      {row.brand_name ?? "—"}
                    </td>
                    <td className={cn(CELL, "truncate")} title={row.bag_type_name ?? undefined}>
                      {row.bag_type_name ?? "—"}
                    </td>
                    <BagsCell count={row.bag_count} />
                    <LooseKgCell kg={row.loose_kg} />
                    <TotalKgCell kg={row.total_quantity_kg} low={low} />
                    <td className={cn(CELL, "inventory-actions-cell whitespace-nowrap text-center")}>
                      <IconButton
                        label="Edit stock"
                        size="sm"
                        variant="ghost"
                        onClick={() => onEdit(row)}
                      >
                        <Pencil className="h-4 w-4" />
                      </IconButton>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <div className={cn("space-y-3 lg:hidden", className)}>
        {products.flatMap((product) =>
          product.rows.map((row) => {
            const low = isLowStock(row);
            return (
              <div
                key={row.id}
                className={cn(
                  "space-y-3 rounded-xl border border-line/80 bg-surface p-3",
                  low && "border-amber-300/80 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-950/25"
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{product.productName}</p>
                    <p className="mt-0.5 truncate text-sm text-ink-muted">
                      {row.brand_name ?? "—"} · {row.bag_type_name ?? "—"}
                    </p>
                  </div>
                  {low ? (
                    <TriangleAlert
                      className="h-4 w-4 shrink-0 text-warning-600 dark:text-warning-400"
                      aria-label="Low stock"
                    />
                  ) : null}
                </div>
                <dl className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <dt className="text-ink-subtle">Bags</dt>
                    <dd className="v2-mono tabular-nums text-ink">{row.bag_count}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-subtle">Loose kg</dt>
                    <dd className="v2-mono tabular-nums text-ink">{formatQtyKg(row.loose_kg)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-subtle">Total kg</dt>
                    <dd className="v2-mono font-semibold tabular-nums text-ink">
                      {formatQtyKg(row.total_quantity_kg)}
                    </dd>
                  </div>
                </dl>
                <Button
                  size="md"
                  variant="secondary"
                  className="w-full"
                  leftIcon={<Pencil className="h-4 w-4" />}
                  onClick={() => onEdit(row)}
                >
                  Edit stock
                </Button>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

function OwnerLabel({ owner }: { owner: OwnerGroup }) {
  if (owner.ownerType === "job_work") {
    return owner.customerId ? (
      <CustomerDetailLink customerId={owner.customerId} customerName={owner.customerName} />
    ) : (
      <Badge tone="info" size="sm">
        Job work
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" size="sm">
      Owned
    </Badge>
  );
}

type OwnerProductTableProps = {
  owners: OwnerGroup[];
  onEdit: (row: InvRow) => void;
};

/** Detail view: product + owner columns grouped (rowspan) per owner → product. */
function OwnerProductGroupedTable({ owners, onEdit }: OwnerProductTableProps) {
  return (
    <>
      <div className="hidden overflow-x-auto lg:block">
        <table className="v2-data-table inventory-stock-table w-full min-w-[52rem] text-sm">
          <colgroup>
            <col className="w-[18%]" />
            <col className="w-[14%]" />
            <col className="w-[14%]" />
            <col className="w-[14%]" />
            <col style={{ width: "4.5rem" }} />
            <col style={{ width: "6.75rem" }} />
            <col style={{ width: "11rem" }} />
            <col style={{ width: "5rem" }} />
          </colgroup>
          <thead className="bg-surface-subtle/80">
            <tr>
              <th scope="col" className={HEAD_LEFT}>
                Owner
              </th>
              <th scope="col" className={HEAD_LEFT}>
                Product
              </th>
              <th scope="col" className={HEAD_LEFT}>
                Brand
              </th>
              <th scope="col" className={HEAD_LEFT}>
                Bag type
              </th>
              <BagsHeader />
              <LooseKgHeader />
              <TotalKgHeader />
              <ActionsHeader />
            </tr>
          </thead>
          <tbody>
            {owners.flatMap((owner, ownerIdx) => {
              const isLastOwner = ownerIdx === owners.length - 1;

              return owner.products.flatMap((product, productIdx) =>
                product.rows.map((row, rowIdx) => {
                  const low = isLowStock(row);
                  const isFirstProductRow = rowIdx === 0;
                  const isLastProductRow = rowIdx === product.rows.length - 1;
                  const isLastProduct = productIdx === owner.products.length - 1;

                  return (
                    <tr
                      key={row.id}
                      className={cn(
                        low && "bg-amber-50/80 dark:bg-amber-950/20",
                        !isLastProductRow && "border-b border-line/25",
                        isLastProductRow && !isLastProduct && "border-b border-line/35",
                        isLastProductRow && isLastProduct && !isLastOwner && "border-b-2 border-line/50"
                      )}
                    >
                      {isFirstProductRow ? (
                        <td
                          rowSpan={product.rows.length}
                          className={cn(
                            CELL,
                            "border-r border-line/30 bg-surface-subtle/25 align-top"
                          )}
                        >
                          <OwnerLabel owner={owner} />
                        </td>
                      ) : null}
                      {isFirstProductRow ? (
                        <td
                          rowSpan={product.rows.length}
                          className={cn(
                            CELL,
                            "border-r border-line/40 bg-surface-subtle/40 align-top font-semibold text-ink"
                          )}
                          title={product.productName}
                        >
                          <span className="line-clamp-4">{product.productName}</span>
                        </td>
                      ) : null}
                      <td className={cn(CELL, "truncate")} title={row.brand_name ?? undefined}>
                        {row.brand_name ?? "—"}
                      </td>
                      <td className={cn(CELL, "truncate")} title={row.bag_type_name ?? undefined}>
                        {row.bag_type_name ?? "—"}
                      </td>
                      <BagsCell count={row.bag_count} />
                      <LooseKgCell kg={row.loose_kg} />
                      <TotalKgCell kg={row.total_quantity_kg} low={low} />
                      <td className={cn(CELL, "inventory-actions-cell whitespace-nowrap text-center")}>
                        <IconButton
                          label="Edit stock"
                          size="sm"
                          variant="outline"
                          onClick={() => onEdit(row)}
                        >
                          <Pencil className="h-4 w-4" />
                        </IconButton>
                      </td>
                    </tr>
                  );
                })
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="space-y-3 p-3 lg:hidden">
        {owners.flatMap((owner) =>
          owner.products.flatMap((product) =>
            product.rows.map((row) => {
              const low = isLowStock(row);
              return (
                <div
                  key={row.id}
                  className={cn(
                    "space-y-3 rounded-xl border border-line/80 bg-surface p-3",
                    low && "border-amber-300/80 bg-amber-50/70 dark:border-amber-800 dark:bg-amber-950/25"
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <OwnerLabel owner={owner} />
                  </div>
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{product.productName}</p>
                    <p className="mt-0.5 truncate text-sm text-ink-muted">
                      {row.brand_name ?? "—"} · {row.bag_type_name ?? "—"}
                    </p>
                  </div>
                  <dl className="grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <dt className="text-ink-subtle">Bags</dt>
                      <dd className="v2-mono tabular-nums text-ink">{row.bag_count}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-subtle">Loose kg</dt>
                      <dd className="v2-mono tabular-nums text-ink">{formatQtyKg(row.loose_kg)}</dd>
                    </div>
                    <div>
                      <dt className="text-ink-subtle">Total kg</dt>
                      <dd className="v2-mono font-semibold tabular-nums text-ink">
                        {formatQtyKg(row.total_quantity_kg)}
                      </dd>
                    </div>
                  </dl>
                  <Button
                    size="md"
                    variant="secondary"
                    className="w-full"
                    leftIcon={<Pencil className="h-4 w-4" />}
                    onClick={() => onEdit(row)}
                  >
                    Edit stock
                  </Button>
                </div>
              );
            })
          )
        )}
      </div>
    </>
  );
}

type SummaryProps = {
  groups: LocationGroup[];
  loading: boolean;
  collapsedLocationIds: Set<number>;
  expandedOwnerKeys: Set<string>;
  onToggleLocation: (locationId: number) => void;
  onToggleOwner: (key: string) => void;
  onEdit: (row: InvRow) => void;
  onAddStock: () => void;
};

export function InventorySummaryView({
  groups,
  loading,
  collapsedLocationIds,
  expandedOwnerKeys,
  onToggleLocation,
  onToggleOwner,
  onEdit,
  onAddStock,
}: SummaryProps) {
  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (groups.length === 0) {
    return (
      <EmptyState
        title="No stock rows"
        description="Add opening stock or clear filters."
        action={<Button onClick={onAddStock}>Add stock</Button>}
      />
    );
  }

  return (
    <div className="space-y-3">
      {groups.map((location) => {
        const locCollapsed = collapsedLocationIds.has(location.locationId);
        const lineCount = location.owners.reduce(
          (n, o) => n + o.products.reduce((pn, p) => pn + p.rows.length, 0),
          0
        );
        return (
          <section
            key={location.locationId}
            className="overflow-hidden rounded-xl border border-line bg-surface shadow-soft"
          >
            <button
              type="button"
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-subtle/60"
              onClick={() => onToggleLocation(location.locationId)}
            >
              {locCollapsed ? (
                <ChevronRight className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden="true" />
              )}
              <MapPin className="h-5 w-5 shrink-0 text-primary-600" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block text-base font-semibold text-ink">{location.locationName}</span>
                <span className="text-sm text-ink-muted">
                  {location.owners.length} owner{location.owners.length === 1 ? "" : "s"} · {lineCount} line
                  {lineCount === 1 ? "" : "s"} · {formatQtyKg(locationTotalKg(location))}
                </span>
              </span>
            </button>

            {!locCollapsed && (
              <div className="border-t border-line/60">
                {location.owners.map((owner) => {
                  const ownerExpandKey = `${location.locationId}:${owner.ownerKey}`;
                  const ownerExpanded = expandedOwnerKeys.has(ownerExpandKey);
                  const ownerLines = owner.products.reduce((n, p) => n + p.rows.length, 0);
                  return (
                    <div key={ownerExpandKey} className="border-b border-line/40 last:border-b-0">
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 px-4 py-2.5 pl-4 text-left hover:bg-surface-subtle/50 sm:pl-10"
                        onClick={() => onToggleOwner(ownerExpandKey)}
                      >
                        {ownerExpanded ? (
                          <ChevronDown className="h-4 w-4 shrink-0 text-ink-muted" />
                        ) : (
                          <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" />
                        )}
                        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                          {owner.ownerType === "job_work" ? (
                            <>
                              <Badge tone="info" size="sm">
                                Job work
                              </Badge>
                              <span className="font-medium text-ink">
                                {owner.customerName ?? `Customer #${owner.customerId}`}
                              </span>
                              {owner.customerId ? (
                                <CustomerDetailLink
                                  customerId={owner.customerId}
                                  customerName={owner.customerName}
                                />
                              ) : null}
                            </>
                          ) : (
                            <Badge tone="neutral" size="sm">
                              Owned
                            </Badge>
                          )}
                          <span className="text-sm text-ink-muted">
                            {ownerLines} line{ownerLines === 1 ? "" : "s"} · {formatQtyKg(ownerTotalKg(owner))}
                          </span>
                        </div>
                      </button>
                      {ownerExpanded ? (
                        <div className="px-3 pb-3 sm:px-4 sm:pb-4 sm:pl-10 lg:pl-16">
                          <ProductGroupedTable
                            products={owner.products}
                            onEdit={onEdit}
                            className="rounded-lg border border-line/50"
                          />
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

type DetailProps = {
  groups: LocationGroup[];
  loading: boolean;
  onEdit: (row: InvRow) => void;
  onAddStock: () => void;
  onLocationClick?: (row: InvRow) => void;
};

export function InventoryDetailView({
  groups,
  loading,
  onEdit,
  onAddStock,
  onLocationClick,
}: DetailProps) {
  if (loading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }
  if (groups.length === 0) {
    return (
      <EmptyState
        title="No stock rows"
        description="Add opening stock or clear filters."
        action={<Button onClick={onAddStock}>Add stock</Button>}
      />
    );
  }

  return (
    <div className="space-y-4">
      {groups.map((location) => (
          <section
            key={location.locationId}
            className="overflow-hidden rounded-xl border border-line bg-surface"
          >
            <header className="border-b border-line/60 bg-surface-subtle/50 px-4 py-3">
              <button
                type="button"
                className="inline-flex items-center gap-2 text-left font-semibold text-ink hover:opacity-80"
                onClick={() => onLocationClick?.(location.sampleRow)}
              >
                <MapPin className="h-4 w-4 text-primary-600" aria-hidden="true" />
                {location.locationName}
                <span className="text-sm font-normal text-ink-muted">
                  · {formatQtyKg(locationTotalKg(location))}
                </span>
              </button>
            </header>
            <OwnerProductGroupedTable owners={location.owners} onEdit={onEdit} />
          </section>
        ))}
    </div>
  );
}
