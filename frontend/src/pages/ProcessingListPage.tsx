import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Cog, History, Package, Plus } from "lucide-react";
import { api, DEFAULT_PAGE_LIMIT, idempotencyHeaders, newIdempotencyKey, type PageOut, type ProcessingJob, type ProcessingJobListItem } from "../api/client";
import { searchBrands, searchProducts } from "../lib/masterSearch";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import Banner from "../components/ui/Banner";
import FormField from "../components/ui/FormField";
import AsyncSearchCombobox from "../components/ui/AsyncSearchCombobox";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import PaginationBar from "../components/ui/PaginationBar";
import Skeleton from "../components/ui/Skeleton";
import Badge from "../components/ui/Badge";
import Modal from "../components/ui/Modal";
import { formatDateTime } from "../lib/format";
import { cn } from "../lib/cn";

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Error";
}

const LIST_TH =
  "border-b border-line bg-surface-muted/70 px-5 py-3.5 text-left text-base font-semibold uppercase tracking-wide text-ink-muted";
const LIST_TD = "border-b border-line/70 px-5 py-4 align-middle text-base text-ink";

export default function ProcessingListPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<ProcessingJobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [completedTotal, setCompletedTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const limit = DEFAULT_PAGE_LIMIT;
  const [saving, setSaving] = useState(false);
  const idemKeyRef = useRef<string | null>(null);
  const [jobOpen, setJobOpen] = useState(false);
  const [form, setForm] = useState({ input_product_id: "", input_brand_id: "" });
  const [selectedProductLabel, setSelectedProductLabel] = useState("");

  const loadJobs = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<ProcessingJobListItem>>(`/api/operations/processing?status=open&limit=${limit}&offset=${offset}`)
      .then((page) => {
        setJobs(page.items);
        setTotal(page.total);
      })
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false));
  }, [limit, offset]);

  const loadCompletedCount = useCallback(() => {
    api
      .get<PageOut<ProcessingJobListItem>>("/api/operations/processing?status=completed&limit=1&offset=0")
      .then((page) => setCompletedTotal(page.total))
      .catch(() => setCompletedTotal(0));
  }, []);

  useEffect(() => {
    loadJobs();
    loadCompletedCount();
  }, [loadJobs, loadCompletedCount]);

  const openJobs = jobs;
  const completedCount = completedTotal;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!form.input_product_id || !form.input_brand_id) {
      setError("Select product and brand");
      idemKeyRef.current = null;
      return;
    }
    if (!idemKeyRef.current) idemKeyRef.current = newIdempotencyKey();
    setSaving(true);
    try {
      const job = await api.post<ProcessingJob>(
        "/api/operations/processing",
        {
          input_product_id: Number(form.input_product_id),
          input_brand_id: Number(form.input_brand_id),
        },
        { headers: idempotencyHeaders(idemKeyRef.current) }
      );
      idemKeyRef.current = null;
      navigate(`/operations/processing/${job.id}?from=open`);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const openJobDialog = () => {
    idemKeyRef.current = null;
    setForm({ input_product_id: "", input_brand_id: "" });
    setSelectedProductLabel("");
    setJobOpen(true);
  };

  const closeJobDialog = () => {
    setJobOpen(false);
    setForm({ input_product_id: "", input_brand_id: "" });
    setSelectedProductLabel("");
  };

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Processing"
        subtitle="Open a job per raw product and brand. Record batches incrementally — input, output, balance return, and waste. Mass-balance guard with 100 kg tolerance enforced on submit."
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to="/histories/processing">
              <Button variant="secondary" leftIcon={<History className="h-4 w-4" />}>
                View history
              </Button>
            </Link>
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openJobDialog}>
              Open job
            </Button>
          </div>
        }
      />

      {error && (
        <Banner tone="danger" className="mb-4" onClose={() => setError("")}>
          {error}
        </Banner>
      )}

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <Card className="border-primary-200/70 bg-gradient-to-br from-primary-50/80 via-surface to-violet-50/40 dark:border-primary-800/40 dark:from-primary-950/35 dark:via-surface dark:to-violet-950/25">
          <CardBody className="flex items-center gap-4 p-5">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-violet-600 text-white shadow-md">
              <Cog className="h-6 w-6" aria-hidden="true" />
            </span>
            <div>
              <p className="text-sm font-medium text-primary-700/80 dark:text-primary-300/80">Open jobs</p>
              <p className="text-3xl font-bold text-primary-900 dark:text-primary-50">{openJobs.length}</p>
            </div>
          </CardBody>
        </Card>
        <Card className="border-line/80 bg-surface">
          <CardBody className="flex items-center gap-4 p-5">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-surface-muted text-ink-muted ring-1 ring-line">
              <Package className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink-muted">Completed jobs</p>
              <p className="text-3xl font-bold text-ink">{completedCount}</p>
            </div>
            {completedCount > 0 && (
              <Link to="/histories/processing">
                <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-4 w-4" />}>
                  View all
                </Button>
              </Link>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Open jobs"
          subtitle="Continue an in-progress job to record input or output batches."
        />
        <CardBody>
          {loading ? (
            <div className="space-y-3" aria-busy="true">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-xl" />
              ))}
            </div>
          ) : openJobs.length === 0 ? (
            <EmptyState
              icon={<Cog className="h-8 w-8" />}
              title="No open jobs"
              description="Open a new processing job to get started."
              action={
                <Button leftIcon={<Plus className="h-4 w-4" />} onClick={openJobDialog}>
                  Open job
                </Button>
              }
            />
          ) : (
            <>
              <div className="hidden overflow-x-auto md:block">
                <table className="v2-data-table min-w-full w-full text-base">
                  <caption className="sr-only">Open processing jobs</caption>
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
                      <th scope="col" className={cn(LIST_TH, "text-right")}>
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {openJobs.map((j) => (
                      <tr
                        key={j.id}
                        className="border-l-4 border-l-primary-500 bg-primary-50/40 dark:bg-primary-950/25 [&>td]:bg-primary-50/40 dark:[&>td]:bg-primary-950/25"
                      >
                        <td className={cn(LIST_TD, "font-semibold text-primary-900 dark:text-primary-100")}>
                          {j.input_product_name ?? `#${j.input_product_id}`}
                        </td>
                        <td className={LIST_TD}>{j.input_brand_name ?? `#${j.input_brand_id}`}</td>
                        <td className={cn(LIST_TD, "v2-mono text-ink-muted")}>
                          {formatDateTime(j.opened_at)}
                        </td>
                        <td className={cn(LIST_TD, "text-right")}>
                          <Link to={`/operations/processing/${j.id}?from=open`}>
                            <Button
                              variant="secondary"
                              size="sm"
                              rightIcon={<ArrowRight className="h-4 w-4" />}
                            >
                              Continue
                            </Button>
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="space-y-3 md:hidden">
                {openJobs.map((j) => (
                  <div
                    key={j.id}
                    className="rounded-2xl border border-primary-200/70 border-l-4 border-l-primary-500 bg-primary-50/50 p-4 dark:border-primary-800/50 dark:bg-primary-950/30"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-lg font-bold text-primary-900 dark:text-primary-100">
                          {j.input_product_name ?? `#${j.input_product_id}`}
                        </p>
                        <p className="mt-0.5 text-base text-ink">{j.input_brand_name ?? `#${j.input_brand_id}`}</p>
                        <p className="mt-2 v2-mono text-sm text-ink-muted">{formatDateTime(j.opened_at)}</p>
                      </div>
                      <Badge tone="primary">Open</Badge>
                    </div>
                    <div className="mt-4">
                      <Link to={`/operations/processing/${j.id}?from=open`} className="block">
                        <Button className="w-full" rightIcon={<ArrowRight className="h-4 w-4" />}>
                          Continue job
                        </Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>

              <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />

              <p className="mt-4 text-sm text-ink-subtle">
                {openJobs.length} open job{openJobs.length === 1 ? "" : "s"}
              </p>
            </>
          )}
        </CardBody>
      </Card>

      <Modal
        open={jobOpen}
        onClose={closeJobDialog}
        size="md"
        headerIcon={<Cog className="h-5 w-5" />}
        title="Open processing job"
        description="Pick the raw product and brand you are cleaning or grading."
        footer={
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-ink-muted">
              {selectedProductLabel ? (
                <>
                  Starting job for{" "}
                  <span className="font-semibold text-ink">{selectedProductLabel}</span>
                </>
              ) : (
                "Select product and brand to continue"
              )}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={closeJobDialog} disabled={saving}>
                Cancel
              </Button>
              <Button
                type="submit"
                form="open-processing-job-form"
                loading={saving}
                disabled={!form.input_product_id || !form.input_brand_id}
                leftIcon={<Plus className="h-4 w-4" />}
              >
                Open job
              </Button>
            </div>
          </div>
        }
      >
        <form id="open-processing-job-form" onSubmit={submit} className="space-y-4">
          <FormField label="Input product" required hint="Commodity being processed">
            {() => (
              <AsyncSearchCombobox
                value={form.input_product_id ? Number(form.input_product_id) : null}
                onChange={(id, opt) => {
                  setForm({
                    ...form,
                    input_product_id: id != null ? String(id) : "",
                    input_brand_id: "",
                  });
                  setSelectedProductLabel(opt?.label ?? "");
                }}
                searchFn={searchProducts}
                placeholder="Search product…"
                emptyText="No matching product"
              />
            )}
          </FormField>
          <FormField label="Input brand" required hint="Brand of the raw stock">
            {() => (
              <AsyncSearchCombobox
                value={form.input_brand_id ? Number(form.input_brand_id) : null}
                onChange={(id) =>
                  setForm({ ...form, input_brand_id: id != null ? String(id) : "" })
                }
                searchFn={searchBrands}
                placeholder="Search brand…"
                emptyText="No matching brand"
                disabled={!form.input_product_id}
              />
            )}
          </FormField>
        </form>
      </Modal>
    </>
  );
}
