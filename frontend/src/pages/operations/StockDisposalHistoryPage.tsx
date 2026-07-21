import OperationHistoryPage, {
  OperationHistoryVoidCell,
} from "../../components/operations/OperationHistoryPage";
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
  return (
    <OperationHistoryPage<DisposalRecord>
      title="Stock disposal history"
      subtitle="All disposals — newest first"
      formTo="/operations/stock-disposal"
      historyTo="/histories/stock-disposal"
      listPath="/api/operations/stock-disposal"
      voidPath={(id) => `/api/operations/stock-disposal/${id}/void`}
      emptyMessage="No disposals yet."
      voidSuccessMessage="Disposal voided — stock restored"
      voidDialogTitle="Void this disposal?"
      voidDialogDescription="Reverse this disposal and restore stock?"
      renderTable={(rows, onVoid) => (
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
                  <OperationHistoryVoidCell voidedAt={r.voided_at} onVoid={() => onVoid(r)} />
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    />
  );
}
