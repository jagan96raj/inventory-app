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

type BagChangeRecord = {
  id: number;
  location_name?: string;
  product_name?: string;
  brand_name?: string;
  from_bag_type_name?: string;
  from_bag_count: number;
  from_loose_kg: string;
  from_quantity_kg: string;
  quantity_loss_kg: string;
  operation_at: string;
  voided_at?: string | null;
  to_lines: {
    to_bag_type_name?: string;
    bag_count: number;
    loose_kg: string;
    quantity_kg: string;
  }[];
};

export default function BagChangeHistoryPage() {
  const [rows, setRows] = useState<BagChangeRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [voidTarget, setVoidTarget] = useState<BagChangeRecord | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<BagChangeRecord>>(`/api/operations/bag-change?limit=${limit}&offset=${offset}`)
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
        `/api/operations/bag-change/${voidTarget.id}/void`,
        {},
        { headers: idempotencyVoidAuthHeaders(newIdempotencyKey(), authorizationPassword) }
      );
      toast.success("Bag change voided — stock restored");
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
        title="Bag change history"
        subtitle="All bag changes — newest first"
        formTo="/operations/bag-change"
        historyTo="/histories/bag-change"
        mode="history"
      />

      <div className="card card--plain">
        {loading ? (
          <p className="hint">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <p>No bag changes yet.</p>
          </div>
        ) : (
          <div className="v2-table-frame table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Location</th>
                  <th>Product</th>
                  <th>From</th>
                  <th className="col-num">From kg</th>
                  <th className="col-num">Loss kg</th>
                  <th>To lines</th>
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
                        {r.from_bag_type_name} (
                        {r.from_bag_count > 0 ? `${r.from_bag_count} bags` : `${r.from_loose_kg} kg loose`})
                      </td>
                      <td className={cn("col-num", voided && "line-through")}>
                        {formatQtyKg(r.from_quantity_kg)}
                      </td>
                      <td className={cn("col-num", voided && "line-through")}>
                        {formatQtyKg(r.quantity_loss_kg)}
                      </td>
                      <td className={cn(voided && "line-through")}>
                        {r.to_lines.map((tl, i) => (
                          <span key={i} className="operations-history-line">
                            {tl.to_bag_type_name}: {tl.bag_count > 0 ? `${tl.bag_count} bags` : `${tl.loose_kg} kg`} (
                            {formatQtyKg(tl.quantity_kg)})
                          </span>
                        ))}
                      </td>
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
        title="Void this bag change?"
        description="Reverse this bag change and restore stock?"
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
