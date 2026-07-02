import { Navigate, useParams } from "react-router-dom";

/** Deep links to deliver still work — opens the dialog on the fulfillment list. */
export default function FulfillmentDeliverPage() {
  const { lineId } = useParams();
  return <Navigate to={`/fulfillment?action=deliver&line=${lineId}`} replace />;
}
