import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, Search } from "lucide-react";
import { auditApi, DEFAULT_PAGE_LIMIT, type AuditEvent } from "../../api/client";
import PageHeader from "../../components/ui/PageHeader";
import { Card, CardBody } from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import FormField from "../../components/ui/FormField";
import Input from "../../components/ui/Input";
import PaginationBar from "../../components/ui/PaginationBar";
import Select from "../../components/ui/Select";
import Table, { type Column } from "../../components/ui/Table";
import {
  AUDIT_ACTION_OPTIONS,
  AUDIT_ENTITY_TYPE_OPTIONS,
  auditActionLabel,
  auditEntityTypeLabel,
} from "../../lib/auditLabels";
import { formatDateTime } from "../../lib/format";

function metadataSnippet(metadata: Record<string, unknown> | null | undefined): string {
  if (!metadata || Object.keys(metadata).length === 0) return "—";
  return Object.entries(metadata)
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");
}

export default function AuditLogPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const page = await auditApi.listEvents({
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: search.trim() || undefined,
        limit,
        offset,
      });
      setRows(page.items);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit log");
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [actionFilter, entityTypeFilter, dateFrom, dateTo, search, limit, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [actionFilter, entityTypeFilter, dateFrom, dateTo, search]);

  const columns: Column<AuditEvent>[] = useMemo(
    () => [
      {
        key: "when",
        header: "When",
        cell: (row) => <span className="whitespace-nowrap text-sm">{formatDateTime(row.created_at)}</span>,
      },
      {
        key: "user",
        header: "User",
        cell: (row) => (
          <span className="text-sm">{row.user_email ?? (row.user_id != null ? `User #${row.user_id}` : "—")}</span>
        ),
      },
      {
        key: "action",
        header: "Action",
        cell: (row) => <span className="text-sm font-medium">{auditActionLabel(row.action)}</span>,
      },
      {
        key: "entity",
        header: "Entity",
        cell: (row) => (
          <span className="text-sm text-muted">
            {auditEntityTypeLabel(row.entity_type)}
            {row.entity_id != null ? ` #${row.entity_id}` : ""}
          </span>
        ),
      },
      {
        key: "label",
        header: "Label",
        cell: (row) => <span className="text-sm">{row.entity_label ?? "—"}</span>,
      },
      {
        key: "details",
        header: "Details",
        cell: (row) => <span className="text-sm text-muted">{metadataSnippet(row.metadata)}</span>,
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />
            History
          </span>
        }
        title="Audit log"
        subtitle="Central trail of sensitive voids, edits, master deletes, and user admin actions (owner only)."
        actions={
          <Link to="/histories/logins" className="text-sm text-primary hover:underline">
            View login history
          </Link>
        }
      />

      <Card>
        <CardBody className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
          <FormField label="Action">
            {({ id }) => (
              <Select
                id={id}
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
              >
                <option value="">All actions</option>
                {AUDIT_ACTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <FormField label="Entity type">
            {({ id }) => (
              <Select
                id={id}
                value={entityTypeFilter}
                onChange={(e) => setEntityTypeFilter(e.target.value)}
              >
                <option value="">All types</option>
                {AUDIT_ENTITY_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
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
          <FormField label="Search label">
            {({ id }) => (
              <Input
                id={id}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Bill number, customer…"
                leftIcon={<Search />}
              />
            )}
          </FormField>
        </CardBody>
      </Card>

      {error ? (
        <EmptyState title="Could not load audit log" description={error} />
      ) : (
        <>
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            caption="Audit log"
            loading={loading}
            empty={<span className="text-base text-ink-muted">No audit events match your filters.</span>}
          />
          <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
        </>
      )}
    </div>
  );
}
