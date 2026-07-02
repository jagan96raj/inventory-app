import type { Customer } from "../api/client";

export function customerPhones(customer: Pick<Customer, "phone" | "alternate_phone">): string {
  return [customer.phone, customer.alternate_phone].filter(Boolean).join(" · ");
}

export function customerMatchesQuery(
  customer: Pick<Customer, "name" | "phone" | "alternate_phone">,
  query: string
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [customer.name, customer.phone ?? "", customer.alternate_phone ?? ""]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

export function customerComboLabel(customer: Pick<Customer, "name" | "phone" | "alternate_phone">): string {
  const phones = customerPhones(customer);
  return phones ? `${customer.name} (${phones})` : customer.name;
}
