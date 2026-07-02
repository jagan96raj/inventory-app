export type StockAtLocation = {
  product_id: number;
  brand_id: number;
  bag_type_id: number;
  owner_type?: "owned" | "job_work";
  customer_id?: number | null;
  customer_name?: string | null;
  bag_count: number;
  loose_kg: string;
  total_quantity_kg: string;
  product_name?: string;
  brand_name?: string;
  bag_type_name?: string;
};

export type StockOwnerFilter = {
  owner_type?: "owned" | "job_work";
  customer_id?: number | null;
};

type Option = { id: number; label: string };

function distinctById(items: Option[]): Option[] {
  const seen = new Set<number>();
  return items.filter((x) => {
    if (seen.has(x.id)) return false;
    seen.add(x.id);
    return true;
  });
}

function rowHasStock(row: StockAtLocation): boolean {
  return Number(row.total_quantity_kg) > 0 || Number(row.bag_count) > 0;
}

function rowIsJobWork(row: StockAtLocation): boolean {
  return row.owner_type === "job_work";
}

function rowIsOwned(row: StockAtLocation): boolean {
  return !row.owner_type || row.owner_type === "owned";
}

function customerIdsMatch(
  a: number | string | null | undefined,
  b: number | string | null | undefined
): boolean {
  if (a == null || b == null) return false;
  return Number(a) === Number(b);
}

export function filterStockForOwner(
  stock: StockAtLocation[],
  owner: StockOwnerFilter
): StockAtLocation[] {
  return stock.filter((row) => {
    if (!rowHasStock(row)) return false;
    if (!owner.owner_type || owner.owner_type === "owned") {
      return rowIsOwned(row);
    }
    if (!rowIsJobWork(row)) return false;
    if (owner.customer_id == null) return true;
    return customerIdsMatch(row.customer_id, owner.customer_id);
  });
}

export function jobWorkCustodiansAtLocation(stock: StockAtLocation[]): { id: number; name: string }[] {
  const map = new Map<number, string>();
  for (const row of stock) {
    if (!rowIsJobWork(row) || !rowHasStock(row) || row.customer_id == null) continue;
    const id = Number(row.customer_id);
    map.set(id, row.customer_name ?? `Customer #${id}`);
  }
  return [...map.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function stockOwnerFilter(
  ownerType: "owned" | "job_work",
  customerId: string
): StockOwnerFilter {
  return {
    owner_type: ownerType,
    customer_id: ownerType === "job_work" && customerId ? Number(customerId) : null,
  };
}

export function productsFromStock(stock: StockAtLocation[]): Option[] {
  const map = new Map<number, string>();
  for (const r of stock) {
    if (!map.has(r.product_id)) {
      map.set(r.product_id, r.product_name ?? `Product #${r.product_id}`);
    }
  }
  return distinctById(
    [...map.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  );
}

export function brandsFromStock(stock: StockAtLocation[], productId: string): Option[] {
  if (!productId) return [];
  const pid = Number(productId);
  const map = new Map<number, string>();
  for (const r of stock.filter((x) => x.product_id === pid)) {
    if (!map.has(r.brand_id)) {
      map.set(r.brand_id, r.brand_name ?? `Brand #${r.brand_id}`);
    }
  }
  return distinctById(
    [...map.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  );
}

export function bagTypesFromStock(stock: StockAtLocation[], productId: string, brandId: string): Option[] {
  if (!productId || !brandId) return [];
  const pid = Number(productId);
  const bid = Number(brandId);
  const map = new Map<number, string>();
  for (const r of stock.filter((x) => x.product_id === pid && x.brand_id === bid)) {
    if (!map.has(r.bag_type_id)) {
      map.set(r.bag_type_id, r.bag_type_name ?? `Bag #${r.bag_type_id}`);
    }
  }
  return distinctById(
    [...map.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  );
}

export function stockRow(
  stock: StockAtLocation[],
  productId: string,
  brandId: string,
  bagTypeId: string,
  owner?: StockOwnerFilter
): StockAtLocation | undefined {
  if (!productId || !brandId || !bagTypeId) return undefined;
  return stock.find((x) => {
    if (x.product_id !== Number(productId) || x.brand_id !== Number(brandId) || x.bag_type_id !== Number(bagTypeId)) {
      return false;
    }
    if (!owner?.owner_type || owner.owner_type === "owned") {
      return !x.owner_type || x.owner_type === "owned";
    }
    if (owner.owner_type === "job_work") {
      if (!rowIsJobWork(x)) return false;
      if (owner.customer_id != null && !customerIdsMatch(x.customer_id, owner.customer_id)) return false;
      return true;
    }
    return true;
  });
}
