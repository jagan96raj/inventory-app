/** Company address fields for Profile + registration (v17.0.6). */
export const companyAddressFormFields = [
  {
    key: "address_line",
    label: "Address line 1",
    optional: true,
    wide: true,
    placeholder: "Door no., street, building…",
  },
  {
    key: "address_line_2",
    label: "Address line 2",
    optional: true,
    wide: true,
    placeholder: "Area, landmark (optional)",
  },
  {
    key: "district",
    label: "District",
    optional: true,
    placeholder: "e.g. Coimbatore",
  },
  {
    key: "state",
    label: "State",
    optional: true,
    placeholder: "e.g. Tamil Nadu",
  },
  {
    key: "pin_code",
    label: "PIN code",
    optional: true,
    placeholder: "6 digits",
  },
  {
    key: "gstin",
    label: "GSTIN",
    optional: true,
    wide: true,
    placeholder: "e.g. 33AAAAA0000A1Z5",
  },
] as const;

export type CompanyAddressFieldKey = (typeof companyAddressFormFields)[number]["key"];

export function formatCompanyAddressLines(c: {
  address_line?: string | null;
  address_line_2?: string | null;
  district?: string | null;
  state?: string | null;
  pin_code?: string | null;
}): string[] {
  const lines: string[] = [];
  if (c.address_line?.trim()) lines.push(c.address_line.trim());
  if (c.address_line_2?.trim()) lines.push(c.address_line_2.trim());
  const cityLine = [c.district, c.state, c.pin_code]
    .map((p) => (p && String(p).trim()) || "")
    .filter(Boolean)
    .join(", ");
  if (cityLine) lines.push(cityLine);
  return lines;
}
