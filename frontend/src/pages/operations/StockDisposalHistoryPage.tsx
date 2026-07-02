import { useCallback, useEffect, useState } from "react";
import { api, DEFAULT_PAGE_LIMIT, idempotencyVoidAuthHeaders, newIdempotencyKey, type PageOut } from "../../api/client";
import OperationPageHeader from "../../components/OperationPageHeader";
import Button from "../../components/ui/Button";
import VoidConfirmDialog from "../../components/ui/VoidConfirmDialog";
import PaginationBar from "../../components/ui/PaginationBar";
import { VoidPill } from "../../components/ui/StatusPill";
import { toast } from "../../components/ui/Toaster";
import { cn } from "../../lib/cn";
import { formatQtyKg } from "../../lib/format";

type DisposalRecord = {
  id: number;
  location_name?: string;
  product_name?: string;
  brand_name?: string;
  bag_type_name?: string;
  bag_count: number;
  loose_kg: string;
  quantity_kg: string;
  reason?: string | null;
  operation_at: string;
  voided_at?: string | null;
};

export default function StockDisposalHistoryPage() {
  const [rows, setRows] = useState<DisposalRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [voidTarget, setVoidTarget] = useState<DisposalRecord | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<DisposalRecord>>(`/api/operations/stock-disposal?limit=${limit}&offset=${offset}`)
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

  const confirmVoid = async (authorizationPassword: string) => {
    if (!voidTarget) return;
    setVoidAuthError("");
    try {
      await api.post(
        `/api/operations/stock-disposal/${voidTarget.id}/void`,
        {},
        { headers: idempotencyVoidAuthHeaders(newIdempotencyKey(), authorizationPassword) }
      );
      toast.success("Disposal voided — stock restored");
      setVoidTarget(null);
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Void failed";
      if (msg.toLowerCase().includes("authorization") || msg.toLowerCase().includes("password")) {
        setVoidAuthError(msg);
      } else {
        toast.error(msg);
      }
      throw e;
    }
  };

  return (
    <>
      <OperationPageHeader
        title="Stock disposal history"
        subtitle="All disposals — newest first"
        formTo="/operations/stock-disposal"
        historyTo="/histories/stock-disposal"
        mode="history"
      />

      <div className="card card--plain">
        {loading ? (
          <p className="hint">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <p>No disposals yet.</p>
          </div>
        ) : (
          <div className="v2-table-frame table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Location</th>
                  <th>Product</th>
                  <th>Bag type</th>
                  <th className="col-num">Qty</th>
                  <th>Reason</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const voided = Boolean(r.voided_at);
                  return (
                    <tr key={r.id} className={cn(voided && "opacity-65")}>
                      <td>{new Date(r.operation_at).toLocaleString()}</td>
                      <td>{r.location_name}</td>
                      <td>
                        {r.product_name} · {r.brand_name}
                      </td>
                      <td className={cn(voided && "line-through")}>
                        {r.bag_type_name}
                        {r.bag_count > 0 ? ` (${r.bag_count} bags)` : ` (${r.loose_kg} kg loose)`}
                      </td>
                      <td className={cn("col-num", voided && "line-through")}>
                        {formatQtyKg(r.quantity_kg)}
                      </td>
                      <td>{r.reason || "—"}</td>
                      <td>
                        {voided ? (
                          <VoidPill when={r.voided_at} />
                        ) : (
                          <Button type="button" variant="danger" size="sm" onClick={() => setVoidTarget(r)}>
                            Void
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
      </div>

      <VoidConfirmDialog
        open={voidTarget != null}
        title="Void this disposal?"
        description="Reverse this disposal and restore stock?"
        confirmLabel="Void"
        onConfirm={confirmVoid}
        onClose={() => {
          setVoidAuthError("");
          setVoidTarget(null);
        }}
        authError={voidAuthError || undefined}
      />
    </>
  );
}
