import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  accountsApi,
  DEFAULT_PAGE_LIMIT,
  type CustomerStatementPage as StatementPage,
  type CustomerStatementRow,
} from "../../api/client";
import { formatDate, formatInr } from "../../lib/format";
import PageHeader from "../../components/ui/PageHeader";
import Button from "../../components/ui/Button";
import Banner from "../../components/ui/Banner";
import Badge from "../../components/ui/Badge";
import { Card, CardBody } from "../../components/ui/Card";
import PaginationBar from "../../components/ui/PaginationBar";
import Input from "../../components/ui/Input";
import Table, { type Column } from "../../components/ui/Table";

const KIND_LABELS: Record<string, { label: string; tone: "primary" | "info" | "danger" | "warning" | "success" | "neutral" }> = {
  bill_created: { label: "Bill created", tone: "primary" },
  bill_edited: { label: "Bill edited", tone: "info" },
  bill_voided: { label: "Bill voided", tone: "danger" },
  payment_received: { label: "Payment", tone: "success" },
  payment_voided: { label: "Payment voided", tone: "danger" },
  setoff: { label: "Set-off", tone: "warning" },
};

export default function CustomerStatementPage() {
  const { id } = useParams<{ id: string }>();
  const customerId = Number(id);

  const [page, setPage] = useState<StatementPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    if (!customerId) return;
    accountsApi
      .statement(customerId, { limit, offset, date_from: from || undefined, date_to: to || undefined })
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [customerId, from, to, limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [from, to]);

  const columns: Column<CustomerStatementRow>[] = useMemo(
    () => [
      {
        key: "date",
        header: "Date",
        cell: (r) => <span className="v2-mono text-sm text-ink-muted">{formatDate(r.event_date)}</span>,
      },
      {
        key: "event",
        header: "Event",
        cell: (r) => {
          const meta = KIND_LABELS[r.kind];
          return meta ? (
            <Badge size="sm" tone={meta.tone}>{meta.label}</Badge>
          ) : (
            <Badge size="sm">{r.kind}</Badge>
          );
        },
      },
      {
        key: "desc",
        header: "Description",
        cell: (r) => (
          <div className="min-w-0">
            <p className="text-sm text-ink">{r.description}</p>
            {r.bill_id && r.bill_number && (
              <Link to={`/sales-bills/${r.bill_id}`} className="v2-mono text-xs text-primary-600 hover:underline">
                {r.bill_number}
              </Link>
            )}
          </div>
        ),
      },
      {
        key: "debit",
        header: "Debit (₹)",
        numeric: true,
        cell: (r) =>
          Number(r.debit_amount) > 0 ? (
            <span className="v2-mono text-rose-700">{formatInr(r.debit_amount)}</span>
          ) : (
            <span className="text-ink-subtle">—</span>
          ),
      },
      {
        key: "credit",
        header: "Credit (₹)",
        numeric: true,
        cell: (r) =>
          Number(r.credit_amount) > 0 ? (
            <span className="v2-mono text-emerald-700">{formatInr(r.credit_amount)}</span>
          ) : (
            <span className="text-ink-subtle">—</span>
          ),
      },
      {
        key: "running",
        header: "Running",
        numeric: true,
        cell: (r) => <span className="v2-mono text-sm font-semibold">{formatInr(r.running_balance)}</span>,
      },
    ],
    []
  );

  return (
    <>
      <PageHeader
        eyebrow="Accounts"
        title={page?.customer_name ?? "Customer statement"}
        subtitle="Chronological list of bills, payments, and set-offs with running balance."
        actions={
          <Link to="/accounts/customers">
            <Button variant="ghost" leftIcon={<ArrowLeft className="h-4 w-4" />}>
              Back
            </Button>
          </Link>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      {page && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Card>
            <CardBody>
              <p className="text-xs uppercase text-ink-subtle">Net balance</p>
              <p className="v2-mono mt-1 text-xl font-bold text-ink">{formatInr(page.current_net_balance)}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-xs uppercase text-ink-subtle">Customer owes me</p>
              <p className="v2-mono mt-1 text-xl font-semibold text-emerald-700">{formatInr(page.current_debit_balance)}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <p className="text-xs uppercase text-ink-subtle">I owe customer</p>
              <p className="v2-mono mt-1 text-xl font-semibold text-amber-700">{formatInr(page.current_credit_balance)}</p>
            </CardBody>
          </Card>
        </div>
      )}

      <Card className="mb-4">
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Date from</label>
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">Date to</label>
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </CardBody>
      </Card>

      {page && (
        <>
          <Table columns={columns} rows={page.items} rowKey={(r, i) => `${r.event_at}-${i}`} caption="Customer statement" />
          <PaginationBar total={page.total} limit={limit} offset={offset} onPageChange={setOffset} className="mt-2" />
        </>
      )}
    </>
  );
}
