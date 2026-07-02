import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  Download,
  IndianRupee,
  Package,
  PackagePlus,
  Plus,
  ShoppingCart,
  TrendingUp,
  Weight,
} from "lucide-react";
import {
  reportsApi,
  type BillTypeParam,
  type BusinessCompare,
  type BusinessSummary,
  type DailyBillAmounts,
  type SalesByCustomer,
  type SalesByLocation,
  type SalesByProduct,
} from "../api/client";
import { formatInr, formatInrCompact, formatQtyKg } from "../lib/format";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Card, { CardBody, CardHeader } from "../components/ui/Card";
import Stat from "../components/ui/Stat";
import KpiSparkline from "../components/ui/KpiSparkline";
import Banner from "../components/ui/Banner";
import Select from "../components/ui/Select";
import SegmentedControl from "../components/ui/SegmentedControl";
import Skeleton from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
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

const SALES_COLOR = "#6366f1";
const PURCHASE_COLOR = "#10b981";
const PIE_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6", "#06b6d4", "#84cc16"];

function nowParts() {
  const d = new Date();
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function prevParts(year: number, month: number) {
  if (month === 1) return { year: year - 1, month: 12 };
  return { year, month: month - 1 };
}

function changeFromPct(v: string | null | undefined) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (Number.isNaN(n)) return null;
  return { value: n };
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [summary, setSummary] = useState<BusinessSummary | null>(null);
  const [compare, setCompare] = useState<BusinessCompare | null>(null);
  const [daily, setDaily] = useState<DailyBillAmounts | null>(null);
  const [byProduct, setByProduct] = useState<SalesByProduct | null>(null);
  const [byCustomer, setByCustomer] = useState<SalesByCustomer | null>(null);
  const [byLocation, setByLocation] = useState<SalesByLocation | null>(null);

  const params = useMemo(() => ({ year, month }), [year, month]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const bundle = await reportsApi.dashboardBundle({
        ...params,
        bill_type: billType,
        group_by: groupBy,
      });
      setSummary(bundle.summary);
      setCompare(bundle.compare);
      setDaily(bundle.daily);
      setByProduct(bundle.by_product);
      setByCustomer(bundle.by_customer);
      setByLocation(bundle.by_location);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [params, groupBy, billType]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartDaily = useMemo(
    () =>
      (daily?.rows ?? [])
        .filter((r) => r.sales_bill_count > 0 || r.purchase_bill_count > 0)
        .map((r) => ({
          day: r.day,
          sales: Number(r.sales_amount),
          purchase: Number(r.purchase_amount),
        })),
    [daily]
  );

  const sparkSales = useMemo(
    () => (daily?.rows ?? []).map((r) => ({ x: r.day, y: Number(r.sales_amount) })),
    [daily]
  );
  const sparkPurchase = useMemo(
    () => (daily?.rows ?? []).map((r) => ({ x: r.day, y: Number(r.purchase_amount) })),
    [daily]
  );
  const sparkSalesQty = useMemo(
    () =>
      (daily?.rows ?? []).map((r) => ({
        x: r.day,
        y: Math.max(0, Number(r.sales_amount) / 50),
      })),
    [daily]
  );
  const sparkPurchaseQty = useMemo(
    () =>
      (daily?.rows ?? []).map((r) => ({
        x: r.day,
        y: Math.max(0, Number(r.purchase_amount) / 50),
      })),
    [daily]
  );

  const productPie = useMemo(
    () =>
      (byProduct?.rows ?? []).slice(0, 6).map((r) => ({
        name:
          groupBy === "product_brand" && r.brand_name
            ? `${r.product_name} · ${r.brand_name}`
            : r.product_name,
        value: Number(r.amount),
      })),
    [byProduct, groupBy]
  );

  const empty =
    !loading &&
    summary != null &&
    summary.sales.bill_count === 0 &&
    summary.purchase.bill_count === 0;

  const productBreakdownTotals = useMemo(() => {
    if (!byProduct?.rows.length) return null;
    const kg = byProduct.rows.reduce((sum, r) => sum + Number(r.quantity_kg), 0);
    const bags = byProduct.rows.reduce((sum, r) => sum + r.bag_count, 0);
    return {
      kg,
      bags,
      lineAmount: byProduct.lines_subtotal,
      billTotal: byProduct.bills_grand_total,
    };
  }, [byProduct]);

  const monthTotals = useMemo(() => {
    if (!summary) return null;
    return {
      kg: Number(summary.sales.qty_ordered_kg) + Number(summary.purchase.qty_ordered_kg),
      bags: (summary.sales.bags_ordered ?? 0) + (summary.purchase.bags_ordered ?? 0),
    };
  }, [summary]);

  const productBreakdownTitle =
    billType === "sales" ? "Product sales breakdown" : "Product purchase breakdown";

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
        subtitle="Bills dated in the selected month — ordered quantities and bill amounts. Delivery and payments may occur later."
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
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
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
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Stat
              tone="primary"
              label="Sales bill amount"
              value={formatInrCompact(summary.sales.bill_amount)}
              icon={<IndianRupee />}
              delta={compare ? changeFromPct(compare.change_percent.sales_bill_amount) : null}
              footer={
                <span>{summary.sales.bill_count} bill{summary.sales.bill_count === 1 ? "" : "s"}</span>
              }
              sparkline={<KpiSparkline data={sparkSales} color={SALES_COLOR} gradientId="kpi-s-amt" />}
            />
            <Stat
              tone="success"
              label="Purchase bill amount"
              value={formatInrCompact(summary.purchase.bill_amount)}
              icon={<PackagePlus />}
              delta={compare ? changeFromPct(compare.change_percent.purchase_bill_amount) : null}
              footer={
                <span>{summary.purchase.bill_count} bill{summary.purchase.bill_count === 1 ? "" : "s"}</span>
              }
              sparkline={<KpiSparkline data={sparkPurchase} color={PURCHASE_COLOR} gradientId="kpi-p-amt" />}
            />
            <Stat
              tone="warning"
              label="Sales qty ordered"
              value={formatQtyKg(summary.sales.qty_ordered_kg)}
              icon={<Weight />}
              delta={compare ? changeFromPct(compare.change_percent.sales_qty_ordered_kg) : null}
              footer={<span>{formatBags(summary.sales.bags_ordered ?? 0)}</span>}
              sparkline={<KpiSparkline data={sparkSalesQty} color="#f59e0b" gradientId="kpi-s-qty" />}
            />
            <Stat
              tone="info"
              label="Purchase qty ordered"
              value={formatQtyKg(summary.purchase.qty_ordered_kg)}
              icon={<ShoppingCart />}
              delta={compare ? changeFromPct(compare.change_percent.purchase_qty_ordered_kg) : null}
              footer={<span>{formatBags(summary.purchase.bags_ordered ?? 0)}</span>}
              sparkline={<KpiSparkline data={sparkPurchaseQty} color="#06b6d4" gradientId="kpi-p-qty" />}
            />
            {monthTotals ? (
              <>
                <Stat
                  tone="neutral"
                  label="Total qty ordered"
                  value={formatQtyKg(monthTotals.kg)}
                  icon={<Weight />}
                  footer={
                    <span>
                      Sales {formatQtyKg(summary.sales.qty_ordered_kg)} · Purchase{" "}
                      {formatQtyKg(summary.purchase.qty_ordered_kg)}
                    </span>
                  }
                />
                <Stat
                  tone="muted"
                  label="Total bags ordered"
                  value={monthTotals.bags.toLocaleString("en-IN")}
                  unit="bags"
                  icon={<Package />}
                  footer={
                    <span>
                      Sales {formatBags(summary.sales.bags_ordered ?? 0)} · Purchase{" "}
                      {formatBags(summary.purchase.bags_ordered ?? 0)}
                    </span>
                  }
                />
              </>
            ) : null}
          </div>

          {empty ? (
            <EmptyState
              icon={<TrendingUp />}
              title={`No finalized bills dated in ${MONTHS[month - 1]} ${year}`}
              description="Create a bill to start tracking ordered quantities and bill amounts for this month."
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
              <div className="mb-6 grid gap-4 lg:grid-cols-3">
                <Card className="lg:col-span-2">
                  <CardHeader title="Daily bill amounts" subtitle={`${MONTHS[month - 1]} ${year}`} />
                  <CardBody>
                    <div className="h-64 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartDaily}>
                          <defs>
                            <linearGradient id="s-area" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={SALES_COLOR} stopOpacity={0.35} />
                              <stop offset="100%" stopColor={SALES_COLOR} stopOpacity={0} />
                            </linearGradient>
                            <linearGradient id="p-area" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={PURCHASE_COLOR} stopOpacity={0.35} />
                              <stop offset="100%" stopColor={PURCHASE_COLOR} stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                          <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="rgb(var(--ink-muted))" />
                          <YAxis tick={{ fontSize: 11 }} stroke="rgb(var(--ink-muted))" />
                          <Tooltip formatter={(v: number) => formatInr(v)} />
                          <Legend wrapperStyle={{ fontSize: 12 }} />
                          <Area
                            type="monotone"
                            dataKey="sales"
                            name="Sales"
                            stroke={SALES_COLOR}
                            fill="url(#s-area)"
                            strokeWidth={2}
                          />
                          <Area
                            type="monotone"
                            dataKey="purchase"
                            name="Purchase"
                            stroke={PURCHASE_COLOR}
                            fill="url(#p-area)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader
                    title={`Top products (${billType})`}
                    actions={
                      <SegmentedControl
                        ariaLabel="Bill type"
                        value={billType}
                        onChange={(v) => setBillType(v)}
                        options={[
                          { value: "sales", label: "Sales" },
                          { value: "purchase", label: "Purchase" },
                        ]}
                      />
                    }
                  />
                  <CardBody>
                    {productPie.length === 0 ? (
                      <p className="py-12 text-center text-sm text-ink-subtle">No data for this filter.</p>
                    ) : (
                      <div className="h-64">
                        <ResponsiveContainer>
                          <PieChart>
                            <Pie
                              data={productPie}
                              dataKey="value"
                              nameKey="name"
                              innerRadius={48}
                              outerRadius={86}
                              paddingAngle={3}
                            >
                              {productPie.map((_, i) => (
                                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v: number) => formatInr(v)} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </CardBody>
                </Card>
              </div>

              {compare && (
                <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {(
                    [
                      ["Sales bill amount", compare.current.sales_bill_amount, compare.previous.sales_bill_amount, compare.change_percent.sales_bill_amount, "money"],
                      ["Purchase bill amount", compare.current.purchase_bill_amount, compare.previous.purchase_bill_amount, compare.change_percent.purchase_bill_amount, "money"],
                      ["Sales qty ordered", compare.current.sales_qty_ordered_kg, compare.previous.sales_qty_ordered_kg, compare.change_percent.sales_qty_ordered_kg, "kg"],
                      ["Purchase qty ordered", compare.current.purchase_qty_ordered_kg, compare.previous.purchase_qty_ordered_kg, compare.change_percent.purchase_qty_ordered_kg, "kg"],
                    ] as const
                  ).map(([label, cur, prev, chg]) => {
                    const ch = chg == null ? null : Number(chg);
                    const isPos = ch != null && ch >= 0;
                    return (
                      <Card key={label}>
                        <CardBody>
                          <p className="text-xs font-medium uppercase tracking-wider text-ink-subtle">{label}</p>
                          <p className="mt-1 v2-mono whitespace-nowrap text-lg font-semibold tabular-nums text-ink">
                            {String(cur).includes("kg") ? cur : (label.endsWith("ordered") ? formatQtyKg(String(cur)) : formatInr(String(cur)))}
                          </p>
                          <p className="mt-1 inline-flex flex-nowrap items-center gap-1 text-xs text-ink-subtle">
                            Prev{" "}
                            <span className="v2-mono whitespace-nowrap tabular-nums">
                              {label.endsWith("ordered") ? formatQtyKg(String(prev)) : formatInr(String(prev))}
                            </span>
                            {ch != null && (
                              <span
                                className={cn(
                                  "ml-1 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                                  isPos
                                    ? "bg-accent-50 text-accent-700 dark:bg-accent-900/30 dark:text-accent-200"
                                    : "bg-danger-50 text-danger-700 dark:bg-danger-900/30 dark:text-danger-200"
                                )}
                              >
                                {isPos ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                                {Math.abs(ch).toFixed(1)}%
                              </span>
                            )}
                          </p>
                        </CardBody>
                      </Card>
                    );
                  })}
                </div>
              )}

              <div className="mb-6 grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader title={partyTableTitle} subtitle="By bill amount" />
                  <CardBody className="pt-0">
                    <div className="overflow-x-auto -mx-1 px-1">
                      <table className={DASH_TABLE}>
                        <thead className="bg-surface-subtle text-ink-subtle">
                          <tr>
                            <th className={DASH_LABEL_TH}>{partyColumnLabel}</th>
                            <th className={DASH_NUM_TH}>Bills</th>
                            <th className={DASH_NUM_TH}>Qty</th>
                            <th className={DASH_NUM_TH}>Amount</th>
                            <th className={DASH_NUM_TH}>Share</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(byCustomer?.rows ?? []).map((r) => (
                            <tr key={r.customer_id} className="border-t border-line/70">
                              <DashboardLabelCell title={r.customer_name}>{r.customer_name}</DashboardLabelCell>
                              <td className={DASH_NUM_TD}>{r.bill_count}</td>
                              <td className={DASH_NUM_TD}>{formatQtyKg(r.quantity_kg)}</td>
                              <td className={DASH_NUM_TD}>{formatInr(r.amount)}</td>
                              <td className={DASH_NUM_TD}>{Number(r.share_percent).toFixed(1)}%</td>
                            </tr>
                          ))}
                          {(byCustomer?.rows ?? []).length === 0 && (
                            <tr>
                              <td colSpan={5} className="px-3 py-6 text-center text-sm text-ink-subtle">
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
                  <CardHeader title={`${billType === "sales" ? "Sales" : "Purchase"} by location`} subtitle="Bill amount and qty ordered" />
                  <CardBody className="pt-0">
                    <div className="overflow-x-auto -mx-1 px-1">
                      <table className={DASH_TABLE}>
                        <thead className="bg-surface-subtle text-ink-subtle">
                          <tr>
                            <th className={DASH_LABEL_TH}>Location</th>
                            <th className={DASH_NUM_TH}>Bills</th>
                            <th className={DASH_NUM_TH}>Qty</th>
                            <th className={DASH_NUM_TH}>Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(byLocation?.rows ?? []).map((r, i) => (
                            <tr key={r.location_id ?? `loc-${i}`} className="border-t border-line/70">
                              <DashboardLabelCell title={r.location_name}>{r.location_name}</DashboardLabelCell>
                              <td className={DASH_NUM_TD}>{r.bill_count}</td>
                              <td className={DASH_NUM_TD}>{formatQtyKg(r.quantity_kg)}</td>
                              <td className={DASH_NUM_TD}>{formatInr(r.amount)}</td>
                            </tr>
                          ))}
                          {(byLocation?.rows ?? []).length === 0 && (
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
              </div>

              <Card className="mb-6">
                <CardHeader
                  title={productBreakdownTitle}
                  subtitle={
                    productBreakdownTotals
                      ? billType === "sales"
                        ? `Total sales ${formatInr(productBreakdownTotals.lineAmount)} · Total ${formatQtyKg(productBreakdownTotals.kg)} · ${formatBags(productBreakdownTotals.bags)}`
                        : `Total purchase ${formatInr(productBreakdownTotals.lineAmount)} · Total ${formatQtyKg(productBreakdownTotals.kg)} · ${formatBags(productBreakdownTotals.bags)}`
                      : "Line amount sums line totals (bill-level discount/adjustment not included)"
                  }
                  actions={
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
                          <th className="px-5 py-3.5 text-right font-medium">Qty ordered (kg)</th>
                          <th className="px-5 py-3.5 text-right font-medium">Bags</th>
                          <th className="px-5 py-3.5 text-right font-medium">Line amount</th>
                          <th className="px-5 py-3.5 text-right font-medium">Share</th>
                          <th className="px-5 py-3.5 text-right font-medium">Avg rate/kg</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(byProduct?.rows ?? []).map((r, i) => (
                          <tr
                            key={`${r.product_id}-${r.brand_id ?? 0}-${i}`}
                            className="border-t border-line/70"
                          >
                            <td className="px-5 py-3.5 text-ink">{r.product_name}</td>
                            {groupBy === "product_brand" && (
                              <td className="px-5 py-3.5 text-ink-muted">{r.brand_name ?? "—"}</td>
                            )}
                            <td className="px-5 py-3.5 text-right v2-mono">{formatQtyKg(r.quantity_kg)}</td>
                            <td className="px-5 py-3.5 text-right v2-mono">{r.bag_count}</td>
                            <td className="px-5 py-3.5 text-right v2-mono">{formatInr(r.amount)}</td>
                            <td className="px-5 py-3.5 text-right v2-mono">{Number(r.share_percent).toFixed(1)}%</td>
                            <td className="px-5 py-3.5 text-right v2-mono">{formatInr(r.avg_rate_per_kg)}</td>
                          </tr>
                        ))}
                        {(byProduct?.rows ?? []).length === 0 && (
                          <tr>
                            <td
                              colSpan={groupBy === "product_brand" ? 7 : 6}
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
                              colSpan={groupBy === "product_brand" ? 2 : 1}
                              className="px-5 py-3.5 text-sm text-ink"
                            >
                              {billType === "sales" ? "Total sales" : "Total purchase"}
                            </td>
                            <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                              {formatQtyKg(productBreakdownTotals.kg)}
                            </td>
                            <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                              {productBreakdownTotals.bags.toLocaleString("en-IN")}
                            </td>
                            <td className="px-5 py-3.5 text-right v2-mono whitespace-nowrap tabular-nums">
                              {formatInr(productBreakdownTotals.lineAmount)}
                            </td>
                            <td colSpan={2} />
                          </tr>
                          {productBreakdownTotals.lineAmount !== productBreakdownTotals.billTotal && (
                            <tr className="border-t border-line">
                              <td
                                colSpan={groupBy === "product_brand" ? 4 : 3}
                                className="px-5 py-3.5 text-sm font-medium text-ink-muted"
                              >
                                Bills grand total (incl. discount/adjustment)
                              </td>
                              <td className="px-5 py-3.5 text-right v2-mono font-semibold whitespace-nowrap tabular-nums">
                                {formatInr(productBreakdownTotals.billTotal)}
                              </td>
                              <td colSpan={2} />
                            </tr>
                          )}
                        </tfoot>
                      )}
                    </table>
                  </div>
                </CardBody>
              </Card>
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
