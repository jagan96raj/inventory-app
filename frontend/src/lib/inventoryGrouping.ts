export type InvRow = {
  id: number;
  product_id: number;
  brand_id: number;
  location_id: number;
  bag_type_id: number;
  owner_type?: "owned" | "job_work";
  customer_id?: number | null;
  customer_name?: string | null;
  product_name?: string;
  brand_name?: string;
  location_name?: string;
  bag_type_name?: string;
  bag_count: number;
  loose_kg: string;
  total_quantity_kg: string;
};

export type ProductGroup = {
  productId: number;
  productName: string;
  rows: InvRow[];
};

export type OwnerGroup = {
  ownerKey: string;
  ownerType: "owned" | "job_work";
  customerId: number | null;
  customerName: string | null;
  products: ProductGroup[];
};

export type LocationGroup = {
  locationId: number;
  locationName: string;
  sampleRow: InvRow;
  owners: OwnerGroup[];
};

export function ownerKey(row: InvRow): string {
  if (row.owner_type === "job_work" && row.customer_id != null) {
    return `job_work:${row.customer_id}`;
  }
  return "owned";
}

export function ownerTotalKg(owner: OwnerGroup): number {
  return owner.products.reduce(
    (sum, product) =>
      sum + product.rows.reduce((lineSum, row) => lineSum + Number(row.total_quantity_kg), 0),
    0
  );
}

export function locationTotalKg(location: LocationGroup): number {
  return location.owners.reduce((sum, owner) => sum + ownerTotalKg(owner), 0);
}

export function groupInventoryRows(rows: InvRow[]): LocationGroup[] {
  const groups: LocationGroup[] = [];
  let currentLoc: LocationGroup | null = null;
  let currentOwner: OwnerGroup | null = null;
  let currentProd: ProductGroup | null = null;

  for (const row of rows) {
    const rowOwnerKey = ownerKey(row);
    if (!currentLoc || currentLoc.locationId !== row.location_id) {
      currentLoc = {
        locationId: row.location_id,
        locationName: row.location_name ?? `Location #${row.location_id}`,
        sampleRow: row,
        owners: [],
      };
      groups.push(currentLoc);
      currentOwner = null;
      currentProd = null;
    }
    if (!currentOwner || currentOwner.ownerKey !== rowOwnerKey) {
      currentOwner = {
        ownerKey: rowOwnerKey,
        ownerType: row.owner_type ?? "owned",
        customerId: row.customer_id ?? null,
        customerName: row.customer_name ?? null,
        products: [],
      };
      currentLoc.owners.push(currentOwner);
      currentProd = null;
    }
    if (!currentProd || currentProd.productId !== row.product_id) {
      currentProd = {
        productId: row.product_id,
        productName: row.product_name ?? "—",
        rows: [],
      };
      currentOwner.products.push(currentProd);
    }
    currentProd.rows.push(row);
  }

  return groups;
}

export function flattenLocationRows(location: LocationGroup): InvRow[] {
  return location.owners.flatMap((owner) => owner.products.flatMap((product) => product.rows));
}

/** Consecutive rows with the same product_id → one ProductGroup (for rowspan tables). */
export function groupRowsByProduct(rows: InvRow[]): ProductGroup[] {
  const products: ProductGroup[] = [];
  let current: ProductGroup | null = null;
  for (const row of rows) {
    if (!current || current.productId !== row.product_id) {
      current = {
        productId: row.product_id,
        productName: row.product_name ?? "—",
        rows: [],
      };
      products.push(current);
    }
    current.rows.push(row);
  }
  return products;
}
