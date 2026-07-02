import { Navigate, useParams, useSearchParams } from "react-router-dom";

/** Deep links to return still work — opens the dialog on the fulfillment list. */
export default function FulfillmentReturnPage() {
  const { lineId } = useParams();
  const [searchParams] = useSearchParams();
  const parent = searchParams.get("parent_entry_id");
  const qs = parent ? `&parent_entry_id=${parent}` : "";
  return <Navigate to={`/fulfillment?action=return&line=${lineId}${qs}`} replace />;
}
