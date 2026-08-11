import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  CalendarDays,
  Download,
  Hammer,
  IndianRupee,
  PackagePlus,
  Plus,
  Receipt,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  reportsApi,
  type BillTypeParam,
  type BusinessSummary,
  type FiscalYearSummary,
  type JobWorkByProduct,
  type SalesByCustomer,
  type SalesByLocation,
  type SalesByProduct,
} from "../api/client";
import { formatInr, formatInrCompact, formatQtyKg } from "../lib/format";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Stat from "../components/ui/Stat";
import Banner from "../components/ui/Banner";
import Select from "../components/ui/Select";
import SegmentedControl from "../components/ui/SegmentedControl";
import Skeleton from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import { searchCustomers } from "../lib/masterSearch";
import { cn } from "../lib/cn";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function nowParts() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function prevParts(year: number, month: number) {
  if (month === 1) return { year: year - 1, month: 12 };
  return { year, month: month - 1 };
}

function formatBags(count: number): string {
  return `${count.toLocaleString("en-IN")} bag${count === 1 ? "" : "s"}`;
}

const DASH_TABLE = "v2-data-table dashboard-summary-table w-full min-w-[26rem] text-sm";
const DASH_LABEL_TH = "dashboard-summary-table__label px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide";
const DASH_NUM_TH = "dashboard-summary-table__num px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide";
const DASH_LABEL_TD = "dashboard-summary-table__label px-3 py-2.5 text-ink";
const DASH_NUM_TD = "dashboard-summary-table__num px-3 py-2.5 text-right v2-mono text-sm tabular-nums";

function DashboardLabelCell({ children, title }: { children: string; title?: string }) {
  return (
    <td className={DASH_LABEL_TD} title={title ?? children}>
      <span className="block truncate font-medium">{children}</span>
    </td>
  );
}

export default function DashboardPage() {
  const initial = nowParts();
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [groupBy, setGroupBy] = useState<"product" | "product_brand">("product_brand");
  const [billType, setBillType] = useState<BillTypeParam>("sales");
  const [productCustomerId, setProductCustomerId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [summary, setSummary] = useState<BusinessSummary | null>(null);
  const [fiscalYear, setFiscalYear] = useState<FiscalYearSummary | null>(null);
  const [byProduct, setByProduct] = useState<SalesByProduct | null>(null);
  const [byCustomer, setByCustomer] = useState<SalesByCustomer | null>(null);
  const [byLocation, setByLocation] = useState<SalesByLocation | null>(null);
  const [jobWork, setJobWork] = useState<JobWorkByProduct | null>(null);

  const params = useMemo(() => ({ year, month }), [year, month]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const bundle = await reportsApi.dashboardBundle({
        ...params,
        bill_type: billType,
        group_by: groupBy,
        customer_id: productCustomerId,
      });
      setSummary(bundle.summary);
      setFiscalYear(bundle.fiscal_year);
      setByProduct(bundle.by_product);
      setByCustomer(bundle.by_customer);
      setByLocation(bundle.by_location);
      setJobWork(bundle.job_work);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [params, groupBy, billType, productCustomerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const empty =
    !loading &&
    summary != null &&
    summary.sales.bill_count === 0 &&
    summary.purchase.bill_count === 0;

  const productBreakdownTotals = useMemo(() => {
    if (!byProduct?.rows.length) return null;
    const kg = byProduct.rows.reduce((sum, r) => sum + Number(r.quantity_kg), 0);
    const bags = byProduct.rows.reduce((sum, r) => sum + r.bag_count, 0);
    return { kg, bags };
  }, [byProduct]);

  /** Share of ordered quantity, so the bar matches the qty column beside it. */
  const qtyShare = (kg: string) => {
    const total = productBreakdownTotals?.kg ?? 0;
    return total > 0 ? (Number(kg) / total) * 100 : 0;
  };

  const productBreakdownTitle =
    billType === "sales" ? "Product sales breakdown" : "Product purchase breakdown";
  const billTypeLabel = billType === "sales" ? "Sales" : "Purchase";

  const partyTableTitle = billType === "sales" ? "Top customers" : "Top suppliers";
  const partyColumnLabel = billType === "sales" ? "Customer" : "Supplier";

  const setThisMonth = () => {
    const n = nowParts();
    setYear(n.year);
    setMonth(n.month);
  };
  const setPreviousMonth = () => {
    const p = prevParts(year, month);
    setYear(p.year);
    setMonth(p.month);
  };

  const exportCsv = async () => {
    const base = import.meta.env.VITE_API_URL ?? "";
    const q = new URLSearchParams({
      year: String(year),
      month: String(month),
      group_by: groupBy,
      bill_type: billType,
    });
    if (productCustomerId != null) q.set("customer_id", String(productCustomerId));
    const res = await fetch(`${base}/api/reports/bills-export?${q}`, { credentials: "include" });
    if (!res.ok) throw new Error("Export failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${billType}-${year}-${String(month).padStart(2, "0")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const onFilterSubmit = (e: FormEvent) => {
    e.preventDefault();
    void load();
  };

  const grossProfit = summary ? Number(summary.gross_profit) : 0;
  const netProfit = summary ? Number(summary.net_profit) : 0;
  const profitTone = grossProfit >= 0 ? "success" : "danger";
  const netProfitTone = netProfit >= 0 ? "success" : "danger";
  const fyGross = fiscalYear ? Number(fiscalYear.gross_profit) : 0;
  const fyNet = fiscalYear ? Number(fiscalYear.net_profit) : 0;
  const fyProfitTone = fyGross >= 0 ? "success" : "danger";
  const fyNetTone = fyNet >= 0 ? "success" : "danger";
  const monthSw = summary ? Number(summary.self_withdrawal_total ?? 0) : 0;
  const fySw = fiscalYear ? Number(fiscalYear.self_withdrawal_total ?? 0) : 0;

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-3.5 w-3.5" />
            {MONTHS[month - 1]} {year}
          </span>
        }
        title="Business dashboard"
        subtitle="Month sales and purchase, cash-book expenses (Self Withdrawal shown separately), and product quantities ordered."
        actions={
          <>
            <Button variant="secondary" onClick={setPreviousMonth}>
              ← Prev
            </Button>
            <Button variant="secondary" onClick={setThisMonth}>
              This month
            </Button>
            <Button
              variant="secondary"
              leftIcon={<Download className="h-4 w-4" />}
              onClick={() => void exportCsv()}
              disabled={empty}
            >
              Export
            </Button>
          </>
        }
      />

      <Card className="mb-6">
        <form className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 lg:grid-cols-5" onSubmit={onFilterSubmit}>
          <label className="text-xs font-medium text-ink-muted">
            Year
            <Select
              className="mt-1"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            >
              {[year - 1, year, year + 1].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-xs font-medium text-ink-muted">
            Month
            <Select
              className="mt-1"
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
            >
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-xs font-medium text-ink-muted">
            Bill type
            <Select
              className="mt-1"
              value={billType}
              onChange={(e) => setBillType(e.target.value as BillTypeParam)}
            >
              <option value="sales">Sales</option>
              <option value="purchase">Purchase</option>
            </Select>
          </label>
          <label className="text-xs font-medium text-ink-muted">
            Product grouping
            <Select
              className="mt-1"
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as "product" | "product_brand")}
            >
              <option value="product">Product only</option>
              <option value="product_brand">Product + brand</option>
            </Select>
          </label>
          <div className="flex items-end">
            <Button block type="submit">
              Apply
            </Button>
          </div>
        </form>
      </Card>

      {error && (
        <Banner tone="danger" title="Couldn’t load dashboard" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {loading ? (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <CardBody>
                <Skeleton className="mb-3 h-3 w-20" />
                <Skeleton className="mb-2 h-8 w-32" />
                <Skeleton className="h-3 w-16" />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : summary ? (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <Stat
              tone="primary"
              label="Sales (this month)"
              value={formatInrCompact(summary.sales.bill_amount)}
              icon={<IndianRupee />}
              footer={
                <span>
                  {summary.sales.bill_count} bill{summary.sales.bill_count === 1 ? "" : "s"} ·{" "}
                  {formatQtyKg(summary.sales.qty_ordered_kg)}
                </span>
              }
            />
            <Stat
              tone="success"
              label="Purchase (this month)"
              value={formatInrCompact(summary.purchase.bill_amount)}
              icon={<PackagePlus />}
              footer={
                <span>
                  {summary.purchase.bill_count} bill{summary.purchase.bill_count === 1 ? "" : "s"} ·{" "}
                  {formatQtyKg(summary.purchase.qty_ordered_kg)}
                </span>
              }
            />
            <Stat
              tone="warning"
              label="Expenses (cash book)"
              value={formatInrCompact(summary.expense_total)}
              icon={<Wallet />}
              footer={
                <span>
                  Excludes Self Withdrawal
                  {monthSw > 0 ? ` · SW ${formatInrCompact(summary.self_withdrawal_total)}` : ""}
                </span>
              }
            />
            <Stat
              tone={profitTone}
              label="Gross profit (month)"
              value={formatInrCompact(summary.gross_profit)}
              icon={<TrendingUp />}
              footer={<span>Sales − purchase − expenses (excl. SW)</span>}
            />
            <Stat
              tone={netProfitTone}
              label="Net profit (month)"
              value={formatInrCompact(summary.net_profit)}
              icon={<TrendingDown />}
              footer={<span>Sales − purchase − all expenses (incl. SW)</span>}
            />
          </div>

          {fiscalYear && (
            <Card className="mb-6">
              <CardHeader
                title={`${fiscalYear.label} year report`}
                subtitle={`1 Apr ${fiscalYear.start_year} – 31 Mar ${fiscalYear.end_year} · Gross excl. Self Withdrawal · Net includes Self Withdrawal`}
              />
              <CardBody className="space-y-5 pt-0">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  <Stat
                    tone="primary"
                    label="FY sales"
                    value={formatInrCompact(fiscalYear.sales.bill_amount)}
                    icon={<IndianRupee />}
                    footer={
                      <span>
                        {fiscalYear.sales.bill_count} bill
                        {fiscalYear.sales.bill_count === 1 ? "" : "s"}
                      </span>
                    }
                  />
                  <Stat
                    tone="success"
                    label="FY purchase"
                    value={formatInrCompact(fiscalYear.purchase.bill_amount)}
                    icon={<PackagePlus />}
                    footer={
                      <span>
                        {fiscalYear.purchase.bill_count} bill
                        {fiscalYear.purchase.bill_count === 1 ? "" : "s"}
                      </span>
                    }
                  />
                  <Stat
                    tone="warning"
                    label="FY expenses"
                    value={formatInrCompact(fiscalYear.expense_total)}
                    icon={<Wallet />}
                    footer={
                      <span>
                        Excl. Self Withdrawal
                        {fySw > 0 ? ` · SW ${formatInrCompact(fiscalYear.self_withdrawal_total)}` : ""}
                      </span>
                    }
                  />
                  <Stat
                    tone={fyProfitTone}
                    label="FY gross profit"
                    value={formatInrCompact(fiscalYear.gross_profit)}
                    icon={<TrendingUp />}
                    footer={<span>Sales − purchase − expenses (excl. SW)</span>}
                  />
                  <Stat
                    tone={fyNetTone}
                    label="FY net profit"
                    value={formatInrCompact(fiscalYear.net_profit)}
                    icon={<TrendingDown />}
                    footer={<span>Sales − purchase − all expenses (incl. SW)</span>}
                  />
                </div>
                <div className="overflow-x-auto">
                  <table className={DASH_TABLE}>
                    <thead className="bg-surface-subtle text-ink-subtle">
                      <tr>
                        <th className={DASH_LABEL_TH}>Month</th>
                        <th className={DASH_NUM_TH}>Sales</th>
                        <th className={DASH_NUM_TH}>Purchase</th>
                        <th className={DASH_NUM_TH}>Expense</th>
                        <th className={DASH_NUM_TH}>Self WD</th>
                        <th className={DASH_NUM_TH}>Gross profit</th>
                        <th className={DASH_NUM_TH}>Net profit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fiscalYear.months.map((row) => {
                        const gp = Number(row.gross_profit);
                        const np = Number(row.net_profit);
                        return (
                          <tr key={`${row.year}-${row.month}`} className="border-t border-line/70">
                            <td className={DASH_LABEL_TD}>
                              {MONTHS[row.month - 1]} {row.year}
                            </td>
                            <td className={DASH_NUM_TD}>{formatInr(row.sales_amount)}</td>
                            <td className={DASH_NUM_TD}>{formatInr(row.purchase_amount)}</td>
                            <td className={DASH_NUM_TD}>{formatInr(row.expense_total)}</td>
                            <td className={DASH_NUM_TD}>{formatInr(row.self_withdrawal_total)}</td>
                            <td
                              className={cn(
                                DASH_NUM_TD,
                                "font-semibold",
                                gp >= 0 ? "text-accent-700 dark:text-accent-300" : "text-danger-700 dark:text-danger-300"
                              )}
                            >
                              {formatInr(row.gross_profit)}
                            </td>
                            <td
                              className={cn(
                                DASH_NUM_TD,
                                "font-semibold",
                                np >= 0 ? "text-accent-700 dark:text-accent-300" : "text-danger-700 dark:text-danger-300"
                              )}
                            >
                              {formatInr(row.net_profit)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-line bg-surface-subtle font-semibold">
                        <td className={DASH_LABEL_TD}>FY total</td>
                        <td className={DASH_NUM_TD}>{formatInr(fiscalYear.sales.bill_amount)}</td>
                        <td className={DASH_NUM_TD}>{formatInr(fiscalYear.purchase.bill_amount)}</td>
                        <td className={DASH_NUM_TD}>{formatInr(fiscalYear.expense_total)}</td>
                        <td className={DASH_NUM_TD}>{formatInr(fiscalYear.self_withdrawal_total)}</td>
                        <td
                          className={cn(
                            DASH_NUM_TD,
                            fyGross >= 0 ? "text-accent-700 dark:text-accent-300" : "text-danger-700 dark:text-danger-300"
                          )}
                        >
                          {formatInr(fiscalYear.gross_profit)}
                        </td>
                        <td
                          className={cn(
                            DASH_NUM_TD,
                            fyNet >= 0 ? "text-accent-700 dark:text-accent-300" : "text-danger-700 dark:text-danger-300"
                          )}
                        >
                          {formatInr(fiscalYear.net_profit)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </CardBody>
            </Card>
          )}

          {empty ? (
            <EmptyState
              icon={<Receipt />}
              title={`No finalized bills dated in ${MONTHS[month - 1]} ${year}`}
              description="Create a bill to start tracking ordered quantities for this month."
              action={
                <Link
                  to="/sales-bills/new"
                  className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-soft hover:bg-primary-700"
                >
                  <Plus className="h-4 w-4" /> Create sales bill
                </Link>
              }
            />
          ) : (
            <>
              <Card className="mb-6">
                <CardHeader
                  title={productBreakdownTitle}
                  subtitle={
                    productBreakdownTotals
                      ? `Total ${formatQtyKg(productBreakdownTotals.kg)} · ${formatBags(productBreakdownTotals.bags)}`
                      : "Ordered quantity by product and brand"
                  }
                  actions={
                    <div className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto">
                      <SegmentedControl
                        ariaLabel="Bill type"
                        value={billType}
                        onChange={(v) => setBillType(v)}
                        options={[
                          { value: "sales", label: "Sales" },
                          { value: "purchase", label: "Purchase" },
                        ]}
                      />
                      <div className="w-full sm:w-56">
                        <AsyncSearchCombobox
                          value={productCustomerId}
                          onChange={(id) => setProductCustomerId(id)}
                          searchFn={searchCustomers}
                          placeholder={billType === "sales" ? "All customers" : "All suppliers"}
                          emptyText={billType === "sales" ? "No matching customer" : "No matching supplier"}
                        />
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        leftIcon={<BarChart3 className="h-4 w-4" />}
                        onClick={() =>
                          setGroupBy(groupBy === "product" ? "product_brand" : "product")
                        }
                      >
                        Group: {groupBy === "product" ? "Product" : "Product + brand"}
                      </Button>
                    </div>
                  }
                />
                <CardBody className="pt-0">
                  <div className="overflow-x-auto">
                    <table className="v2-data-table min-w-full text-base">
                      <thead className="bg-surface-subtle text-base font-semibold uppercase tracking-wide text-ink-subtle">
                        <tr>
                          <th className="px-5 py-3.5 text-left font-medium">Product</th>
                          {groupBy === "product_brand" && (
                            <th className="px-5 py-3.5 text-left font-medium">Brand</th>
                          )}
                          <th className="px-5 py-3.5 text-left font-medium">Type</th>
                          <th className="px-5 py-3.5 text-right font-medium">Qty ordered</th>
                          <th className="px-5 py-3.5 text-right font-medium">Bags</th>
                          <th className="px-5 py-3.5 text-left font-medium">Share of qty</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(byProduct?.rows ?? []).map((r, i) => {
                          const share = qtyShare(r.quantity_kg);
                          return (
                            <tr
                              key={`${r.product_id}-${r.brand_id ?? 0}-${i}`}
                              className="border-t border-line/70"
                            >
                              <td className="px-5 py-3.5 text-ink">{r.product_name}</td>
                              {groupBy === "product_brand" && (
                                <td className="px-5 py-3.5 text-ink-muted">{r.brand_name ?? "—"}</td>
                              )}
                              <td className="px-5 py-3.5">
                                <span
                                  className={cn(
                                    "inline-flex rounded-full px-2 py-0.5 text-xs font-semibold",
                                    billType === "sales"
                                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-200"
                                      : "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200"
                                  )}
                                >
                                  {billTypeLabel}
                                </span>
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono">{formatQtyKg(r.quantity_kg)}</td>
                              <td className="px-5 py-3.5 text-right v2-mono">{r.bag_count}</td>
                              <td className="w-40 px-5 py-3.5">
                                <div className="flex items-center gap-2">
                                  <div className="h-2 w-full min-w-16 overflow-hidden rounded-full bg-surface-muted">
                                    <div
                                      className={cn(
                                        "h-full rounded-full",
                                        billType === "sales" ? "bg-primary-500" : "bg-emerald-500"
                                      )}
                                      style={{ width: `${Math.min(100, Math.max(share, share > 0 ? 3 : 0))}%` }}
                                    />
                                  </div>
                                  <span className="v2-mono w-12 shrink-0 text-right text-xs tabular-nums text-ink-muted">
                                    {share.toFixed(1)}%
                                  </span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                        {(byProduct?.rows ?? []).length === 0 && (
                          <tr>
                            <td
                              colSpan={groupBy === "product_brand" ? 6 : 5}
                              className="px-3 py-6 text-center text-sm text-ink-subtle"
                            >
                              No data
                            </td>
                          </tr>
                        )}
                      </tbody>
                      {byProduct && productBreakdownTotals && (
                        <tfoot>
                          <tr className="border-t-2 border-line bg-surface-subtle font-semibold">
                            <td
                              colSpan={groupBy === "product_brand" ? 3 : 2}
                              className="px-5 py-3.5 text-sm text-ink"
                            >
                              Total {billTypeLabel.toLowerCase()}
                            </td>
                            <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                              {formatQtyKg(productBreakdownTotals.kg)}
                            </td>
                            <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                              {productBreakdownTotals.bags.toLocaleString("en-IN")}
                            </td>
                            <td />
                          </tr>
                        </tfoot>
                      )}
                    </table>
                  </div>
                </CardBody>
              </Card>

              <Card className="mb-6">
                <CardHeader
                  title="Job order breakdown"
                  subtitle={
                    jobWork
                      ? `${jobWork.order_count} job order${jobWork.order_count === 1 ? "" : "s"} · Ordered ${formatQtyKg(jobWork.ordered_quantity_kg)} · Received ${formatQtyKg(jobWork.received_quantity_kg)}`
                      : "Quantities sent for job work this month"
                  }
                  actions={
                    <Link to="/job-work">
                      <Button variant="secondary" size="sm" leftIcon={<Hammer className="h-4 w-4" />}>
                        Open job work
                      </Button>
                    </Link>
                  }
                />
                <CardBody className="pt-0">
                  <div className="overflow-x-auto">
                    <table className="v2-data-table min-w-full text-base">
                      <thead className="bg-surface-subtle text-base font-semibold uppercase tracking-wide text-ink-subtle">
                        <tr>
                          <th className="px-5 py-3.5 text-left font-medium">Product</th>
                          {groupBy === "product_brand" && (
                            <th className="px-5 py-3.5 text-left font-medium">Brand</th>
                          )}
                            <th className="px-5 py-3.5 text-right font-medium">Qty ordered</th>
                            <th className="px-5 py-3.5 text-right font-medium">Bags</th>
                            <th className="px-5 py-3.5 text-right font-medium">Received</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(jobWork?.rows ?? []).map((r, i) => (
                            <tr
                              key={`jw-${r.product_id}-${r.brand_id ?? 0}-${i}`}
                              className="border-t border-line/70"
                            >
                              <td className="px-5 py-3.5 text-ink">{r.product_name}</td>
                              {groupBy === "product_brand" && (
                                <td className="px-5 py-3.5 text-ink-muted">{r.brand_name ?? "—"}</td>
                              )}
                              <td className="px-5 py-3.5 text-right v2-mono">
                                {formatQtyKg(r.ordered_quantity_kg)}
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono">{r.ordered_bags}</td>
                              <td className="px-5 py-3.5 text-right v2-mono">
                                {formatQtyKg(r.received_quantity_kg)}
                              </td>
                            </tr>
                          ))}
                          {(jobWork?.rows ?? []).length === 0 && (
                            <tr>
                              <td
                                colSpan={groupBy === "product_brand" ? 5 : 4}
                                className="px-3 py-6 text-center text-sm text-ink-subtle"
                              >
                                No job orders this month
                              </td>
                            </tr>
                          )}
                        </tbody>
                        {jobWork && jobWork.rows.length > 0 && (
                          <tfoot>
                            <tr className="border-t-2 border-line bg-surface-subtle font-semibold">
                              <td
                                colSpan={groupBy === "product_brand" ? 2 : 1}
                                className="px-5 py-3.5 text-sm text-ink"
                              >
                                Total job work
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                                {formatQtyKg(jobWork.ordered_quantity_kg)}
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                                {jobWork.ordered_bags.toLocaleString("en-IN")}
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                                {formatQtyKg(jobWork.received_quantity_kg)}
                              </td>
                            </tr>
                          </tfoot>
                        )}
                    </table>
                  </div>
                </CardBody>
              </Card>

              <div className="mb-6 grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader title={partyTableTitle} subtitle="By quantity ordered" />
                  <CardBody className="pt-0">
                    <div className="overflow-x-auto -mx-1 px-1">
                      <table className={DASH_TABLE}>
                        <thead className="bg-surface-subtle text-ink-subtle">
                          <tr>
                            <th className={DASH_LABEL_TH}>{partyColumnLabel}</th>
                            <th className={DASH_NUM_TH}>Bills</th>
                            <th className={DASH_NUM_TH}>Qty</th>
                            <th className={DASH_NUM_TH}>Share</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(byCustomer?.rows ?? []).map((r) => (
                            <tr key={r.customer_id} className="border-t border-line/70">
                              <DashboardLabelCell title={r.customer_name}>{r.customer_name}</DashboardLabelCell>
                              <td className={DASH_NUM_TD}>{r.bill_count}</td>
                              <td className={DASH_NUM_TD}>{formatQtyKg(r.quantity_kg)}</td>
                              <td className={DASH_NUM_TD}>{Number(r.share_percent).toFixed(1)}%</td>
                            </tr>
                          ))}
                          {(byCustomer?.rows ?? []).length === 0 && (
                            <tr>
                              <td colSpan={4} className="px-3 py-6 text-center text-sm text-ink-subtle">
                                No data
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title={`${billTypeLabel} by location`} subtitle="Qty ordered" />
                  <CardBody className="pt-0">
                    <div className="overflow-x-auto -mx-1 px-1">
                      <table className={DASH_TABLE}>
                        <thead className="bg-surface-subtle text-ink-subtle">
                          <tr>
                            <th className={DASH_LABEL_TH}>Location</th>
                            <th className={DASH_NUM_TH}>Bills</th>
                            <th className={DASH_NUM_TH}>Qty</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(byLocation?.rows ?? []).map((r, i) => (
                            <tr key={r.location_id ?? `loc-${i}`} className="border-t border-line/70">
                              <DashboardLabelCell title={r.location_name}>{r.location_name}</DashboardLabelCell>
                              <td className={DASH_NUM_TD}>{r.bill_count}</td>
                              <td className={DASH_NUM_TD}>{formatQtyKg(r.quantity_kg)}</td>
                            </tr>
                          ))}
                          {(byLocation?.rows ?? []).length === 0 && (
                            <tr>
                              <td colSpan={3} className="px-3 py-6 text-center text-sm text-ink-subtle">
                                No data
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </CardBody>
                </Card>
              </div>
            </>
          )}
        </>
      ) : null}

      <Card>
        <CardHeader title="Quick links" subtitle="Jump to common tasks across the app." />
        <CardBody>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ["/inventory", "Inventory"],
              ["/sales-bills", "Sales bills"],
              ["/purchase-bills", "Purchase bills"],
              ["/fulfillment", "Fulfillment"],
              ["/payments", "Payments"],
              ["/home", "All shortcuts"],
            ].map(([to, label]) => (
              <Link
                key={to}
                to={to}
                className="rounded-xl border border-line bg-surface px-5 py-3.5 text-center text-sm font-medium text-ink-muted hover:border-primary-300 hover:text-ink"
              >
                {label}
              </Link>
            ))}
          </div>
        </CardBody>
      </Card>
    </>
  );
}
