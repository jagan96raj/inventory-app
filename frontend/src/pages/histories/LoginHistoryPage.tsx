import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { LogIn, Search } from "lucide-react";
import { DEFAULT_PAGE_LIMIT, loginHistoryApi, type LoginEvent } from "../../api/client";
import PageHeader from "../../components/ui/PageHeader";
import Badge from "../../components/ui/Badge";
import { Card, CardBody } from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import FormField from "../../components/ui/FormField";
import Input from "../../components/ui/Input";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import Table, { type Column } from "../../components/ui/Table";
import { loginFailureReasonLabel } from "../../lib/loginHistoryLabels";
import { formatDateTime } from "../../lib/format";

export default function LoginHistoryPage() {
  const [rows, setRows] = useState<LoginEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successFilter, setSuccessFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await loginHistoryApi.listEvents({
        success: successFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: search.trim() || undefined,
        limit,
        offset,
      });
      setRows(page.items);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load login history");
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [successFilter, dateFrom, dateTo, search, limit, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [successFilter, dateFrom, dateTo, search]);

  const columns: Column<LoginEvent>[] = useMemo(
    () => [
      {
        key: "when",
        header: "When",
        cell: (row) => <span className="whitespace-nowrap text-sm">{formatDateTime(row.created_at)}</span>,
      },
      {
        key: "email",
        header: "Email",
        cell: (row) => <span className="text-sm">{row.email}</span>,
      },
      {
        key: "user",
        header: "User",
        cell: (row) => (
          <span className="text-sm text-muted">{row.user_id != null ? `User #${row.user_id}` : "—"}</span>
        ),
      },
      {
        key: "result",
        header: "Result",
        cell: (row) => (
          <Badge tone={row.success ? "success" : "danger"}>{row.success ? "Success" : "Failed"}</Badge>
        ),
      },
      {
        key: "reason",
        header: "Reason",
        cell: (row) => (
          <span className="text-sm text-muted">{loginFailureReasonLabel(row.failure_reason)}</span>
        ),
      },
      {
        key: "ip",
        header: "IP",
        cell: (row) => <span className="text-sm text-muted">{row.ip_address ?? "—"}</span>,
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <LogIn className="h-3.5 w-3.5" aria-hidden="true" />
            History
          </span>
        }
        title="Login history"
        subtitle="Sign-in attempts including successes and failures (owner only)."
        actions={
          <Link to="/histories/audit" className="text-sm text-primary hover:underline">
            View audit log
          </Link>
        }
      />

      <Card>
        <CardBody className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <FormField label="Result">
            {({ id }) => (
              <Select id={id} value={successFilter} onChange={(e) => setSuccessFilter(e.target.value)}>
                <option value="">All</option>
                <option value="true">Success only</option>
                <option value="false">Failed only</option>
              </Select>
            )}
          </FormField>
          <FormField label="From date">
            {({ id }) => (
              <Input id={id} type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            )}
          </FormField>
          <FormField label="To date">
            {({ id }) => (
              <Input id={id} type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            )}
          </FormField>
          <FormField label="Search email">
            {({ id }) => (
              <Input
                id={id}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="user@example.com"
                leftIcon={<Search />}
              />
            )}
          </FormField>
        </CardBody>
      </Card>

      {error ? (
        <EmptyState title="Could not load login history" description={error} />
      ) : (
        <>
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            caption="Login history"
            loading={loading}
            empty={<span className="text-base text-ink-muted">No login events match your filters.</span>}
          />
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
        </>
      )}
    </div>
  );
}
