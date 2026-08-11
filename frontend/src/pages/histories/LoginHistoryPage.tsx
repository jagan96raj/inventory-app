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
        <CardBody className="grid min-w-0 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <FormField label="Result" className="min-w-0">
            {({ id }) => (
              <Select id={id} value={successFilter} onChange={(e) => setSuccessFilter(e.target.value)}>
                <option value="">All</option>
                <option value="true">Success only</option>
                <option value="false">Failed only</option>
              </Select>
            )}
          </FormField>
          <FormField label="From date" className="min-w-0">
            {({ id }) => (
              <Input id={id} type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            )}
          </FormField>
          <FormField label="To date" className="min-w-0">
            {({ id }) => (
              <Input id={id} type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            )}
          </FormField>
          <FormField label="Search email" className="min-w-0">
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
          <div className="space-y-3 lg:hidden">
            {loading ? (
              <Card>
                <CardBody className="text-sm text-ink-muted">Loading…</CardBody>
              </Card>
            ) : rows.length === 0 ? (
              <Card>
                <CardBody className="text-sm text-ink-muted">No login events match your filters.</CardBody>
              </Card>
            ) : (
              rows.map((row) => (
                <Card key={row.id} className="min-w-0 overflow-hidden">
                  <CardBody className="space-y-2 p-4">
                    <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-ink">{row.email}</p>
                        <p className="text-xs text-ink-muted">{formatDateTime(row.created_at)}</p>
                      </div>
                      <Badge tone={row.success ? "success" : "danger"}>{row.success ? "Success" : "Failed"}</Badge>
                    </div>
                    <dl className="grid grid-cols-2 gap-2 text-sm">
                      <div className="min-w-0">
                        <dt className="text-ink-subtle">Reason</dt>
                        <dd className="text-ink">{loginFailureReasonLabel(row.failure_reason)}</dd>
                      </div>
                      <div className="min-w-0">
                        <dt className="text-ink-subtle">IP</dt>
                        <dd className="truncate text-ink">{row.ip_address ?? "—"}</dd>
                      </div>
                    </dl>
                  </CardBody>
                </Card>
              ))
            )}
          </div>
          <div className="hidden lg:block">
            <Table
              columns={columns}
              rows={rows}
              rowKey={(row) => row.id}
              caption="Login history"
              loading={loading}
              empty={<span className="text-base text-ink-muted">No login events match your filters.</span>}
            />
          </div>
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
        </>
      )}
    </div>
  );
}
