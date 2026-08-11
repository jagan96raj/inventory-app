import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileSearch, Users } from "lucide-react";
import {
  accountsApi,
  DEFAULT_PAGE_LIMIT,
  type CustomerBalanceRow,
} from "../../api/client";
import { formatCustomerName } from "../../lib/customerDisplay";
import { formatDateTime, formatInr } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Banner from "../../components/ui/Banner";
import EmptyState from "../../components/ui/EmptyState";
import { Card, CardBody } from "../../components/ui/Card";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import Input from "../../components/ui/Input";
import Table, { type Column } from "../../components/ui/Table";

type Filter = "any" | "positive" | "zero";

export default function CustomerBalancesPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<CustomerBalanceRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("any");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [filter, debounced]);

  const load = useCallback(() => {
    accountsApi
      .customers({ limit, offset, has_balance: filter, search: debounced || undefined })
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(e.message));
  }, [filter, debounced, limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<CustomerBalanceRow>[] = useMemo(
    () => [
      {
        key: "name",
        header: "Customer",
        cell: (r) => {
          const name = formatCustomerName(r.customer_name);
          return (
            <Link
              to={`/accounts/customers/${r.customer_id}`}
              className="block max-w-[14rem] truncate text-sm font-semibold tracking-tight text-ink hover:text-primary-700 sm:max-w-[18rem] md:max-w-[22rem]"
              title={name}
            >
              {name}
            </Link>
          );
        },
      },
      {
        key: "credit",
        header: "Customer owes (₹)",
        numeric: true,
        cell: (r) => (
          <span className={Number(r.debit_balance) > 0 ? "v2-mono font-semibold text-emerald-700" : "v2-mono text-ink-subtle"}>
            {formatInr(r.debit_balance)}
          </span>
        ),
      },
      {
        key: "debit",
        header: "I owe (₹)",
        numeric: true,
        cell: (r) => (
          <span className={Number(r.credit_balance) > 0 ? "v2-mono font-semibold text-amber-700" : "v2-mono text-ink-subtle"}>
            {formatInr(r.credit_balance)}
          </span>
        ),
      },
      {
        key: "net",
        header: "Net (₹)",
        numeric: true,
        cell: (r) => <span className="v2-mono text-base font-semibold">{formatInr(r.net_balance)}</span>,
      },
      {
        key: "activity",
        header: "Last activity",
        cell: (r) => (
          <span className="text-xs text-ink-muted">
            {r.last_activity_at ? formatDateTime(r.last_activity_at) : "—"}
          </span>
        ),
      },
      {
        key: "actions",
        header: "",
        align: "right",
        cell: (r) => (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<FileSearch className="h-3.5 w-3.5" />}
            onClick={() => navigate(`/accounts/customers/${r.customer_id}`)}
          >
            Statement
          </Button>
        ),
      },
    ],
    [navigate]
  );

  return (
    <div className="min-w-0">
      <PageHeader
        eyebrow="Accounts"
        title="Customer balances"
        subtitle="Each customer's running credit / debit position and last activity."
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <Card className="mb-4">
        <CardBody className="grid min-w-0 gap-3 sm:grid-cols-3">
          <div className="min-w-0 space-y-1 sm:col-span-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Search</label>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Customer name, phone…"
              className="min-w-0"
            />
          </div>
          <div className="min-w-0 space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Balance</label>
            <Select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
              <option value="any">All customers</option>
              <option value="positive">Has balance</option>
              <option value="zero">Zero balance</option>
            </Select>
          </div>
        </CardBody>
      </Card>

      {rows.length === 0 && total === 0 ? (
        <Card>
          <CardBody>
            <EmptyState icon={<Users />} title="No customers" description="Add a customer to see balances." />
          </CardBody>
        </Card>
      ) : (
        <>
          <div className="space-y-3 lg:hidden">
            {rows.map((r) => {
              const name = formatCustomerName(r.customer_name);
              return (
                <Card key={r.customer_id} className="overflow-hidden">
                  <CardBody className="space-y-3 p-4">
                    <div className="min-w-0">
                      <Link
                        to={`/accounts/customers/${r.customer_id}`}
                        className="block truncate text-base font-semibold tracking-tight text-ink hover:text-primary-700"
                        title={name}
                      >
                        {name}
                      </Link>
                      <p className="mt-1 text-xs text-ink-muted">
                        {r.last_activity_at ? `Last activity ${formatDateTime(r.last_activity_at)}` : "No activity yet"}
                      </p>
                    </div>
                    <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                      <div className="min-w-0">
                        <dt className="text-ink-subtle">Customer owes</dt>
                        <dd
                          className={
                            Number(r.debit_balance) > 0
                              ? "v2-mono font-semibold text-emerald-700"
                              : "v2-mono text-ink-subtle"
                          }
                        >
                          {formatInr(r.debit_balance)}
                        </dd>
                      </div>
                      <div className="min-w-0">
                        <dt className="text-ink-subtle">I owe</dt>
                        <dd
                          className={
                            Number(r.credit_balance) > 0
                              ? "v2-mono font-semibold text-amber-700"
                              : "v2-mono text-ink-subtle"
                          }
                        >
                          {formatInr(r.credit_balance)}
                        </dd>
                      </div>
                      <div className="min-w-0 col-span-2 sm:col-span-1">
                        <dt className="text-ink-subtle">Net</dt>
                        <dd className="v2-mono font-semibold text-ink">{formatInr(r.net_balance)}</dd>
                      </div>
                    </dl>
                    <div className="border-t border-line/60 pt-3">
                      <Button
                        size="md"
                        variant="secondary"
                        className="min-h-10 w-full sm:w-auto"
                        leftIcon={<FileSearch className="h-3.5 w-3.5" />}
                        onClick={() => navigate(`/accounts/customers/${r.customer_id}`)}
                      >
                        Statement
                      </Button>
                    </div>
                  </CardBody>
                </Card>
              );
            })}
          </div>
          <div className="hidden lg:block">
            <Table columns={columns} rows={rows} rowKey={(r) => r.customer_id} caption="Customer balances" />
          </div>
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} className="mt-2" />
        </>
      )}
    </div>
  );
}
