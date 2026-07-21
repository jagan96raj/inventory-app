import { forwardRef } from "react";
import {
  billDocumentTitle,
  billLineQtyLabel,
  billTotalsRows,
  formatCustomerAddress,
  type BillPrintDocumentProps,
} from "../../lib/billPrint";
import { formatCompanyAddressLines } from "../../lib/companyAddressFields";
import { formatInr, formatDate } from "../../lib/format";
import { cn } from "../../lib/cn";

const BillPrintDocument = forwardRef<HTMLDivElement, BillPrintDocumentProps>(function BillPrintDocument(
  { bill, bookSettings, billType },
  ref
) {
  const isVoided = bill.status === "voided";
  const customerAddress = formatCustomerAddress(bill);
  const totals = billTotalsRows(bill);
  const companyAddressLines = bookSettings
    ? formatCompanyAddressLines({
        address_line: bookSettings.company_address_line,
        address_line_2: bookSettings.company_address_line_2,
        district: bookSettings.company_district,
        state: bookSettings.company_state,
        pin_code: bookSettings.company_pin_code,
      })
    : [];

  return (
    <div
      ref={ref}
      className={cn(
        "bill-print-root relative mx-auto max-w-[210mm] bg-white px-8 py-10 text-ink print:px-0 print:py-0",
        isVoided && "bill-print-voided"
      )}
    >
      {isVoided && (
        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center print:flex"
          aria-hidden
        >
          <span className="rotate-[-30deg] text-7xl font-bold uppercase tracking-[0.35em] text-danger-500/20 print:text-danger-600/25">
            VOIDED
          </span>
        </div>
      )}

      <header className="border-b border-ink/15 pb-5">
        {bookSettings?.company_name && (
          <h1 className="text-2xl font-bold tracking-tight text-ink">{bookSettings.company_name}</h1>
        )}
        {companyAddressLines.map((line) => (
          <p key={line} className="mt-1 text-sm text-ink-muted">
            {line}
          </p>
        ))}
        {bookSettings?.company_phone && (
          <p className="mt-1 text-sm text-ink-muted">Phone: {bookSettings.company_phone}</p>
        )}
        {bookSettings?.company_gstin && (
          <p className="mt-1 text-sm text-ink-muted">GSTIN: {bookSettings.company_gstin}</p>
        )}
        {!bookSettings?.company_name && (
          <p className="text-sm text-ink-muted">Set company details on Profile</p>
        )}
      </header>

      <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold uppercase tracking-wide text-ink">
            {billDocumentTitle(billType)}
          </h2>
          <p className="mt-2 text-sm">
            <span className="text-ink-muted">Bill no.</span>{" "}
            <span className="font-mono font-semibold">{bill.bill_number}</span>
          </p>
          <p className="text-sm">
            <span className="text-ink-muted">Date</span>{" "}
            <span className="font-medium">{formatDate(bill.bill_date)}</span>
          </p>
        </div>
        <div className="min-w-[12rem] text-sm">
          <p className="font-semibold text-ink">{bill.customer_name ?? "—"}</p>
          {customerAddress && <p className="mt-1 text-ink-muted">{customerAddress}</p>}
          {bill.customer_phone && <p className="mt-1 text-ink-muted">Phone: {bill.customer_phone}</p>}
        </div>
      </div>

      <table className="mt-8 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink/20">
            <th className="py-2 pr-2 text-left font-semibold">Product</th>
            <th className="py-2 pr-2 text-left font-semibold">Brand</th>
            <th className="py-2 pr-2 text-left font-semibold">Bag type</th>
            <th className="py-2 pr-2 text-right font-semibold">Qty</th>
            <th className="py-2 pr-2 text-right font-semibold">Rate/kg</th>
            <th className="py-2 text-right font-semibold">Line total</th>
          </tr>
        </thead>
        <tbody>
          {bill.lines.map((line) => (
            <tr key={line.id} className="border-b border-ink/10">
              <td className="py-2.5 pr-2 align-top">{line.product_name ?? "—"}</td>
              <td className="py-2.5 pr-2 align-top">{line.brand_name ?? "—"}</td>
              <td className="py-2.5 pr-2 align-top">{line.bag_type_name ?? "—"}</td>
              <td className="py-2.5 pr-2 text-right align-top font-mono text-xs">
                {billLineQtyLabel(line, billType)}
              </td>
              <td className="py-2.5 pr-2 text-right align-top font-mono">{formatInr(line.rate_per_kg)}</td>
              <td className="py-2.5 text-right align-top font-mono font-medium">{formatInr(line.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-6 flex justify-end">
        <table className="w-full max-w-xs text-sm">
          <tbody>
            {totals.map((row) => (
              <tr key={row.label}>
                <td className={cn("py-1 pr-4 text-ink-muted", row.emphasis && "font-semibold text-ink")}>
                  {row.label}
                </td>
                <td
                  className={cn(
                    "py-1 text-right font-mono",
                    row.emphasis ? "font-bold text-ink" : "text-ink"
                  )}
                >
                  {row.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {bill.notes?.trim() && (
        <div className="mt-6 rounded-md border border-ink/10 bg-surface-muted/30 px-4 py-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Notes</p>
          <p className="mt-1 whitespace-pre-wrap text-ink">{bill.notes.trim()}</p>
        </div>
      )}

      <footer className="mt-10 border-t border-ink/10 pt-4 text-xs text-ink-muted">
        Computer-generated bill · {bill.bill_number}
      </footer>
    </div>
  );
});

export default BillPrintDocument;
