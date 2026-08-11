import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  Banknote,
  Coins,
  HandCoins,
  Plus,
  ReceiptText,
  Settings2,
  Users,
  Wallet,
} from "lucide-react";
import {
  accountsApi,
  type AccountsSummary,
  type BankAccountBalance,
  type CashBookEntry,
} from "../../api/client";
import { formatDate, formatInr } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import Stat from "../../components/ui/Stat";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import Table, { type Column } from "../../components/ui/Table";
import { cn } from "../../lib/cn";

const NOWRAP = "whitespace-nowrap";

function entryKindLabel(entry: CashBookEntry): string {
  if (entry.entry_type === "income") return "Income";
  if (entry.entry_type === "transfer") return "Transfer";
  return "Expense";
}

function entryTypeBadge(entry: CashBookEntry) {
  if (entry.entry_type === "income") return <Badge tone="success" size="sm">Income</Badge>;
  if (entry.entry_type === "transfer") return <Badge tone="info" size="sm">Transfer</Badge>;
  return <Badge tone="danger" size="sm">Expense</Badge>;
}

function entrySourceLabel(entry: CashBookEntry): string {
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

function amountTone(entry: CashBookEntry): string {
  if (entry.entry_type === "income") return "text-emerald-700 dark:text-emerald-300";
  if (entry.entry_type === "transfer") return "text-indigo-700 dark:text-indigo-300";
  return "text-rose-700 dark:text-rose-300";
}

const NESTED_TABLE_CLASS =
  "rounded-none border-0 border-t border-line/70 bg-transparent shadow-none";

export default function AccountsDashboardPage() {
  const [summary, setSummary] = useState<AccountsSummary | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    accountsApi
      .summary()
      .then(setSummary)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const bankColumns: Column<BankAccountBalance>[] = useMemo(
    () => [
      {
        key: "name",
        header: "Bank",
        width: "32%",
        cell: (bank) => (
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate font-semibold text-ink">{bank.name}</span>
            {bank.is_default ? <Badge size="sm" tone="primary">Default</Badge> : null}
            {!bank.is_active ? <Badge size="sm" tone="neutral">Inactive</Badge> : null}
          </div>
        ),
      },
      {
        key: "account",
        header: "A/C ending",
        width: "11%",
        className: NOWRAP,
        cell: (bank) => (
          <span className="v2-mono text-sm text-ink-muted">
            {bank.account_number_last4 ? `••${bank.account_number_last4}` : "—"}
          </span>
        ),
      },
      {
        key: "ifsc",
        header: "IFSC",
        width: "14%",
        className: NOWRAP,
        cell: (bank) => (
          <span className="v2-mono text-sm text-ink-muted">{bank.ifsc ?? "—"}</span>
        ),
      },
      {
        key: "opening",
        header: "Opening balance",
        width: "21%",
        numeric: true,
        className: NOWRAP,
        cell: (bank) => (
          <span className="v2-mono text-sm text-ink-muted">{formatInr(bank.opening_balance)}</span>
        ),
      },
      {
        key: "closing",
        header: "Closing balance",
        width: "22%",
        numeric: true,
        className: NOWRAP,
        cell: (bank) => (
          <span className="v2-mono font-semibold text-ink">{formatInr(bank.balance)}</span>
        ),
      },
    ],
    []
  );

  const entryColumns: Column<CashBookEntry>[] = useMemo(
    () => [
      {
        key: "date",
        header: "Date",
        width: "11%",
        className: NOWRAP,
        cell: (entry) => (
          <span className="v2-mono text-sm text-ink-muted">{formatDate(entry.entry_date)}</span>
        ),
      },
      {
        key: "type",
        header: "Type",
        width: "10%",
        className: NOWRAP,
        cell: (entry) => entryTypeBadge(entry),
      },
      {
        key: "category",
        header: "Category",
        width: "22%",
        cell: (entry) => (
          <span className="block truncate font-medium text-ink">
            {entry.category_name ?? entryKindLabel(entry)}
          </span>
        ),
      },
      {
        key: "payment",
        header: "Payment",
        width: "22%",
        cell: (entry) => (
          <span className="block truncate text-sm text-ink-muted">{entrySourceLabel(entry)}</span>
        ),
      },
      {
        key: "bill",
        header: "Bill",
        width: "13%",
        className: NOWRAP,
        cell: (entry) =>
          entry.bill_number ? (
            <Link
              to={`/sales-bills/${entry.bill_id}`}
              className="v2-mono text-sm font-medium text-primary-600 hover:underline"
            >
              {entry.bill_number}
            </Link>
          ) : (
            <span className="text-sm text-ink-subtle">—</span>
          ),
      },
      {
        key: "amount",
        header: "Amount",
        width: "14%",
        numeric: true,
        className: NOWRAP,
        cell: (entry) => (
          <span className={cn("v2-mono font-semibold tabular-nums", amountTone(entry))}>
            {formatInr(entry.amount)}
          </span>
        ),
      },
    ],
    []
  );

  return (
    <>
      <PageHeader
        eyebrow="Accounts"
        title="Accounts dashboard"
        subtitle="Live cash, bank, and customer balances. Powered by bills, payments, and cash book entries."
        actions={
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            <Link to="/accounts/cashbook/new?type=expense" className="min-w-0 flex-1 sm:flex-none">
              <Button variant="secondary" leftIcon={<ArrowUpRight className="h-4 w-4" />} className="w-full sm:w-auto">
                <span className="sm:hidden">Expense</span>
                <span className="hidden sm:inline">Record expense</span>
              </Button>
            </Link>
            <Link to="/accounts/cashbook/new?type=income" className="min-w-0 flex-1 sm:flex-none">
              <Button variant="secondary" leftIcon={<ArrowDownLeft className="h-4 w-4" />} className="w-full sm:w-auto">
                <span className="sm:hidden">Income</span>
                <span className="hidden sm:inline">Record income</span>
              </Button>
            </Link>
            <Link to="/accounts/cashbook/new?type=transfer" className="min-w-0 flex-1 sm:flex-none">
              <Button variant="secondary" leftIcon={<ArrowLeftRight className="h-4 w-4" />} className="w-full sm:w-auto">
                Transfer
              </Button>
            </Link>
            <Link to="/accounts/setup" className="min-w-0 flex-1 sm:flex-none">
              <Button variant="ghost" leftIcon={<Settings2 className="h-4 w-4" />} className="w-full sm:w-auto">
                <span className="sm:hidden">Setup</span>
                <span className="hidden sm:inline">Opening balances</span>
              </Button>
            </Link>
          </div>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {!summary ? (
        <Card>
          <CardBody>
            <p className="text-sm text-ink-muted">Loading summary…</p>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Stat
              label="Cash on hand"
              value={formatInr(summary.cash_balance)}
              icon={<Coins />}
              tone="primary"
            />
            <Stat
              label="Total bank balance"
              value={formatInr(summary.total_bank_balance)}
              icon={<Banknote />}
              tone="info"
            />
            <Stat
              label="Total money"
              value={formatInr(summary.total_money)}
              icon={<Wallet />}
              tone="primary"
              footer="Cash + all bank accounts"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Stat
              label="Customers owe me"
              value={formatInr(summary.total_customer_debit)}
              icon={<HandCoins />}
              tone="success"
              footer="Total customer debit balance"
            />
            <Stat
              label="I owe customers"
              value={formatInr(summary.total_customer_credit)}
              icon={<Users />}
              tone="warning"
              footer="Total customer credit balance"
            />
          </div>

          <Card className="overflow-hidden">
            <CardHeader
              title="Accounts"
              subtitle="Opening and closing balance per account."
              actions={
                <Link to="/accounts/bank-accounts">
                  <Button size="sm" variant="ghost">
                    Manage
                  </Button>
                </Link>
              }
            />
            {summary.bank_accounts.length === 0 ? (
              <CardBody>
                <EmptyState
                  icon={<Banknote />}
                  title="No bank accounts"
                  description="Add a bank account to start recording bank payments and transfers."
                  action={
                    <Link to="/accounts/bank-accounts">
                      <Button leftIcon={<Plus className="h-4 w-4" />}>Add bank account</Button>
                    </Link>
                  }
                />
              </CardBody>
            ) : (
              <>
                <div className="space-y-3 px-4 pb-4 lg:hidden">
                  {summary.bank_accounts.map((bank) => (
                    <div
                      key={bank.id}
                      className="space-y-2 rounded-2xl border border-line/80 bg-surface-subtle/50 p-4"
                    >
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <span className="truncate font-semibold text-ink">{bank.name}</span>
                        {bank.is_default ? <Badge size="sm" tone="primary">Default</Badge> : null}
                        {!bank.is_active ? <Badge size="sm" tone="neutral">Inactive</Badge> : null}
                      </div>
                      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                        <div>
                          <dt className="text-ink-subtle">A/C ending</dt>
                          <dd className="v2-mono text-ink-muted">
                            {bank.account_number_last4 ? `••${bank.account_number_last4}` : "—"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">IFSC</dt>
                          <dd className="v2-mono truncate text-ink-muted">{bank.ifsc ?? "—"}</dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Opening</dt>
                          <dd className="v2-mono text-ink-muted">{formatInr(bank.opening_balance)}</dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Closing</dt>
                          <dd className="v2-mono font-semibold text-ink">{formatInr(bank.balance)}</dd>
                        </div>
                      </dl>
                    </div>
                  ))}
                </div>
                <div className="hidden lg:block">
                  <Table
                    columns={bankColumns}
                    rows={summary.bank_accounts}
                    rowKey={(b) => b.id}
                    caption="Bank account balances"
                    zebra
                    compact
                    stickyHeader={false}
                    className={NESTED_TABLE_CLASS}
                    headerClassName="text-xs"
                  />
                </div>
              </>
            )}
          </Card>

          <Card className="overflow-hidden">
            <CardHeader
              title="Recent cash book entries"
              subtitle="Last 10 non-bill money movements"
              actions={
                <Link to="/accounts/cashbook">
                  <Button size="sm" variant="ghost">
                    Open cash book
                  </Button>
                </Link>
              }
            />
            {summary.recent_entries.length === 0 ? (
              <CardBody>
                <EmptyState
                  icon={<ReceiptText />}
                  title="No entries yet"
                  description="Record your first cash-book entry."
                  action={
                    <Link to="/accounts/cashbook/new">
                      <Button leftIcon={<Plus className="h-4 w-4" />}>New entry</Button>
                    </Link>
                  }
                />
              </CardBody>
            ) : (
              <>
                <div className="space-y-3 px-4 pb-4 lg:hidden">
                  {summary.recent_entries.map((entry) => (
                    <div
                      key={entry.id}
                      className="space-y-2 rounded-2xl border border-line/80 bg-surface-subtle/50 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            {entryTypeBadge(entry)}
                            <span className="v2-mono text-sm text-ink-muted">{formatDate(entry.entry_date)}</span>
                          </div>
                          <p className="truncate font-medium text-ink">
                            {entry.category_name ?? entryKindLabel(entry)}
                          </p>
                          <p className="truncate text-sm text-ink-muted">{entrySourceLabel(entry)}</p>
                        </div>
                        <p className={cn("v2-mono shrink-0 text-lg font-bold tabular-nums", amountTone(entry))}>
                          {formatInr(entry.amount)}
                        </p>
                      </div>
                      {entry.bill_number ? (
                        <Link
                          to={`/sales-bills/${entry.bill_id}`}
                          className="v2-mono text-sm font-medium text-primary-600 hover:underline"
                        >
                          {entry.bill_number}
                        </Link>
                      ) : null}
                    </div>
                  ))}
                </div>
                <div className="hidden lg:block">
                  <Table
                    columns={entryColumns}
                    rows={summary.recent_entries}
                    rowKey={(e) => e.id}
                    caption="Recent cash book entries"
                    zebra
                    compact
                    stickyHeader={false}
                    className={NESTED_TABLE_CLASS}
                    headerClassName="text-xs"
                  />
                </div>
              </>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
