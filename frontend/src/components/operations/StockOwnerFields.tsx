import FormField from "../ui/FormField";
import Select from "../ui/Select";
import AsyncSearchCombobox from "../ui/AsyncSearchCombobox";
import { searchCustomers } from "../../lib/masterSearch";

export type StockOwnerValue = {
  owner_type: "owned" | "job_work";
  customer_id: string;
};

type Props = {
  value: StockOwnerValue;
  onChange: (next: StockOwnerValue) => void;
  onOwnerChange?: () => void;
  customerInitialLabel?: string;
};

export default function StockOwnerFields({
  value,
  onChange,
  onOwnerChange,
  customerInitialLabel,
}: Props) {
  return (
    <>
      <FormField label="Stock owner" required>
        {({ id }) => (
          <Select
            id={id}
            value={value.owner_type}
            onChange={(e) => {
              const v = e.target.value as "owned" | "job_work";
              onChange({ owner_type: v, customer_id: "" });
              onOwnerChange?.();
            }}
          >
            <option value="owned">Owned stock</option>
            <option value="job_work">Job work (customer)</option>
          </Select>
        )}
      </FormField>
      {value.owner_type === "job_work" && (
        <FormField label="Customer" required>
          {() => (
            <AsyncSearchCombobox
              value={value.customer_id ? Number(value.customer_id) : null}
              onChange={(id) => {
                onChange({ ...value, customer_id: id != null ? String(id) : "" });
                onOwnerChange?.();
              }}
              searchFn={searchCustomers}
              placeholder="Search customer…"
              emptyText="No matching customer"
              initialLabel={customerInitialLabel}
            />
          )}
        </FormField>
      )}
    </>
  );
}
