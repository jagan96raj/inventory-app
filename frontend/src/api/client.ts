/** Empty = use Vite proxy (/api → localhost:8000). Set VITE_API_URL for direct backend. */
const API = import.meta.env.VITE_API_URL ?? "";

export const EXPECTED_BILL_VERSION_HEADER = "X-Expected-Bill-Version";
export const VOID_AUTH_HEADER = "X-Void-Authorization";
export const IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";
export const DEFAULT_PAGE_LIMIT = 25;
export const MASTER_SEARCH_LIMIT = 30;
/** @deprecated Use async master search (MASTER_SEARCH_LIMIT) on forms instead of bulk mount loads. */
export const BULK_FETCH_LIMIT = 500;

export type PageOut<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type BillListItem = {
  id: number;
  bill_number: string;
  bill_type: "sales" | "purchase";
  bill_date: string;
  customer_id: number;
  customer_name?: string | null;
  location_id?: number | null;
  location_name?: string | null;
  grand_total: string;
  final_payable: string;
  amount_paid: string;
  amount_due: string;
  due_amount: string;
  payment_status: string;
  order_delivery_status: string;
  version: number;
  notes?: string | null;
};

export type BillsPage = PageOut<BillListItem> & {
  summary: {
    total_count: number;
    unpaid_count: number;
    total_due: string;
    pending_delivery_count: number;
  };
};

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function idempotencyHeaders(key: string, extra?: Record<string, string>): Record<string, string> {
  return { [IDEMPOTENCY_KEY_HEADER]: key, ...extra };
}

export function voidAuthHeaders(password: string, extra?: Record<string, string>): Record<string, string> {
  return { [VOID_AUTH_HEADER]: password, ...extra };
}

export function idempotencyVoidAuthHeaders(
  key: string,
  password: string,
  extra?: Record<string, string>
): Record<string, string> {
  return voidAuthHeaders(password, idempotencyHeaders(key, extra));
}

export function idempotencyHeadersOptionalAuth(
  key: string,
  authPassword?: string,
  extra?: Record<string, string>
): Record<string, string> {
  if (authPassword) return idempotencyVoidAuthHeaders(key, authPassword, extra);
  return idempotencyHeaders(key, extra);
}

export type AuthUser = {
  id: number;
  email: string;
  name?: string | null;
  picture_url?: string | null;
  role?: "owner" | "writer" | "stock_manager" | "factory_manager" | null;
  is_active?: boolean;
  company_id: number;
  company_name?: string | null;
};

type RequestOptions = RequestInit & { skipAuthRedirect?: boolean };

const AUTH_CREDENTIAL_PATHS = [
  "/api/auth/login",
  "/api/auth/signup",
  "/api/auth/otp-login",
  "/api/companies/register",
];

function isAuthCredentialRequest(path: string): boolean {
  return AUTH_CREDENTIAL_PATHS.some((p) => path === p || path.startsWith(`${p}?`));
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    let detail: unknown = body.detail ?? (typeof body === "string" ? body : fallback);
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg || d).join(", ");
    return String(detail);
  } catch {
    return fallback;
  }
}

function redirectToLogin() {
  if (window.location.pathname.startsWith("/login")) return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}`);
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  let res: Response;
  const { headers: extraHeaders, ...rest } = options ?? {};
  try {
    res = await fetch(`${API}${path}`, {
      credentials: "include",
      ...rest,
      // Force no HTTP cache (Electron/Chromium otherwise can serve stale GETs).
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        Pragma: "no-cache",
        ...extraHeaders,
      },
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start backend: uvicorn app.main:app --reload --port 8000. Run: alembic upgrade head"
    );
  }
  if (res.status === 401) {
    const detail = await readErrorDetail(res, "Not authenticated");
    if (isAuthCredentialRequest(path)) {
      throw new Error(detail);
    }
    if (!options?.skipAuthRedirect) redirectToLogin();
    throw new Error(detail);
  }
  if (res.status === 403) {
    let detail = "You do not have permission for this action.";
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg || d).join(", ");
    } catch {
      /* ignore */
    }
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("app:forbidden", { detail: String(detail) }));
    }
    throw new Error(String(detail));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? (typeof body === "string" ? body : JSON.stringify(body));
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg || d).join(", ");
    } catch {
      /* ignore */
    }
    if (res.status >= 500 && detail === "Internal Server Error") {
      detail =
        "Server error — something failed while saving. If this keeps happening, check that Docker Desktop is running and the backend is up, then try again.";
    }
    throw new Error(String(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      return star[1].trim();
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1];
  const plain = /filename=([^;]+)/i.exec(header);
  return plain?.[1]?.trim() || fallback;
}

async function downloadBlob(path: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      credentials: "include",
      cache: "no-store",
      headers: {
        "Cache-Control": "no-store",
        Pragma: "no-cache",
      },
    });
  } catch {
    throw new Error(
      "Cannot reach API. Start backend: uvicorn app.main:app --reload --port 8000."
    );
  }
  if (res.status === 401) {
    const detail = await readErrorDetail(res, "Not authenticated");
    redirectToLogin();
    throw new Error(detail);
  }
  if (res.status === 403) {
    let detail = "You do not have permission for this action.";
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("app:forbidden", { detail: String(detail) }));
    }
    throw new Error(String(detail));
  }
  if (!res.ok) {
    const detail = await readErrorDetail(res, res.statusText || "Backup failed");
    throw new Error(String(detail));
  }
  const blob = await res.blob();
  const filename = filenameFromContentDisposition(
    res.headers.get("Content-Disposition"),
    fallbackName
  );
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, options),
  post: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body), ...options }),
  put: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body), ...options }),
  patch: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body), ...options }),
  delete: (path: string, options?: RequestOptions) => request<void>(path, { method: "DELETE", ...options }),
};

export type Product = { id: number; product_name: string };
export type Brand = { id: number; name: string };
export type Location = {
  id: number;
  name: string;
  address_line: string | null;
  district: string | null;
  state: string | null;
  pin_code: string | null;
};
export type BagType = { id: number; name: string; weight_per_bag_kg: string; is_loose: boolean };
export type Customer = {
  id: number;
  name: string;
  address_line: string | null;
  district: string | null;
  state: string | null;
  pin_code: string | null;
  phone: string | null;
  alternate_phone: string | null;
  credit_balance: string;
  debit_balance: string;
};
export type CustomerPage = PageOut<Customer> & {
  credit_total: string;
  debit_total: string;
};
export type InventoryOwnerType = "owned" | "job_work";

export type InventoryRow = {
  id: number;
  product_id: number;
  brand_id: number;
  location_id: number;
  bag_type_id: number;
  owner_type?: InventoryOwnerType;
  customer_id?: number | null;
  customer_name?: string | null;
  loose_kg: string;
  total_quantity_kg: string;
  product_name?: string;
  brand_name?: string;
  location_name?: string;
  bag_type_name?: string;
};
export type BillLine = {
  id: number;
  product_id: number;
  brand_id: number;
  bag_type_id: number;
  ordered_bags: number;
  ordered_loose_kg: string;
  ordered_quantity_kg: string;
  rate_per_kg: string;
  line_total: string;
  line_delivery_status: string;
  net_delivered_kg: string;
  net_received_kg: string;
  net_returned_kg: string;
  bags_purchased?: number;
  bags_sold?: number;
  bags_delivered?: number;
  quantity_kg?: string;
  delivered_quantity_kg?: string;
  is_loose?: boolean;
  product_name?: string;
  brand_name?: string;
  bag_type_name?: string;
  remaining_kg?: string;
  stock_source?: "owned" | "job_work";
  job_work_order_id?: number | null;
  line_charge_type?: "product_sale" | "processing_charge";
};
export type Bill = {
  id: number;
  bill_number: string;
  bill_type: "sales" | "purchase";
  bill_date: string;
  customer_id: number;
  location_id?: number | null;
  status: string;
  version: number;
  discount_percent: string;
  discount_amount: string;
  adjustment: string;
  notes?: string | null;
  total_amount: string;
  final_payable: string;
  subtotal: string;
  grand_total: string;
  amount_paid: string;
  order_delivery_status: string;
  payment_status: string;
  customer_name?: string;
  customer_address_line?: string | null;
  customer_district?: string | null;
  customer_state?: string | null;
  customer_pin_code?: string | null;
  customer_phone?: string | null;
  location_name?: string;
  lines: BillLine[];
  due_amount?: string;
  amount_due?: string;
  customer_credit_balance?: string;
  customer_debit_balance?: string;
  opposite_due_total?: string;
  payments?: Payment[];
};
export type BalancePreview = {
  delta_due: string;
  credit_balance_change: string;
  debit_balance_change: string;
  new_credit_balance: string;
  new_debit_balance: string;
};
export type Payment = {
  id: number;
  bill_id: number;
  amount: string;
  payment_mode: string;
  account_id?: number | null;
  account_name?: string | null;
  account_kind?: BankAccountKind | null;
  /** @deprecated compat alias — use account_id */
  bank_account_id?: number | null;
  /** @deprecated compat alias — use account_name */
  bank_account_name?: string | null;
  paid_at: string;
  voided_at?: string | null;
  linked_payment_id?: number | null;
  bill_number?: string;
  bill_type?: string;
  customer_name?: string;
  grand_total?: string;
  amount_paid?: string;
  amount_due?: string;
  bill_version?: number;
  linked_payments?: Payment[];
};

export type FulfillmentEntry = {
  id: number;
  bill_line_id: number;
  entry_type: "deliver" | "return";
  quantity_kg: string;
  bag_count: number;
  loose_kg: string;
  location_id: number | null;
  location_name: string | null;
  parent_entry_id: number | null;
  notes: string | null;
  vehicle_no: string | null;
  fulfilled_at: string;
  created_at: string;
  voided_at: string | null;
};

export type FulfillmentAuditEntry = FulfillmentEntry & {
  bill_id: number;
  bill_number: string;
  bill_type: "sales" | "purchase";
  bill_version: number;
  customer_name?: string | null;
  product_name?: string | null;
  brand_name?: string | null;
  bag_type_name?: string | null;
  is_loose: boolean;
  bill_location_name?: string | null;
  stock_source?: "owned" | "job_work" | null;
};

export type SetoffAllocationPreview = {
  bill_id: number;
  bill_number: string;
  amount: string;
};
export type SetoffPreview = {
  bill_id: number;
  amount: string;
  payment_mode: string;
  opposite_due_total: string;
  max_amount: string;
  allocations: SetoffAllocationPreview[];
};
export type ProcessingInputSource = "fresh" | "balance_reprocess";

export type ProcessingInputLine = {
  id: number;
  location_id: number;
  location_name?: string;
  bag_type_id: number;
  bag_type_name?: string;
  bag_type_is_loose?: boolean;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  line_index: number;
  input_source: ProcessingInputSource;
  owner_type?: InventoryOwnerType;
  customer_id?: number | null;
  job_work_order_id?: number | null;
};

export type ProcessingWasteAllocation = {
  owner_type: InventoryOwnerType;
  customer_id: number | null;
  dust_kg: string;
  stone_kg: string;
  sack_weight_waste_kg: string;
  powder_kg?: string;
  miscellaneous_waste_kg: string;
};

export type ProcessingBalanceReturnLine = {
  id: number;
  location_id: number;
  location_name?: string;
  bag_type_id: number;
  bag_type_name?: string;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  line_index: number;
  owner_type?: InventoryOwnerType;
  customer_id?: number | null;
};

export type ProcessingOutputLine = {
  id: number;
  brand_id: number;
  brand_name?: string;
  location_id: number;
  location_name?: string;
  bag_type_id: number;
  bag_type_name?: string;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  line_index: number;
  owner_type?: InventoryOwnerType;
  customer_id?: number | null;
};

export type ProcessingBatch = {
  id: number;
  operation_at: string;
  voided_at?: string | null;
  dust_kg: string;
  stone_kg: string;
  sack_weight_waste_kg: string;
  powder_kg: string;
  powder_brand_id?: number | null;
  powder_brand_name?: string | null;
  powder_location_id?: number | null;
  powder_location_name?: string | null;
  powder_bag_type_id?: number | null;
  powder_bag_type_name?: string | null;
  powder_bag_type_is_loose?: boolean | null;
  powder_bag_count?: number | null;
  powder_loose_kg?: string | null;
  miscellaneous_waste_kg: string;
  input_lines: ProcessingInputLine[];
  output_lines: ProcessingOutputLine[];
  balance_return_lines: ProcessingBalanceReturnLine[];
  waste_allocations?: ProcessingWasteAllocation[];
};

export type ProcessingPowderLineIn = {
  brand_id: number;
  location_id: number;
  bag_type_id: number;
  bag_count: number;
  loose_kg: number;
};

export type ProcessingOutputByBrand = {
  brand_id: number;
  brand_name?: string;
  quantity_kg: string;
  bag_count: number;
};

export type ProcessingJobListSummary = {
  batch_count: number;
  total_output_kg: string;
};

export type ProcessingJobListItem = {
  id: number;
  input_product_id: number;
  input_product_name?: string;
  input_brand_id: number;
  input_brand_name?: string;
  status: "open" | "completed";
  opened_at: string;
  completed_at: string | null;
  batches: [];
  summary: ProcessingJobListSummary;
};

export type ProcessingJobSummary = {
  total_fresh_input_kg?: string;
  fresh_input_bags?: number;
  total_balance_reprocess_kg?: string;
  total_balance_return_kg?: string;
  net_balance_kg?: string;
  job_available_reprocess_kg?: string;
  output_by_brand?: ProcessingOutputByBrand[];
  total_waste_kg?: string;
  total_misc_kg?: string;
  total_loss_kg?: string;
  batch_count: number;
  total_output_kg?: string;
  in_process_kg?: string;
};

export type ProcessingOwnerAllocationWeight = {
  owner_type: InventoryOwnerType;
  customer_id?: number | null;
  customer_name?: string | null;
  input_kg: string;
  share_pct: string;
};

export type ProcessingInputAllowedOwner = {
  owner_type: InventoryOwnerType;
  customer_id?: number | null;
  customer_name?: string | null;
};

export type ProcessingJob = {
  id: number;
  input_product_id: number;
  input_product_name?: string;
  input_brand_id: number;
  input_brand_name?: string;
  status: "open" | "completed";
  opened_at: string;
  completed_at: string | null;
  batches?: ProcessingBatch[];
  summary?: ProcessingJobSummary;
  owner_mode?: "single_owner" | "mixed";
  input_locked?: boolean;
  input_allowed_owner?: ProcessingInputAllowedOwner | null;
  has_output?: boolean;
  input_rules_hint?: string | null;
  owner_allocation_weights?: ProcessingOwnerAllocationWeight[];
  output_allocation_mode?: "proportional" | "single_owner" | null;
  single_allocation_owner_type?: "owned" | "job_work" | null;
  single_allocation_customer_id?: number | null;
  single_allocation_customer_name?: string | null;
  output_allocation_locked?: boolean;
  output_allocation_hint?: string | null;
};

export type FulfillmentBill = {
  bill_id: number;
  bill_number: string;
  bill_type: string;
  customer_name: string;
  location_name: string;
  location_id: number;
  order_delivery_status: string;
  lines: {
    line_id: number;
    product_name: string;
    brand_name: string;
    bag_type_name: string;
    ordered_kg: number;
    fulfilled_kg: number;
    remaining_kg: number;
    line_delivery_status: string;
    bags_ordered: number;
    loose_kg_ordered: number;
    is_loose: boolean;
  }[];
};

export type ReportStatusBucket = { count: number; amount: string };

export type BusinessTypeSummary = {
  bill_amount: string;
  bill_count: number;
  qty_ordered_kg: string;
  bags_ordered: number;
};

export type BusinessSummary = {
  year: number;
  month: number;
  sales: BusinessTypeSummary;
  purchase: BusinessTypeSummary;
  /** Cash-book expenses excluding Self Withdrawal. */
  expense_total: string;
  /** Cash-book Self Withdrawal category total. */
  self_withdrawal_total: string;
  /** Sales − purchase − expense_total (excl. Self Withdrawal). */
  gross_profit: string;
  /** Sales − purchase − all expenses including Self Withdrawal. */
  net_profit: string;
};

export type FiscalYearMonthRow = {
  year: number;
  month: number;
  sales_amount: string;
  purchase_amount: string;
  expense_total: string;
  self_withdrawal_total: string;
  gross_profit: string;
  net_profit: string;
};

export type FiscalYearSummary = {
  start_year: number;
  end_year: number;
  label: string;
  date_from: string;
  date_to: string;
  sales: BusinessTypeSummary;
  purchase: BusinessTypeSummary;
  expense_total: string;
  self_withdrawal_total: string;
  /** Sales − purchase − expense_total (excl. Self Withdrawal) for 1 Apr–31 Mar. */
  gross_profit: string;
  /** Sales − purchase − all expenses including Self Withdrawal. */
  net_profit: string;
  months: FiscalYearMonthRow[];
};

export type BusinessCompareBucket = {
  sales_bill_amount: string;
  sales_qty_ordered_kg: string;
  sales_bags_ordered: number;
  sales_bill_count: number;
  purchase_bill_amount: string;
  purchase_qty_ordered_kg: string;
  purchase_bags_ordered: number;
  purchase_bill_count: number;
};

export type BusinessCompare = {
  current: BusinessCompareBucket;
  previous: BusinessCompareBucket;
  change_percent: {
    sales_bill_amount: string | null;
    sales_qty_ordered_kg: string | null;
    sales_bags_ordered: string | null;
    sales_bill_count: string | null;
    purchase_bill_amount: string | null;
    purchase_qty_ordered_kg: string | null;
    purchase_bags_ordered: string | null;
    purchase_bill_count: string | null;
  };
};

export type DailyBillAmountRow = {
  day: number;
  bill_date: string;
  sales_amount: string;
  purchase_amount: string;
  sales_bill_count: number;
  purchase_bill_count: number;
};

export type DailyBillAmounts = { rows: DailyBillAmountRow[] };

export type BillTypeParam = "sales" | "purchase";

export type SalesSummary = {
  total_sales: string;
  bill_count: number;
  total_quantity_kg: string;
  total_collected: string;
  total_due: string;
  avg_bill_value: string;
  prev_month_sales: string;
  mom_change_percent: string | null;
};

export type SalesProductRow = {
  product_id: number;
  product_name: string;
  brand_id?: number | null;
  brand_name?: string | null;
  quantity_kg: string;
  bag_count: number;
  amount: string;
  share_percent: string;
  avg_rate_per_kg: string;
};

export type SalesByProduct = {
  rows: SalesProductRow[];
  lines_subtotal: string;
  bills_grand_total: string;
  group_by: string;
};

export type JobWorkProductRow = {
  product_id: number;
  product_name: string;
  brand_id?: number | null;
  brand_name?: string | null;
  ordered_quantity_kg: string;
  ordered_bags: number;
  received_quantity_kg: string;
  returned_quantity_kg: string;
  in_custody_kg: string;
};

export type JobWorkByProduct = {
  rows: JobWorkProductRow[];
  order_count: number;
  ordered_quantity_kg: string;
  ordered_bags: number;
  received_quantity_kg: string;
  returned_quantity_kg: string;
  in_custody_kg: string;
  group_by: string;
};

export type SalesCustomerRow = {
  customer_id: number;
  customer_name: string;
  bill_count: number;
  quantity_kg: string;
  amount: string;
  share_percent: string;
};

export type SalesByCustomer = { rows: SalesCustomerRow[]; total_amount: string };

export type SalesLocationRow = {
  location_id: number | null;
  location_name: string;
  bill_count: number;
  quantity_kg: string;
  amount: string;
};

export type SalesByLocation = { rows: SalesLocationRow[] };

export type DashboardBundle = {
  summary: BusinessSummary;
  compare: BusinessCompare;
  fiscal_year: FiscalYearSummary;
  daily: DailyBillAmounts;
  by_product: SalesByProduct;
  by_customer: SalesByCustomer;
  by_location: SalesByLocation;
  job_work: JobWorkByProduct;
  money_now: MoneyNow;
};

export type MoneyNow = {
  amount_in_hand: string;
  after_credit: string;
  after_debit: string;
  after_settlement: string;
};

export type SalesDailyRow = {
  day: number;
  bill_date: string;
  amount: string;
  bill_count: number;
  quantity_kg: string;
};

export type SalesDaily = { rows: SalesDailyRow[] };

export type SalesCompareBucket = {
  sales: string;
  bills: number;
  kg: string;
  collected: string;
};

export type SalesCompare = {
  current: SalesCompareBucket;
  previous: SalesCompareBucket;
  change_percent: {
    sales: string | null;
    bills: string | null;
    kg: string | null;
    collected: string | null;
  };
};

export type SalesPaymentBreakdown = {
  paid: ReportStatusBucket;
  partial: ReportStatusBucket;
  unpaid: ReportStatusBucket;
};

export type SalesDeliveryBreakdown = {
  delivered: ReportStatusBucket;
  partial: ReportStatusBucket;
  not_delivered: ReportStatusBucket;
};

export type ReportMonthParams = { year: number; month: number };

function reportQs(
  params: ReportMonthParams & {
    group_by?: string;
    limit?: number;
    bill_type?: BillTypeParam;
    customer_id?: number | null;
  }
) {
  const q = new URLSearchParams({
    year: String(params.year),
    month: String(params.month),
  });
  if (params.group_by) q.set("group_by", params.group_by);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.bill_type) q.set("bill_type", params.bill_type);
  if (params.customer_id != null) q.set("customer_id", String(params.customer_id));
  return q.toString();
}

export const reportsApi = {
  dashboardBundle: (
    p: ReportMonthParams & {
      bill_type: BillTypeParam;
      group_by: "product" | "product_brand";
      customer_id?: number | null;
    }
  ) => api.get<DashboardBundle>(`/api/reports/dashboard-bundle?${reportQs(p)}`),
};

export type AuditEvent = {
  id: number;
  user_id: number | null;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  entity_label: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AuditEventListParams = {
  user_id?: number;
  action?: string;
  entity_type?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export const auditApi = {
  listEvents: (params: AuditEventListParams = {}) => {
    const q = new URLSearchParams();
    if (params.user_id != null) q.set("user_id", String(params.user_id));
    if (params.action) q.set("action", params.action);
    if (params.entity_type) q.set("entity_type", params.entity_type);
    if (params.date_from) q.set("date_from", params.date_from);
    if (params.date_to) q.set("date_to", params.date_to);
    if (params.search) q.set("search", params.search);
    q.set("limit", String(params.limit ?? DEFAULT_PAGE_LIMIT));
    q.set("offset", String(params.offset ?? 0));
    return api.get<PageOut<AuditEvent>>(`/api/audit/events?${q.toString()}`);
  },
};

export type LoginEvent = {
  id: number;
  email: string;
  user_id: number | null;
  success: boolean;
  failure_reason: string | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};

export type LoginEventListParams = {
  email?: string;
  user_id?: number;
  success?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export const loginHistoryApi = {
  listEvents: (params: LoginEventListParams = {}) => {
    const q = new URLSearchParams();
    if (params.email) q.set("email", params.email);
    if (params.user_id != null) q.set("user_id", String(params.user_id));
    if (params.success) q.set("success", params.success);
    if (params.date_from) q.set("date_from", params.date_from);
    if (params.date_to) q.set("date_to", params.date_to);
    if (params.search) q.set("search", params.search);
    q.set("limit", String(params.limit ?? DEFAULT_PAGE_LIMIT));
    q.set("offset", String(params.offset ?? 0));
    return api.get<PageOut<LoginEvent>>(`/api/login-history/events?${q.toString()}`);
  },
};

// ---------------------------------------------------------------------------
// Spec v12.21 — Accounts, Cash Book & Multi-Bank
// ---------------------------------------------------------------------------

export const EXPECTED_CASH_BOOK_VERSION_HEADER = "X-Expected-Cash-Book-Version";

export type BankAccountKind = "cash" | "bank";

export type BankAccount = {
  id: number;
  name: string;
  kind: BankAccountKind;
  account_number_last4: string | null;
  ifsc: string | null;
  opening_balance: string;
  opening_balance_at: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
};

export type BankAccountBalance = BankAccount & { balance: string };

export type BankAccountIn = {
  name: string;
  kind?: BankAccountKind;
  account_number_last4?: string | null;
  ifsc?: string | null;
  opening_balance?: string | number;
  is_default?: boolean;
};

export type BankAccountUpdateIn = {
  name?: string;
  account_number_last4?: string | null;
  ifsc?: string | null;
  opening_balance?: string | number;
  is_active?: boolean;
};

export type ExpenseCategoryKind = "expense" | "income" | "transfer";

export type ExpenseCategory = {
  id: number;
  name: string;
  kind: ExpenseCategoryKind;
  is_system: boolean;
  is_active: boolean;
  created_at: string;
};

export type ExpenseCategoryIn = {
  name: string;
  kind: ExpenseCategoryKind;
};

export type ExpenseCategoryUpdateIn = {
  name?: string;
  is_active?: boolean;
};

export type CashBookEntryType = "expense" | "income" | "transfer";
export type CashBookSourceMode = "cash" | "bank";

export type CashBookEntry = {
  id: number;
  entry_type: CashBookEntryType;
  category_id: number;
  category_name: string | null;
  category_kind: ExpenseCategoryKind | null;
  amount: string;
  description: string | null;
  reference_no: string | null;
  bill_id: number | null;
  bill_number: string | null;
  source_account_id: number | null;
  source_account_name: string | null;
  source_account_kind: BankAccountKind | null;
  dest_account_id: number | null;
  dest_account_name: string | null;
  dest_account_kind: BankAccountKind | null;
  /** @deprecated compat — derived from source_account */
  source_payment_mode: CashBookSourceMode | null;
  /** @deprecated compat — derived from source_account */
  source_bank_account_id: number | null;
  source_bank_account_name: string | null;
  /** @deprecated compat — derived from dest_account */
  dest_payment_mode: CashBookSourceMode | null;
  /** @deprecated compat — derived from dest_account */
  dest_bank_account_id: number | null;
  dest_bank_account_name: string | null;
  entry_date: string;
  entry_at: string;
  voided_at: string | null;
  version: number;
  created_at: string;
};

export type CashBookEntryIn = {
  entry_type: CashBookEntryType;
  category_id: number;
  amount: string | number;
  description?: string | null;
  reference_no?: string | null;
  bill_id?: number | null;
  source_account_id: number;
  dest_account_id?: number | null;
  entry_date?: string | null;
};

export type CashBookEntryEditIn = CashBookEntryIn & { expected_version: number };

export type AccountsSummary = {
  cash_balance: string;
  total_bank_balance: string;
  total_money: string;
  total_customer_credit: string;
  total_customer_debit: string;
  bank_accounts: BankAccountBalance[];
  recent_entries: CashBookEntry[];
};

export type CustomerBalanceRow = {
  customer_id: number;
  customer_name: string;
  credit_balance: string;
  debit_balance: string;
  net_balance: string;
  last_activity_at: string | null;
};

export type CustomerBalancePage = PageOut<CustomerBalanceRow> & {
  credit_total: string;
  debit_total: string;
};

export type CustomerStatementRow = {
  event_at: string;
  event_date: string;
  kind: string;
  description: string;
  bill_id: number | null;
  bill_number: string | null;
  payment_id: number | null;
  debit_amount: string;
  credit_amount: string;
  running_balance: string;
};

export type CustomerStatementPage = PageOut<CustomerStatementRow> & {
  customer_id: number;
  customer_name: string;
  current_credit_balance: string;
  current_debit_balance: string;
  current_net_balance: string;
};

export type BookSettings = {
  id: number;
  cash_opening_balance: string;
  cash_opening_balance_at: string;
  updated_at: string;
  powder_product_id?: number | null;
  powder_product_name?: string | null;
  powder_brand_id?: number | null;
  powder_brand_name?: string | null;
  powder_location_id?: number | null;
  powder_location_name?: string | null;
  powder_bag_type_id?: number | null;
  powder_bag_type_name?: string | null;
  company_name?: string | null;
  company_address_line?: string | null;
  company_address_line_2?: string | null;
  company_district?: string | null;
  company_state?: string | null;
  company_pin_code?: string | null;
  company_gstin?: string | null;
  company_phone?: string | null;
};

export type BookSettingsIn = {
  cash_opening_balance?: string | number;
  powder_product_id?: number | null;
  powder_brand_id?: number | null;
  powder_location_id?: number | null;
  powder_bag_type_id?: number | null;
  company_name?: string | null;
  company_address_line?: string | null;
  company_phone?: string | null;
};

export type BillPickerItem = {
  id: number;
  bill_number: string;
  bill_type: "sales" | "purchase";
  customer_id: number | null;
  customer_name: string | null;
  bill_date: string;
  grand_total: string;
};

export type BillVoidLinkedInfo = {
  bill_id: number;
  can_void: boolean;
  block_reasons: string[];
  linked_active_entries_count: number;
  linked_active_entries_amount: string;
};

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

type ListParams = {
  limit?: number;
  offset?: number;
  search?: string;
};

export const bankAccountsApi = {
  list: (p: ListParams & { active?: "true" | "false" | "all"; kind?: "bank" | "cash" | "all" } = {}) =>
    api.get<PageOut<BankAccountBalance>>(
      `/api/bank-accounts${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        active: p.active ?? "true",
        kind: p.kind ?? "bank",
      })}`
    ),
  create: (body: BankAccountIn, key: string) =>
    api.post<BankAccount>("/api/bank-accounts", body, { headers: idempotencyHeaders(key) }),
  update: (id: number, body: BankAccountUpdateIn, key: string) =>
    api.patch<BankAccount>(`/api/bank-accounts/${id}`, body, { headers: idempotencyHeaders(key) }),
  remove: (id: number) => api.delete(`/api/bank-accounts/${id}`),
  makeDefault: (id: number, key: string) =>
    api.post<BankAccount>(`/api/bank-accounts/${id}/make-default`, {}, { headers: idempotencyHeaders(key) }),
};

export const expenseCategoriesApi = {
  list: (p: ListParams & { active?: "true" | "false" | "all"; kind?: ExpenseCategoryKind } = {}) =>
    api.get<PageOut<ExpenseCategory>>(
      `/api/expense-categories${qs({ limit: p.limit ?? DEFAULT_PAGE_LIMIT, offset: p.offset ?? 0, active: p.active ?? "true", kind: p.kind })}`
    ),
  create: (body: ExpenseCategoryIn, key: string) =>
    api.post<ExpenseCategory>("/api/expense-categories", body, { headers: idempotencyHeaders(key) }),
  update: (id: number, body: ExpenseCategoryUpdateIn, key: string) =>
    api.patch<ExpenseCategory>(`/api/expense-categories/${id}`, body, { headers: idempotencyHeaders(key) }),
  remove: (id: number) => api.delete(`/api/expense-categories/${id}`),
};

export type CashBookListParams = ListParams & {
  entry_type?: CashBookEntryType;
  category_id?: number;
  account_id?: number;
  bill_id?: number;
  voided?: "false" | "true" | "any";
  date_from?: string;
  date_to?: string;
};

export type CashBookPage = PageOut<CashBookEntry> & {
  amount_total: string;
  expense_total: string;
  income_total: string;
  transfer_total: string;
};

export const cashBookApi = {
  get: (id: number) => api.get<CashBookEntry>(`/api/cashbook/${id}`),
  list: (p: CashBookListParams = {}) =>
    api.get<CashBookPage>(
      `/api/cashbook${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        entry_type: p.entry_type,
        category_id: p.category_id,
        account_id: p.account_id,
        bill_id: p.bill_id,
        voided: p.voided ?? "false",
        date_from: p.date_from,
        date_to: p.date_to,
        search: p.search,
        // Unique query each call — defeats Electron/Chromium stale GET reuse.
        _: Date.now(),
      })}`
    ),
  create: (body: CashBookEntryIn, key: string, authorizationPassword?: string) =>
    api.post<CashBookEntry>("/api/cashbook", body, {
      headers: idempotencyHeadersOptionalAuth(key, authorizationPassword),
    }),
  update: (id: number, body: CashBookEntryEditIn, key: string) =>
    api.patch<CashBookEntry>(`/api/cashbook/${id}`, body, { headers: idempotencyHeaders(key) }),
  void: (id: number, expectedVersion: number, key: string, authorizationPassword: string) =>
    api.post<CashBookEntry>(`/api/cashbook/${id}/void`, {}, {
      headers: idempotencyVoidAuthHeaders(key, authorizationPassword, {
        [EXPECTED_CASH_BOOK_VERSION_HEADER]: String(expectedVersion),
      }),
    }),
};

export const accountsApi = {
  summary: () =>
    api.get<AccountsSummary>(`/api/accounts/summary${qs({ _: Date.now() })}`),
  customers: (p: ListParams & { has_balance?: "any" | "positive" | "zero" } = {}) =>
    api.get<CustomerBalancePage>(
      `/api/accounts/customers${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        has_balance: p.has_balance ?? "any",
        search: p.search,
      })}`
    ),
  statement: (customerId: number, p: { date_from?: string; date_to?: string; limit?: number; offset?: number } = {}) =>
    api.get<CustomerStatementPage>(
      `/api/accounts/customers/${customerId}/statement${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        date_from: p.date_from,
        date_to: p.date_to,
      })}`
    ),
};

export const bookSettingsApi = {
  get: () => api.get<BookSettings>("/api/book-settings"),
  update: (body: BookSettingsIn, key: string) =>
    api.patch<BookSettings>("/api/book-settings", body, { headers: idempotencyHeaders(key) }),
};

export type Company = {
  id: number;
  name: string;
  address_line?: string | null;
  address_line_2?: string | null;
  district?: string | null;
  state?: string | null;
  pin_code?: string | null;
  gstin?: string | null;
  phone?: string | null;
  is_active?: boolean;
  created_at?: string | null;
};

export type CompanyUpdate = {
  name?: string;
  address_line?: string | null;
  address_line_2?: string | null;
  district?: string | null;
  state?: string | null;
  pin_code?: string | null;
  gstin?: string | null;
  phone?: string | null;
};

export const companiesApi = {
  getMe: () => api.get<Company>("/api/companies/me"),
  updateMe: (body: CompanyUpdate) => api.patch<Company>("/api/companies/me", body),
  registrationStatus: () => api.get<{ allowed: boolean }>("/api/companies/registration-status", { skipAuthRedirect: true }),
};

export const adminApi = {
  downloadBackup: () => downloadBlob("/api/admin/backup", "graintrack-backup.dump"),
};

// ---------------------------------------------------------------------------
// Spec v14.0 — Job Work
// ---------------------------------------------------------------------------

export type JobWorkOrderStatus = "open" | "completed" | "cancelled";

export type JobWorkReceipt = {
  id: number;
  line_id: number;
  location_id: number;
  location_name?: string | null;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  vehicle_no?: string | null;
  notes?: string | null;
  entry_type?: "receive" | "return";
  received_at: string;
  voided_at?: string | null;
};

export type JobWorkLine = {
  id: number;
  product_id: number;
  product_name?: string | null;
  brand_id: number;
  brand_name?: string | null;
  bag_type_id: number;
  bag_type_name?: string | null;
  weight_per_bag_kg?: string | null;
  is_loose?: boolean;
  ordered_bags: number;
  ordered_loose_kg: string;
  ordered_quantity_kg: string;
  received_bags: number;
  received_loose_kg: string;
  received_quantity_kg: string;
  returned_bags: number;
  returned_loose_kg: string;
  returned_quantity_kg: string;
  net_received_bags?: number;
  net_received_loose_kg?: string;
  net_received_kg?: string;
  remaining_receive_bags?: number;
  remaining_receive_loose_kg?: string;
  remaining_receive_kg?: string;
  custody_bags?: number;
  custody_loose_kg?: string;
  custody_kg?: string;
  line_index: number;
  receipts: JobWorkReceipt[];
};

export type JobWorkOrder = {
  id: number;
  job_number: string;
  customer_id: number;
  customer_name?: string | null;
  job_date: string;
  notes?: string | null;
  status: JobWorkOrderStatus | string;
  version: number;
  created_at: string;
  updated_at: string;
  lines: JobWorkLine[];
};

export type JobWorkLineIn = {
  product_id: number;
  brand_id: number;
  bag_type_id: number;
  ordered_bags?: number;
  ordered_loose_kg?: string | number;
};

export type JobWorkOrderCreate = {
  customer_id: number;
  job_date: string;
  notes?: string | null;
  lines: JobWorkLineIn[];
};

export type JobWorkReceiveIn = {
  line_id: number;
  location_id: number;
  bag_count?: number;
  loose_kg?: string | number;
  vehicle_no?: string | null;
  notes?: string | null;
  received_date?: string | null;
};

export type JobWorkReturnIn = {
  line_id: number;
  location_id: number;
  bag_count?: number;
  loose_kg?: string | number;
  notes?: string | null;
  received_date?: string | null;
};

export type JobWorkFulfillmentReceipt = {
  id: number;
  line_id: number;
  location_id: number;
  location_name?: string | null;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  vehicle_no?: string | null;
  notes?: string | null;
  entry_type?: "receive" | "return";
  received_at: string;
  voided_at?: string | null;
};

export type JwReturnLocation = {
  location_id: number;
  location_name?: string | null;
  returnable_bags: number;
  returnable_loose_kg: string;
  returnable_kg: string;
};

export type JobWorkFulfillmentLine = {
  line_id: number;
  order_id: number;
  job_number: string;
  customer_name?: string | null;
  product_id: number;
  product_name?: string | null;
  brand_id: number;
  brand_name?: string | null;
  bag_type_id: number;
  bag_type_name?: string | null;
  weight_per_bag_kg?: string | null;
  is_loose: boolean;
  ordered_bags: number;
  ordered_loose_kg: string;
  received_bags: number;
  received_loose_kg: string;
  returned_bags: number;
  returned_loose_kg: string;
  ordered_kg: string;
  received_kg: string;
  returned_kg: string;
  net_received_kg: string;
  net_received_bags: number;
  net_received_loose_kg: string;
  remaining_receive_kg: string;
  remaining_receive_bags: number;
  remaining_receive_loose_kg: string;
  custody_kg: string;
  custody_bags: number;
  custody_loose_kg: string;
  return_locations: JwReturnLocation[];
  receipts: JobWorkFulfillmentReceipt[];
};

export type JobWorkFulfillmentOrder = {
  order_id: number;
  job_number: string;
  customer_id: number;
  customer_name?: string | null;
  job_date: string;
  status: string;
  lines: JobWorkFulfillmentLine[];
};

export type JobWorkFulfillmentListParams = ListParams & {
  tab?: "all" | "receive" | "return";
  visibility?: "actionable" | "all";
};

export type JobWorkStatementOrder = {
  job_work_order_id: number;
  job_number: string;
  job_date: string;
  status: string;
  ordered_quantity_kg: string;
  received_quantity_kg: string;
  returned_quantity_kg: string;
  outstanding_quantity_kg: string;
};

export type JobWorkStatement = {
  customer_id: number;
  customer_name: string;
  from_date?: string | null;
  to_date?: string | null;
  total_ordered_kg: string;
  total_received_kg: string;
  total_returned_kg: string;
  outstanding_in_custody_kg: string;
  orders: JobWorkStatementOrder[];
};

export type JobWorkListParams = ListParams & {
  customer_id?: number;
  status?: JobWorkOrderStatus;
};

export const jobWorkApi = {
  nextNumber: () => api.get<{ job_number: string }>("/api/job-work/next-number"),
  list: (p: JobWorkListParams = {}) =>
    api.get<PageOut<JobWorkOrder>>(
      `/api/job-work${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        customer_id: p.customer_id,
        status: p.status,
        search: p.search,
      })}`
    ),
  get: (id: number) => api.get<JobWorkOrder>(`/api/job-work/${id}`),
  void: (orderId: number, key: string, authorizationPassword: string) =>
    api.post<JobWorkOrder>(`/api/job-work/${orderId}/void`, {}, {
      headers: idempotencyVoidAuthHeaders(key, authorizationPassword),
    }),
  create: (body: JobWorkOrderCreate, key: string, authorizationPassword?: string) =>
    api.post<JobWorkOrder>("/api/job-work", body, {
      headers: idempotencyHeadersOptionalAuth(key, authorizationPassword),
    }),
  receive: (body: JobWorkReceiveIn, key: string, authorizationPassword?: string) =>
    api.post<JobWorkReceipt>("/api/job-work/receive", body, {
      headers: idempotencyHeadersOptionalAuth(key, authorizationPassword),
    }),
  voidReceipt: (receiptId: number, key: string, authorizationPassword: string) =>
    api.post<JobWorkReceipt>(`/api/job-work/receipts/${receiptId}/void`, {}, {
      headers: idempotencyVoidAuthHeaders(key, authorizationPassword),
    }),
  returnToCustomer: (body: JobWorkReturnIn, key: string, authorizationPassword?: string) =>
    api.post<JobWorkOrder>("/api/job-work/return", body, {
      headers: idempotencyHeadersOptionalAuth(key, authorizationPassword),
    }),
  statement: (customerId: number, p: { from_date?: string; to_date?: string } = {}) =>
    api.get<JobWorkStatement>(
      `/api/job-work/customers/${customerId}/statement${qs({
        from_date: p.from_date,
        to_date: p.to_date,
      })}`
    ),
};

export const jobWorkFulfillmentApi = {
  listOrders: (p: JobWorkFulfillmentListParams = {}) =>
    api.get<PageOut<JobWorkFulfillmentOrder>>(
      `/api/job-work/fulfillment/orders${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        tab: p.tab ?? "all",
        visibility: p.visibility ?? "actionable",
      })}`
    ),
};

export const billsApi = {
  picker: (p: ListParams & { bill_type?: "sales" | "purchase" } = {}) =>
    api.get<PageOut<BillPickerItem>>(
      `/api/bills/picker${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
        bill_type: p.bill_type,
        search: p.search,
      })}`
    ),
  linkedEntries: (billId: number, p: ListParams = {}) =>
    api.get<PageOut<CashBookEntry>>(
      `/api/bills/${billId}/linked-entries${qs({
        limit: p.limit ?? DEFAULT_PAGE_LIMIT,
        offset: p.offset ?? 0,
      })}`
    ),
  voidPrecheck: (billId: number) =>
    api.get<BillVoidLinkedInfo>(`/api/bills/${billId}/void-precheck`),
  void: (
    billId: number,
    key: string,
    authorizationPassword: string,
    expectedVersion: number
  ) =>
    api.post<Bill>(
      `/api/bills/${billId}/void`,
      {},
      {
        headers: idempotencyVoidAuthHeaders(key, authorizationPassword, {
          [EXPECTED_BILL_VERSION_HEADER]: String(expectedVersion),
        }),
      }
    ),
};
