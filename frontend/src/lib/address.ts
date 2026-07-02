export type AddressFields = {
  address_line?: string | null;
  district?: string | null;
  state?: string | null;
  pin_code?: string | null;
};

export function formatDistrictState(a: AddressFields | null | undefined): string | null {
  const locality = [a?.district, a?.state].filter((x) => x?.trim()).join(", ");
  return locality || null;
}

export function hasAddress(a: AddressFields | null | undefined): boolean {
  if (!a) return false;
  return Boolean(
    a.address_line?.trim() || a.district?.trim() || a.state?.trim() || a.pin_code?.trim()
  );
}

export function formatAddress(a: AddressFields | null | undefined): string {
  if (!a) return "—";
  const parts: string[] = [];
  if (a.address_line?.trim()) parts.push(a.address_line.trim());
  const locality = [a.district, a.state].filter((x) => x?.trim()).join(", ");
  if (locality) parts.push(locality);
  if (a.pin_code?.trim()) parts.push(`PIN ${a.pin_code.trim()}`);
  return parts.length ? parts.join(" · ") : "—";
}

export function formatAddressMultiline(a: AddressFields | null | undefined): string {
  if (!a) return "";
  const lines: string[] = [];
  if (a.address_line?.trim()) lines.push(a.address_line.trim());
  const line2 = [a.district, a.state].filter((x) => x?.trim()).join(", ");
  if (line2) lines.push(line2);
  if (a.pin_code?.trim()) lines.push(`PIN ${a.pin_code.trim()}`);
  return lines.join("\n");
}
