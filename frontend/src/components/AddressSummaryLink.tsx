import { useState } from "react";
import {
  formatAddressMultiline,
  formatDistrictState,
  hasAddress,
  type AddressFields,
} from "../lib/address";
import Modal from "./ui/Modal";
import Button from "./ui/Button";

type Props = {
  address: AddressFields | null | undefined;
  /** Modal title when expanded */
  title?: string;
};

export default function AddressSummaryLink({ address, title = "Full address" }: Props) {
  const [open, setOpen] = useState(false);

  if (!hasAddress(address)) {
    return <span className="text-sm text-ink-subtle">—</span>;
  }

  const summary = formatDistrictState(address);
  const full = formatAddressMultiline(address);
  const label = summary ?? "View address";

  return (
    <>
      <button
        type="button"
        className="text-left text-sm text-primary-600 underline-offset-2 hover:underline dark:text-primary-400"
        onClick={() => setOpen(true)}
      >
        {label}
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={title}
        size="sm"
        footer={
          <Button variant="secondary" onClick={() => setOpen(false)}>
            Close
          </Button>
        }
      >
        <p className="whitespace-pre-line text-base leading-relaxed text-ink">{full}</p>
      </Modal>
    </>
  );
}
