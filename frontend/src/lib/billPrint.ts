import type { Bill, BillLine, BookSettings } from "../api/client";
import { formatInr, formatQtyKg } from "./format";

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

export function billDueAmount(bill: Bill): number {
  return Number(bill.amount_due ?? bill.due_amount ?? Number(bill.grand_total) - Number(bill.amount_paid));
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
