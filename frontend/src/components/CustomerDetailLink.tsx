import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Customer } from "../api/client";
import { formatAddressMultiline } from "../lib/address";
import { formatInr } from "../lib/format";
import Badge from "./ui/Badge";
import Banner from "./ui/Banner";
import Button from "./ui/Button";
import Modal from "./ui/Modal";
import Skeleton from "./ui/Skeleton";

type Props = {
  customerId: number;
  customerName?: string | null;
};

export default function CustomerDetailLink({ customerId, customerName }: Props) {
  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const openModal = () => {
    setOpen(true);
    setError("");
    if (customer?.id === customerId) return;
    setLoading(true);
    api
      .get<Customer>(`/api/customers/${customerId}`)
      .then(setCustomer)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load customer"))
      .finally(() => setLoading(false));
  };

  const close = () => {
    setOpen(false);
  };

  const address = customer ? formatAddressMultiline(customer) : "";

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        className="inline-flex rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
        title={customerName ? `View ${customerName}` : "View customer"}
      >
        <Badge tone="info" size="sm" className="cursor-pointer hover:bg-sky-100 dark:hover:bg-sky-900/50">
          Job work
        </Badge>
      </button>

      <Modal
        open={open}
        onClose={close}
        title={customer?.name ?? customerName ?? "Customer"}
        description="Job work material owner"
        size="sm"
        footer={
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={close}>
              Close
            </Button>
            <Link to={`/accounts/customers/${customerId}`} onClick={close}>
              <Button variant="secondary">Account statement</Button>
            </Link>
          </div>
        }
      >
        {error && (
          <Banner tone="danger" className="mb-4">
            {error}
          </Banner>
        )}
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : customer ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Phone</dt>
              <dd className="mt-0.5 text-ink">{customer.phone ?? "—"}</dd>
            </div>
            {customer.alternate_phone ? (
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Alternate phone</dt>
                <dd className="mt-0.5 text-ink">{customer.alternate_phone}</dd>
              </div>
            ) : null}
            <div>
              <dt className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">Address</dt>
              <dd className="mt-0.5 whitespace-pre-line text-ink">{address || "—"}</dd>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">They owe me</dt>
                <dd className="v2-mono mt-0.5 font-semibold text-emerald-700 dark:text-emerald-300">
                  {formatInr(customer.debit_balance)}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-subtle">I owe them</dt>
                <dd className="v2-mono mt-0.5 font-semibold text-amber-700 dark:text-amber-300">
                  {formatInr(customer.credit_balance)}
                </dd>
              </div>
            </div>
          </dl>
        ) : !error ? (
          <p className="text-sm text-ink-muted">No customer details available.</p>
        ) : null}
      </Modal>
    </>
  );
}
