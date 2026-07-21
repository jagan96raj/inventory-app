import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  api,
  DEFAULT_PAGE_LIMIT,
  idempotencyVoidAuthHeaders,
  newIdempotencyKey,
  type PageOut,
} from "../../api/client";
import { isVoidAuthErrorMessage } from "../../lib/masterCrudApi";
import OperationPageHeader from "../OperationPageHeader";
import Button from "../ui/Button";
import VoidConfirmDialog from "../ui/VoidConfirmDialog";
import PaginationBar from "../ui/PaginationBar";
import { VoidPill } from "../ui/StatusPill";
import { toast } from "../ui/Toaster";

export type OperationHistoryRecord = {
  id: number;
  voided_at?: string | null;
};

export type OperationHistoryPageProps<T extends OperationHistoryRecord> = {
  title: string;
  subtitle: string;
  formTo: string;
  historyTo: string;
  listPath: string;
  voidPath: (id: number) => string;
  emptyMessage: string;
  voidSuccessMessage: string;
  voidDialogTitle: string;
  voidDialogDescription: string;
  renderTable: (rows: T[], onVoid: (row: T) => void) => ReactNode;
};

export function OperationHistoryVoidCell({
  voidedAt,
  onVoid,
}: {
  voidedAt?: string | null;
  onVoid: () => void;
}) {
  const voided = Boolean(voidedAt);
  return (
    <td>
      {voided ? (
        <VoidPill when={voidedAt} />
      ) : (
        <Button type="button" variant="danger" size="sm" onClick={onVoid}>
          Void
        </Button>
      )}
    </td>
  );
}

export default function OperationHistoryPage<T extends OperationHistoryRecord>({
  title,
  subtitle,
  formTo,
  historyTo,
  listPath,
  voidPath,
  emptyMessage,
  voidSuccessMessage,
  voidDialogTitle,
  voidDialogDescription,
  renderTable,
}: OperationHistoryPageProps<T>) {
  const [rows, setRows] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [voidTarget, setVoidTarget] = useState<T | null>(null);
  const [voidAuthError, setVoidAuthError] = useState("");
  const limit = DEFAULT_PAGE_LIMIT;

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<PageOut<T>>(`${listPath}?limit=${limit}&offset=${offset}`)
      .then((page) => {
        setRows(page.items);
        setTotal(page.total);
      })
      .catch(() => {
        setRows([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  }, [listPath, limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const confirmVoid = async (authorizationPassword: string) => {
    if (!voidTarget) return;
    setVoidAuthError("");
    try {
      await api.post(
        voidPath(voidTarget.id),
        {},
        { headers: idempotencyVoidAuthHeaders(newIdempotencyKey(), authorizationPassword) }
      );
      toast.success(voidSuccessMessage);
      setVoidTarget(null);
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Void failed";
      if (isVoidAuthErrorMessage(msg)) {
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
        title={title}
        subtitle={subtitle}
        formTo={formTo}
        historyTo={historyTo}
        mode="history"
      />

      <div className="card card--plain">
        {loading ? (
          <p className="hint">Loading…</p>
        ) : rows.length === 0 ? (
          <div className="empty-state">
            <p>{emptyMessage}</p>
          </div>
        ) : (
          <div className="v2-table-frame table-scroll">{renderTable(rows, setVoidTarget)}</div>
        )}
        <PaginationBar total={total} limit={limit} offset={offset} onPageChange={setOffset} />
      </div>

      <VoidConfirmDialog
        open={voidTarget != null}
        title={voidDialogTitle}
        description={voidDialogDescription}
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
