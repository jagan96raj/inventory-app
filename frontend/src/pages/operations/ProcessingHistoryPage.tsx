import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Cog } from "lucide-react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  type PageOut,
  type ProcessingJobListItem,
} from "../../api/client";
import OperationPageHeader from "../../components/OperationPageHeader";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import PaginationBar from "../../components/ui/PaginationBar";
import Skeleton from "../../components/ui/Skeleton";
import { cn } from "../../lib/cn";
import { formatDateTime, formatQtyKg } from "../../lib/format";
import { totalOutputKg } from "../../lib/processingSummary";
const LIST_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-left text-base font-semibold uppercase tracking-wide text-ink-muted";
const LIST_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

export default function ProcessingHistoryPage() {
  const [rows, setRows] = useState<ProcessingJobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<ProcessingJobListItem>>(
        `/api/operations/processing?status=completed&limit=${limit}&offset=${offset}`
      )
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch(() => {
        setRows([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <OperationPageHeader
        title="Processing history"
        subtitle="Completed jobs — newest first. Open a job to review batches, summary, and mass balance."
        formTo="/operations/processing"
        historyTo="/histories/processing"
        mode="history"
      />

      <Card>
        <CardHeader
          title="Completed jobs"
          subtitle={`${total} completed job${total === 1 ? "" : "s"}`}
        />
        <CardBody>
          {loading ? (
            <div className="space-y-3" aria-busy="true">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-xl" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<Cog className="h-8 w-8" />}
              title="No completed jobs yet"
              description="Finish an open processing job to see it here."
              action={
                <Link to="/operations/processing">
                  <Button variant="secondary">Open jobs</Button>
                </Link>
              }
            />
          ) : (
            <>
              <div className="hidden overflow-x-auto md:block">
                <table className="v2-data-table min-w-full w-full text-base">
                  <caption className="sr-only">Completed processing jobs</caption>
                  <thead>
                    <tr>
                      <th scope="col" className={LIST_TH}>
                        Product
                      </th>
                      <th scope="col" className={LIST_TH}>
                        Brand
                      </th>
                      <th scope="col" className={LIST_TH}>
                        Opened
                      </th>
                      <th scope="col" className={LIST_TH}>
                        Completed
                      </th>
                      <th scope="col" className={cn(LIST_TH, "text-right")}>
                        Batches
                      </th>
                      <th scope="col" className={cn(LIST_TH, "text-right")}>
                        Output kg
                      </th>
                      <th scope="col" className={cn(LIST_TH, "text-right")}>
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((j) => {
                      const outputKg = j.summary ? totalOutputKg(j.summary) : 0;
                      return (
                        <tr
                          key={j.id}
                          className="border-l-4 border-l-emerald-500 bg-emerald-50/35 dark:bg-emerald-950/20 [&>td]:bg-emerald-50/35 dark:[&>td]:bg-emerald-950/20"
                        >
                          <td className={cn(LIST_TD, "font-semibold text-ink")}>
                            {j.input_product_name ?? `#${j.input_product_id}`}
                          </td>
                          <td className={LIST_TD}>{j.input_brand_name ?? `#${j.input_brand_id}`}</td>
                          <td className={cn(LIST_TD, "v2-mono text-ink-muted")}>
                            {formatDateTime(j.opened_at)}
                          </td>
                          <td className={cn(LIST_TD, "v2-mono text-ink-muted")}>
                            {j.completed_at ? formatDateTime(j.completed_at) : "—"}
                          </td>
                          <td className={cn(LIST_TD, "v2-mono text-right tabular-nums")}>
                            {j.summary?.batch_count ?? 0}
                          </td>
                          <td className={cn(LIST_TD, "v2-mono text-right font-semibold tabular-nums")}>
                            {formatQtyKg(outputKg)}
                          </td>
                          <td className={cn(LIST_TD, "text-right")}>
                            <Link to={`/operations/processing/${j.id}`}>
                              <Button
                                variant="secondary"
                                size="sm"
                                rightIcon={<ArrowRight className="h-4 w-4" />}
                              >
                                View
                              </Button>
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="space-y-3 md:hidden">
                {rows.map((j) => {
                  const outputKg = j.summary ? totalOutputKg(j.summary) : 0;
                  return (
                    <div
                      key={j.id}
                      className="rounded-2xl border border-emerald-200/70 border-l-4 border-l-emerald-500 bg-emerald-50/50 p-4 dark:border-emerald-800/50 dark:bg-emerald-950/30"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-lg font-bold text-ink">
                            {j.input_product_name ?? `#${j.input_product_id}`}
                          </p>
                          <p className="mt-0.5 text-base text-ink-muted">
                            {j.input_brand_name ?? `#${j.input_brand_id}`}
                          </p>
                          <p className="mt-2 v2-mono text-sm text-ink-muted">
                            Completed {j.completed_at ? formatDateTime(j.completed_at) : "—"}
                          </p>
                          <p className="mt-1 text-sm text-ink-muted">
                            {j.summary?.batch_count ?? 0} batch
                            {(j.summary?.batch_count ?? 0) === 1 ? "" : "es"} · {formatQtyKg(outputKg)} output
                          </p>
                        </div>
                        <Badge tone="success">Completed</Badge>
                      </div>
                      <div className="mt-4">
                        <Link to={`/operations/processing/${j.id}`} className="block">
                          <Button className="w-full" rightIcon={<ArrowRight className="h-4 w-4" />}>
                            View job
                          </Button>
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>

              <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
            </>
          )}
        </CardBody>
      </Card>
    </>
  );
}
