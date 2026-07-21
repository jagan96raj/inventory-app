import type { Bill, BillLine, BookSettings } from "../api/client";
import { billDueAmount } from "./billAmounts";
import { formatCompanyAddressLines } from "./companyAddressFields";
import { formatInr, formatQtyKg } from "./format";

export { billDueAmount } from "./billAmounts";

export function formatCustomerAddress(bill: Bill): string {
  const parts = [
    bill.customer_address_line,
    bill.customer_district,
    bill.customer_state,
    bill.customer_pin_code,
  ].filter((p) => p && String(p).trim());
  return parts.join(", ");
}

export function billLineQtyLabel(line: BillLine, billType: "sales" | "purchase"): string {
  if (line.is_loose) {
    return formatQtyKg(line.ordered_quantity_kg);
  }
  const bags = line.bags_purchased ?? line.bags_sold ?? line.ordered_bags;
  return `${bags} bags · ${formatQtyKg(line.ordered_quantity_kg)}`;
}

export function billDocumentTitle(billType: "sales" | "purchase"): string {
  return billType === "sales" ? "Sales Bill" : "Purchase Bill";
}

export type BillPrintDocumentProps = {
  bill: Bill;
  bookSettings: BookSettings | null;
  billType: "sales" | "purchase";
};

/** Company header lines for bill print (book-settings embeds companies row fields). */
export function bookSettingsCompanyAddressLines(settings: BookSettings | null): string[] {
  if (!settings) return [];
  return formatCompanyAddressLines({
    address_line: settings.company_address_line,
    address_line_2: settings.company_address_line_2,
    district: settings.company_district,
    state: settings.company_state,
    pin_code: settings.company_pin_code,
  });
}

export function billTotalsRows(bill: Bill): Array<{ label: string; value: string; emphasis?: boolean }> {
  const rows = [
    { label: "Subtotal", value: formatInr(bill.subtotal) },
    { label: `Discount (${bill.discount_percent}%)`, value: formatInr(bill.discount_amount) },
    { label: "Adjustment", value: formatInr(bill.adjustment) },
    { label: "Grand total", value: formatInr(bill.grand_total), emphasis: true },
    { label: "Amount paid", value: formatInr(bill.amount_paid) },
    { label: "Amount due", value: formatInr(billDueAmount(bill)), emphasis: true },
  ];
  return rows;
}
