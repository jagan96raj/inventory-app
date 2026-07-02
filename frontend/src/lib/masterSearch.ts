import {
  api,
  MASTER_SEARCH_LIMIT,
  type BagType,
  type Brand,
  type Customer,
  type Location,
  type PageOut,
  type Product,
} from "../api/client";
import type { ComboOption } from "../components/ui/Combobox";
import { customerPhones } from "./customerDisplay";

export type MasterComboOption = ComboOption<number> & {
  bagType?: BagType;
};

function buildSearchParams(query: string): string {
  const q = new URLSearchParams();
  q.set("limit", String(MASTER_SEARCH_LIMIT));
  q.set("offset", "0");
  const trimmed = query.trim();
  if (trimmed) q.set("search", trimmed);
  return q.toString();
}

export async function searchProducts(query: string): Promise<MasterComboOption[]> {
  const page = await api.get<PageOut<Product>>(`/api/products?${buildSearchParams(query)}`);
  return page.items.map((p) => ({
    value: p.id,
    label: p.product_name ?? `Product #${p.id}`,
  }));
}

export async function searchBrands(query: string): Promise<MasterComboOption[]> {
  const page = await api.get<PageOut<Brand>>(`/api/brands?${buildSearchParams(query)}`);
  return page.items.map((b) => ({
    value: b.id,
    label: b.name ?? `Brand #${b.id}`,
  }));
}

export async function searchCustomers(query: string): Promise<MasterComboOption[]> {
  const page = await api.get<PageOut<Customer>>(`/api/customers?${buildSearchParams(query)}`);
  return page.items.map((c) => ({
    value: c.id,
    label: c.name,
    hint: customerPhones(c) || undefined,
  }));
}

export async function searchLocations(query: string): Promise<MasterComboOption[]> {
  const page = await api.get<PageOut<Location>>(`/api/locations?${buildSearchParams(query)}`);
  return page.items.map((l) => ({
    value: l.id,
    label: l.name ?? `Location #${l.id}`,
    hint: [l.district, l.state].filter(Boolean).join(", ") || undefined,
  }));
}

export async function searchBagTypes(query: string): Promise<MasterComboOption[]> {
  const page = await api.get<PageOut<BagType>>(`/api/bag-types?${buildSearchParams(query)}`);
  return page.items.map((bt) => ({
    value: bt.id,
    label: bt.name,
    hint: bt.is_loose ? "Loose" : `${bt.weight_per_bag_kg} kg / bag`,
    bagType: bt,
  }));
}

export async function fetchCustomerById(id: number): Promise<Customer | null> {
  try {
    return await api.get<Customer>(`/api/customers/${id}`);
  } catch {
    return null;
  }
}

export async function fetchLocationById(id: number): Promise<Location | null> {
  try {
    return await api.get<Location>(`/api/locations/${id}`);
  } catch {
    return null;
  }
}

export async function fetchProductById(id: number): Promise<Product | null> {
  try {
    return await api.get<Product>(`/api/products/${id}`);
  } catch {
    return null;
  }
}

export async function fetchBrandById(id: number): Promise<Brand | null> {
  try {
    return await api.get<Brand>(`/api/brands/${id}`);
  } catch {
    return null;
  }
}

export async function fetchBagTypeById(id: number): Promise<BagType | null> {
  try {
    return await api.get<BagType>(`/api/bag-types/${id}`);
  } catch {
    return null;
  }
}

export async function fetchBagTypesByIds(ids: number[]): Promise<BagType[]> {
  const unique = [...new Set(ids.filter((id) => id > 0))];
  const results = await Promise.all(unique.map((id) => fetchBagTypeById(id)));
  return results.filter((bt): bt is BagType => bt != null);
}
