import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Ban,
  Plus,
  ReceiptText,
} from "lucide-react";
import {
  bankAccountsApi,
  cashBookApi,
  expenseCategoriesApi,
  type BankAccountBalance,
  type CashBookEntry,
  type CashBookEntryType,
  type CashBookListParams,
  type ExpenseCategory,
  DEFAULT_PAGE_LIMIT,
  newIdempotencyKey,
} from "../../api/client";
import { accountsByKind } from "../../lib/moneyAccounts";
import {
  clearRememberedCashBookCreated,
  readRememberedCashBookCreated,
} from "../../lib/cashBookCreated";
import { formatDate, formatInr } from "../../lib/format";
import { usePermissions } from "../../lib/permissions";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import { Card, CardBody } from "../../components/ui/Card";
import FormField from "../../components/ui/FormField";
import VoidConfirmDialog from "../../components/ui/VoidConfirmDialog";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import Input from "../../components/ui/Input";
import Table, { type Column } from "../../components/ui/Table";
import { toast } from "../../components/ui/Toaster";
import { cn } from "../../lib/cn";

function entryTypeBadge(entry: CashBookEntry) {
  if (entry.entry_type === "income") return <Badge tone="success" size="sm">Income</Badge>;
  if (entry.entry_type === "transfer") return <Badge tone="info" size="sm">Transfer</Badge>;
  return <Badge tone="danger" size="sm">Expense</Badge>;
}

function entryIcon(entry: CashBookEntry) {
  if (entry.entry_type === "income") return <ArrowDownLeft className="h-4 w-4 shrink-0 text-emerald-600" />;
  if (entry.entry_type === "transfer") return <ArrowLeftRight className="h-4 w-4 shrink-0 text-primary-700" />;
  return <ArrowUpRight className="h-4 w-4 shrink-0 text-rose-600" />;
}

function modeLabel(entry: CashBookEntry): string {
  if (entry.entry_type === "transfer") {
    const src =
      entry.source_payment_mode === "bank" ? entry.source_bank_account_name ?? "Bank" : "Cash";
    const dst = entry.dest_payment_mode === "bank" ? entry.dest_bank_account_name ?? "Bank" : "Cash";
    return `${src} → ${dst}`;
  }
  if (entry.source_payment_mode === "bank") {
    return entry.source_bank_account_name ?? "Bank";
  }
  return "Cash";
}

function resolveSeed(
  locState: { seedEntry?: CashBookEntry } | null,
  createdParam: string | null
): CashBookEntry | null {
  if (locState?.seedEntry && typeof locState.seedEntry.id === "number") {
    return locState.seedEntry;
  }
  const remembered = readRememberedCashBookCreated();
  if (!remembered) return null;
  if (createdParam && remembered.id !== Number(createdParam)) return null;
  return remembered;
}

function sameEntryId(a: number | string | null | undefined, b: number | string | null | undefined): boolean {
  if (a == null || b == null) return false;
  return Number(a) === Number(b);
}

function prependUnique(entry: CashBookEntry, items: CashBookEntry[]): CashBookEntry[] {
  if (items.some((r) => sameEntryId(r.id, entry.id))) {
    return items.map((r) => (sameEntryId(r.id, entry.id) ? entry : r));
  }
  return [entry, ...items];
}

function CashBookMobileCard({
  entry,
  highlighted,
  canVoid,
  busy,
  onVoid,
}: {
  entry: CashBookEntry;
  highlighted: boolean;
  canVoid: boolean;
  busy: boolean;
  onVoid: () => void;
}) {
  return (
    <Card
      className={cn(
        "overflow-hidden border-line/80",
        highlighted && "border-emerald-300/80 bg-emerald-50/70 dark:border-emerald-800 dark:bg-emerald-950/40",
        entry.voided_at && "opacity-70"
      )}
    >
      <CardBody className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              {entryIcon(entry)}
              {entryTypeBadge(entry)}
              {entry.voided_at ? (
                <Badge tone="danger" size="sm">
                  Voided
                </Badge>
              ) : (
                <Badge tone="success" size="sm">
                  Active
                </Badge>
              )}
            </div>
            <p className="truncate font-semibold text-ink">{entry.category_name ?? "—"}</p>
            <p className="v2-mono text-sm text-ink-muted">{formatDate(entry.entry_date)}</p>
          </div>
          <p className="v2-mono shrink-0 text-lg font-bold tabular-nums text-ink">{formatInr(entry.amount)}</p>
        </div>
        <p className="truncate text-sm text-ink-muted">{modeLabel(entry)}</p>
        {(entry.description || entry.reference_no) && (
          <p className="truncate text-xs text-ink-subtle">
            {entry.description ?? ""}
            {entry.description && entry.reference_no ? " · " : ""}
            {entry.reference_no ? `Ref ${entry.reference_no}` : ""}
          </p>
        )}
        {entry.bill_id ? (
          <Link
            to={`/sales-bills/${entry.bill_id}`}
            className="v2-mono text-sm font-medium text-primary-600 hover:underline"
          >
            {entry.bill_number ?? `#${entry.bill_id}`}
          </Link>
        ) : null}
        <div className="flex flex-wrap gap-2 border-t border-line/70 pt-3">
          <Link to={`/accounts/cashbook/${entry.id}/edit`} className="min-w-0 flex-1 sm:flex-none">
            <Button size="md" variant="secondary" className="w-full sm:w-auto">
              Open
            </Button>
          </Link>
          {!entry.voided_at && canVoid ? (
            <Button
              size="md"
              variant="outline"
              leftIcon={<Ban className="h-3.5 w-3.5" />}
              className={cn(
                "w-full border-rose-200/80 bg-rose-50/40 font-medium text-rose-700 sm:w-auto",
                "hover:border-rose-300 hover:bg-rose-100/80 hover:text-rose-800",
                "dark:border-rose-800/50 dark:bg-rose-950/25 dark:text-rose-300"
              )}
              loading={busy}
              onClick={onVoid}
            >
              Void
            </Button>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

export default function CashBookListPage() {
  const { canVoid } = usePermissions();
  const location = useLocation();
  const createdParam = new URLSearchParams(location.search).get("created");
  const createdId =
    createdParam && Number.isFinite(Number(createdParam)) ? Number(createdParam) : null;

  const [rows, setRows] = useState<CashBookEntry[]>(() => {
    const remembered = resolveSeed(null, createdParam);
    return remembered ? [remembered] : [];
  });
  const [total, setTotal] = useState(() => (resolveSeed(null, createdParam) ? 1 : 0));
  const [amountTotal, setAmountTotal] = useState("0.00");
  const [expenseTotal, setExpenseTotal] = useState("0.00");
  const [incomeTotal, setIncomeTotal] = useState("0.00");
  const [transferTotal, setTransferTotal] = useState("0.00");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [voidAuthError, setVoidAuthError] = useState("");
  const [pending, setPending] = useState<CashBookEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [highlightedId, setHighlightedId] = useState<number | null>(createdId);
  const [reloadNonce, setReloadNonce] = useState(0);
  const idemRef = useRef<string | null>(null);
  const loadGenRef = useRef(0);
  const limit = DEFAULT_PAGE_LIMIT;

  const [filters, setFilters] = useState<CashBookListParams>({
    voided: "false",
  });
  const [categories, setCategories] = useState<ExpenseCategory[]>([]);
  const [accounts, setAccounts] = useState<BankAccountBalance[]>([]);

  const groupedAccounts = useMemo(() => accountsByKind(accounts), [accounts]);

  const hasActiveFilters = useMemo(
    () =>
      Boolean(
        filters.entry_type ||
          filters.category_id ||
          filters.account_id ||
          filters.date_from ||
          filters.date_to ||
          (filters.voided && filters.voided !== "false")
      ),
    [filters]
  );

  useEffect(() => {
    expenseCategoriesApi
      .list({ limit: 200, active: "all" })
      .then((p) => setCategories(p.items))
      .catch(() => {});
    bankAccountsApi
      .list({ limit: 200, active: "all", kind: "all" })
      .then((p) => setAccounts(p.items))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [filters]);

  // Single sequential loader: GET created id first (authoritative), then list, always keep created on top.
  useEffect(() => {
    const gen = ++loadGenRef.current;
    let cancelled = false;
    const remembered = resolveSeed(null, createdParam);

    (async () => {
      setLoading(true);
      setError("");

      let createdEntry: CashBookEntry | null = remembered;
      if (createdId != null) {
        try {
          createdEntry = await cashBookApi.get(createdId);
          if (cancelled || gen !== loadGenRef.current) return;
          setHighlightedId(createdEntry.id);
          setRows([createdEntry]);
          setTotal(1);
        } catch (e) {
          if (cancelled || gen !== loadGenRef.current) return;
          const msg = e instanceof Error ? e.message : String(e);
          setError(`Could not load new entry #${createdId}: ${msg}`);
          toast.error(msg);
        }
      }

      try {
        const page = await cashBookApi.list({ ...filters, limit, offset });
        if (cancelled || gen !== loadGenRef.current) return;
        const items = createdEntry ? prependUnique(createdEntry, page.items ?? []) : (page.items ?? []);
        setRows(items);
        setTotal(
          createdEntry && !(page.items ?? []).some((r) => sameEntryId(r.id, createdEntry!.id))
            ? Math.max((page.total ?? 0) + 1, items.length)
            : (page.total ?? 0)
        );
        setAmountTotal(page.amount_total ?? "0.00");
        setExpenseTotal(page.expense_total ?? "0.00");
        setIncomeTotal(page.income_total ?? "0.00");
        setTransferTotal(page.transfer_total ?? "0.00");
        if (createdEntry && (page.items ?? []).some((r) => sameEntryId(r.id, createdEntry!.id))) {
          clearRememberedCashBookCreated(createdEntry.id);
        }
      } catch (e) {
        if (cancelled || gen !== loadGenRef.current) return;
        const msg = e instanceof Error ? e.message : String(e);
        if (!createdEntry) {
          setRows([]);
          setTotal(0);
          setAmountTotal("0.00");
          setExpenseTotal("0.00");
          setIncomeTotal("0.00");
          setTransferTotal("0.00");
        }
        setError(msg);
        toast.error(msg);
      } finally {
        if (!cancelled && gen === loadGenRef.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [createdId, createdParam, filters, limit, offset, reloadNonce]);

  const clearFilters = () => {
    setFilters({ voided: "false" });
  };

  const reload = () => setReloadNonce((n) => n + 1);

  const highlightedEntry = useMemo(
    () => (highlightedId == null ? null : rows.find((r) => sameEntryId(r.id, highlightedId)) ?? null),
    [rows, highlightedId]
  );

  /** Always pin the just-created row to the top for display. */
  const displayRows = useMemo(() => {
    if (!highlightedEntry) return rows;
    return [highlightedEntry, ...rows.filter((r) => !sameEntryId(r.id, highlightedEntry.id))];
  }, [rows, highlightedEntry]);

  const voidEntry = async (authorizationPassword: string) => {
    if (!pending) return;
    if (!idemRef.current) idemRef.current = newIdempotencyKey();
    setBusy(true);
    setVoidAuthError("");
    try {
      await cashBookApi.void(pending.id, pending.version, idemRef.current, authorizationPassword);
      toast.success("Entry voided");
      setPending(null);
      reload();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not void entry";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidAuthError(msg);
      } else {
        setError(msg);
        toast.error(msg);
      }
      throw err;
    } finally {
      // Always rotate key after a completed attempt so retries / next voids never reuse it.
      idemRef.current = null;
      setBusy(false);
    }
  };

  const columns: Column<CashBookEntry>[] = useMemo(
    () => [
      {
        key: "date",
        header: "Date",
        width: "10%",
        cell: (e) => (
          <span className="v2-mono text-sm text-ink-muted">{formatDate(e.entry_date)}</span>
        ),
      },
      {
        key: "entry",
        header: "Entry",
        width: "28%",
        cell: (e) => (
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              {entryIcon(e)}
              {entryTypeBadge(e)}
              <span className="truncate font-medium text-ink">{e.category_name ?? "—"}</span>
            </div>
            {(e.description || e.reference_no) && (
              <p className="truncate text-xs text-ink-subtle">
                {e.description ?? ""}
                {e.description && e.reference_no ? " · " : ""}
                {e.reference_no ? `Ref ${e.reference_no}` : ""}
              </p>
            )}
          </div>
        ),
      },
      {
        key: "amount",
        header: "Amount",
        width: "12%",
        numeric: true,
        cell: (e) => (
          <span className="v2-mono text-base font-semibold text-ink">{formatInr(e.amount)}</span>
        ),
      },
      {
        key: "mode",
        header: "Payment",
        width: "18%",
        cell: (e) => <span className="truncate text-sm text-ink-muted">{modeLabel(e)}</span>,
      },
      {
        key: "bill",
        header: "Bill",
        width: "12%",
        cell: (e) =>
          e.bill_id ? (
            <Link
              to={`/sales-bills/${e.bill_id}`}
              className="v2-mono text-sm font-medium text-primary-600 hover:underline"
            >
              {e.bill_number ?? `#${e.bill_id}`}
            </Link>
          ) : (
            <span className="text-xs text-ink-subtle">—</span>
          ),
      },
      {
        key: "status",
        header: "Status",
        width: "10%",
        cell: (e) =>
          e.voided_at ? (
            <Badge tone="danger" size="sm">
              Voided
            </Badge>
          ) : (
            <Badge tone="success" size="sm">
              Active
            </Badge>
          ),
      },
      {
        key: "actions",
        header: "",
        align: "right",
        width: "10%",
        cell: (e) =>
          e.voided_at ? (
            <span className="text-xs text-ink-subtle">—</span>
          ) : canVoid ? (
            <Button
              size="sm"
              variant="outline"
              leftIcon={<Ban className="h-3.5 w-3.5" />}
              className={cn(
                "min-w-[5.5rem] border-rose-200/80 bg-rose-50/40 font-medium text-rose-700",
                "hover:border-rose-300 hover:bg-rose-100/80 hover:text-rose-800",
                "dark:border-rose-800/50 dark:bg-rose-950/25 dark:text-rose-300",
                "dark:hover:border-rose-700/60 dark:hover:bg-rose-950/45 dark:hover:text-rose-200"
              )}
              onClick={() => {
                idemRef.current = null;
                setPending(e);
              }}
              loading={busy && pending?.id === e.id}
            >
              Void
            </Button>
          ) : (
            <span className="text-xs text-ink-subtle">—</span>
          ),
      },
    ],
    [canVoid, busy, pending?.id]
  );

  return (
    <div className="pb-24 lg:pb-0">
      <PageHeader
        eyebrow="Accounts"
        title="Cash book"
        subtitle="Non-bill money movements: expenses, income, and transfers. Owner can void wrong entries — balances reverse automatically."
        actions={
          <Link to="/accounts/cashbook/new" className="hidden sm:inline-flex">
            <Button leftIcon={<Plus className="h-4 w-4" />}>New entry</Button>
          </Link>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {highlightedEntry && (
        <Card className="mb-4 border-emerald-300/80 bg-emerald-50/60 dark:border-emerald-800 dark:bg-emerald-950/40">
          <CardBody className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0 space-y-1">
              <p className="text-sm font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-200">
                Just recorded
              </p>
              <p className="text-2xl font-bold tabular-nums text-ink">
                {formatInr(highlightedEntry.amount)}
                <span className="ml-2 text-base font-medium text-ink-muted">
                  {highlightedEntry.category_name ?? highlightedEntry.entry_type}
                </span>
              </p>
              <p className="text-sm text-ink-muted">
                #{highlightedEntry.id} · {formatDate(highlightedEntry.entry_date)} · {modeLabel(highlightedEntry)}
                {highlightedEntry.description ? ` · ${highlightedEntry.description}` : ""}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link to={`/accounts/cashbook/${highlightedEntry.id}/edit`}>
                <Button variant="secondary">Open entry</Button>
              </Link>
              {canVoid && !highlightedEntry.voided_at && (
                <Button
                  variant="outline"
                  className="border-rose-200 text-rose-700"
                  onClick={() => {
                    idemRef.current = null;
                    setPending(highlightedEntry);
                  }}
                >
                  Void
                </Button>
              )}
            </div>
          </CardBody>
        </Card>
      )}

      <Card className="mb-4">
        <CardBody className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormField label="Type">
              {({ id }) => (
                <Select
                  id={id}
                  value={filters.entry_type ?? ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      entry_type: (e.target.value || undefined) as CashBookEntryType | undefined,
                    })
                  }
                >
                  <option value="">All types</option>
                  <option value="expense">Expense</option>
                  <option value="income">Income</option>
                  <option value="transfer">Transfer</option>
                </Select>
              )}
            </FormField>
            <FormField label="Category">
              {({ id }) => (
                <Select
                  id={id}
                  value={filters.category_id ?? ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      category_id: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                >
                  <option value="">All categories</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
            <FormField label="Account">
              {({ id }) => (
                <Select
                  id={id}
                  value={filters.account_id ?? ""}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      account_id: e.target.value ? Number(e.target.value) : undefined,
                    })
                  }
                >
                  <option value="">All accounts</option>
                  {groupedAccounts.cash.length > 0 && (
                    <optgroup label="Cash">
                      {groupedAccounts.cash.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {groupedAccounts.bank.length > 0 && (
                    <optgroup label="Bank">
                      {groupedAccounts.bank.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </Select>
              )}
            </FormField>
            <FormField label="Status">
              {({ id }) => (
                <Select
                  id={id}
                  value={filters.voided ?? "false"}
                  onChange={(e) =>
                    setFilters({ ...filters, voided: e.target.value as "false" | "true" | "any" })
                  }
                >
                  <option value="false">Active only</option>
                  <option value="true">Voided only</option>
                  <option value="any">Active + voided</option>
                </Select>
              )}
            </FormField>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <FormField label="Date from">
              {({ id }) => (
                <Input
                  id={id}
                  type="date"
                  value={filters.date_from ?? ""}
                  onChange={(e) => setFilters({ ...filters, date_from: e.target.value || undefined })}
                />
              )}
            </FormField>
            <FormField label="Date to">
              {({ id }) => (
                <Input
                  id={id}
                  type="date"
                  value={filters.date_to ?? ""}
                  onChange={(e) => setFilters({ ...filters, date_to: e.target.value || undefined })}
                />
              )}
            </FormField>
            <div className="flex items-end sm:col-span-2 lg:col-span-2">
              {hasActiveFilters ? (
                <Button variant="secondary" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : (
                <p className="pb-2 text-sm text-ink-subtle">Showing active entries by default.</p>
              )}
            </div>
          </div>
        </CardBody>
      </Card>

      {loading && displayRows.length === 0 ? (
        <Table
          columns={columns}
          rows={[]}
          rowKey={(r) => r.id}
          caption="Cash book entries"
          loading
          zebra
          compact
          stickyHeader={false}
          className="mb-4"
        />
      ) : displayRows.length === 0 ? (
        <Card className="mb-4">
          <CardBody>
            <EmptyState
              icon={<ReceiptText />}
              title={error ? "Could not load cash book" : "No cash-book entries"}
              description={
                error
                  ? error
                  : "Record an expense, income, or transfer to see it here."
              }
              action={
                error ? (
                  <Button variant="secondary" onClick={reload}>
                    Retry
                  </Button>
                ) : (
                  <Link to="/accounts/cashbook/new">
                    <Button leftIcon={<Plus className="h-4 w-4" />}>New entry</Button>
                  </Link>
                )
              }
            />
          </CardBody>
        </Card>
      ) : (
        <div className="mb-4">
          <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {filters.entry_type ? (
              <Card
                className={cn(
                  filters.entry_type === "expense" &&
                    "border-rose-200/80 bg-rose-50/50 dark:border-rose-900 dark:bg-rose-950/30",
                  filters.entry_type === "income" &&
                    "border-emerald-200/80 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/30",
                  filters.entry_type === "transfer" &&
                    "border-sky-200/80 bg-sky-50/50 dark:border-sky-900 dark:bg-sky-950/30"
                )}
              >
                <CardBody className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    {filters.entry_type === "expense"
                      ? "Expense total"
                      : filters.entry_type === "income"
                        ? "Income total"
                        : "Transfer total"}
                  </p>
                  <p className="mt-1 v2-mono text-xl font-bold tabular-nums text-ink">
                    {formatInr(amountTotal)}
                  </p>
                  <p className="mt-1 text-xs text-ink-subtle">
                    {total.toLocaleString("en-IN")} entr{total === 1 ? "y" : "ies"} matching filters
                  </p>
                </CardBody>
              </Card>
            ) : (
              <>
                <Card className="border-rose-200/80 bg-rose-50/50 dark:border-rose-900 dark:bg-rose-950/30">
                  <CardBody className="p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-300">
                      Expense total
                    </p>
                    <p className="mt-1 v2-mono text-xl font-bold tabular-nums text-ink">
                      {formatInr(expenseTotal)}
                    </p>
                  </CardBody>
                </Card>
                <Card className="border-emerald-200/80 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/30">
                  <CardBody className="p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">
                      Income total
                    </p>
                    <p className="mt-1 v2-mono text-xl font-bold tabular-nums text-ink">
                      {formatInr(incomeTotal)}
                    </p>
                  </CardBody>
                </Card>
                <Card className="border-sky-200/80 bg-sky-50/50 dark:border-sky-900 dark:bg-sky-950/30">
                  <CardBody className="p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-300">
                      Transfer total
                    </p>
                    <p className="mt-1 v2-mono text-xl font-bold tabular-nums text-ink">
                      {formatInr(transferTotal)}
                    </p>
                  </CardBody>
                </Card>
                <Card className="border-line/80">
                  <CardBody className="p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">
                      All types total
                    </p>
                    <p className="mt-1 v2-mono text-xl font-bold tabular-nums text-ink">
                      {formatInr(amountTotal)}
                    </p>
                    <p className="mt-1 text-xs text-ink-subtle">
                      {total.toLocaleString("en-IN")} entr{total === 1 ? "y" : "ies"} matching filters
                    </p>
                  </CardBody>
                </Card>
              </>
            )}
          </div>
          <div className="space-y-3 lg:hidden">
            {displayRows.map((r) => (
              <CashBookMobileCard
                key={`cashbook-m-${r.id}`}
                entry={r}
                highlighted={Boolean(highlightedEntry && sameEntryId(r.id, highlightedEntry.id))}
                canVoid={canVoid}
                busy={busy && pending?.id === r.id}
                onVoid={() => {
                  idemRef.current = null;
                  setPending(r);
                }}
              />
            ))}
          </div>
          <div className="hidden lg:block">
            <Table
              columns={columns}
              rows={displayRows}
              rowKey={(r) => `cashbook-${r.id}`}
              caption="Cash book entries"
              zebra
              compact
              stickyHeader={false}
              rowClassName={(r) =>
                highlightedEntry && sameEntryId(r.id, highlightedEntry.id)
                  ? "bg-emerald-50/90 dark:bg-emerald-950/40"
                  : undefined
              }
            />
          </div>
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="mt-2" />
        </div>
      )}

      <VoidConfirmDialog
        open={!!pending}
        onClose={() => {
          idemRef.current = null;
          setVoidAuthError("");
          setPending(null);
        }}
        onConfirm={voidEntry}
        title="Void this entry?"
        description={
          pending
            ? `Void this ${pending.entry_type} of ${formatInr(pending.amount)} — balances will be reversed.`
            : ""
        }
        confirmLabel={busy ? "Voiding…" : "Void"}
        authError={voidAuthError || undefined}
      />
      <Link
        to="/accounts/cashbook/new"
        className="fixed bottom-6 right-6 z-30 inline-flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-glow transition-transform hover:scale-105 active:scale-95 lg:hidden"
        aria-label="New cash book entry"
      >
        <Plus className="h-6 w-6" />
      </Link>
    </div>
  );
}
