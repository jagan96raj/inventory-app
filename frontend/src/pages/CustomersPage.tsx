import { useNavigate } from "react-router-dom";
import { HandCoins, Wallet } from "lucide-react";
import { formatInr } from "../lib/format";
import { formatCustomerName } from "../lib/customerDisplay";
import AddressSummaryLink from "../components/AddressSummaryLink";
import PartyMasterCrud from "../components/PartyMasterCrud";
import { addressFormFields } from "../lib/addressFormFields";
import IconButton from "../components/ui/IconButton";
import Button from "../components/ui/Button";

type Customer = {
  id: number;
  name: string;
  address_line: string | null;
  district: string | null;
  state: string | null;
  pin_code: string | null;
  phone: string | null;
  alternate_phone: string | null;
  credit_balance: string;
  debit_balance: string;
};

export default function CustomersPage() {
  const navigate = useNavigate();

  return (
    <PartyMasterCrud<Customer>
      kind="customer"
      searchable
      title="Customers"
      subtitle="Buyers and suppliers — credit (you owe) and debit (they owe) balances"
      path="/customers"
      fields={[
        {
          key: "name",
          label: "Customer name",
          section: "basic",
          placeholder: "Person or business name",
        },
        ...addressFormFields,
        {
          key: "phone",
          label: "Phone",
          section: "contact",
          optional: true,
          placeholder: "Primary mobile or landline",
        },
        {
          key: "alternate_phone",
          label: "Alternate phone",
          section: "contact",
          optional: true,
          placeholder: "Second contact number",
        },
        {
          key: "credit_balance",
          label: "Credit balance",
          type: "number",
          section: "balances",
          optional: true,
          createOnly: true,
          hint: "Amount you owe them (₹) — opening balance only",
        },
        {
          key: "debit_balance",
          label: "Debit balance",
          type: "number",
          section: "balances",
          optional: true,
          createOnly: true,
          hint: "Amount they owe you (₹) — opening balance only",
        },
      ]}
      columns={[
        {
          key: "name",
          label: "Name",
          render: (r) => {
            const name = formatCustomerName(r.name);
            return (
              <span
                className="block max-w-[14rem] truncate text-sm font-semibold tracking-tight text-ink sm:max-w-[18rem] md:max-w-[22rem]"
                title={name}
              >
                {name}
              </span>
            );
          },
        },
        {
          key: "phone",
          label: "Phone",
          render: (r) => (
            <span className="v2-mono whitespace-nowrap text-sm text-ink">{r.phone || "—"}</span>
          ),
        },
        {
          key: "alternate_phone",
          label: "Alt. phone",
          render: (r) => (
            <span className="v2-mono whitespace-nowrap text-sm text-ink">
              {r.alternate_phone || "—"}
            </span>
          ),
        },
        {
          key: "address_line",
          label: "Address",
          render: (r) => (
            <AddressSummaryLink address={r} title={`${formatCustomerName(r.name)} — address`} />
          ),
        },
        {
          key: "credit_balance",
          label: "Credit (I owe)",
          render: (r) => formatInr(r.credit_balance),
        },
        {
          key: "debit_balance",
          label: "Debit (they owe)",
          render: (r) => formatInr(r.debit_balance),
        },
      ]}
      getInitial={() => ({
        name: "",
        address_line: "",
        district: "",
        state: "",
        pin_code: "",
        phone: "",
        alternate_phone: "",
        credit_balance: "",
        debit_balance: "",
      })}
      rowActions={(row) => {
        const debit = Number(row.debit_balance) > 0;
        const credit = Number(row.credit_balance) > 0;
        if (!debit && !credit) return null;
        return (
          <>
            <span className="hidden items-center gap-0.5 lg:inline-flex">
              {debit && (
                <IconButton
                  label="Pay debit"
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/customers/${row.id}/pay-debit`)}
                >
                  <HandCoins />
                </IconButton>
              )}
              {credit && (
                <IconButton
                  label="Pay credit"
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/customers/${row.id}/pay-credit`)}
                >
                  <Wallet />
                </IconButton>
              )}
            </span>
            <span className="flex w-full flex-wrap gap-2 lg:hidden">
              {debit && (
                <Button
                  size="md"
                  variant="secondary"
                  className="min-h-10 flex-1 sm:flex-none"
                  leftIcon={<HandCoins className="h-3.5 w-3.5" />}
                  onClick={() => navigate(`/customers/${row.id}/pay-debit`)}
                >
                  Pay debit
                </Button>
              )}
              {credit && (
                <Button
                  size="md"
                  variant="secondary"
                  className="min-h-10 flex-1 sm:flex-none"
                  leftIcon={<Wallet className="h-3.5 w-3.5" />}
                  onClick={() => navigate(`/customers/${row.id}/pay-credit`)}
                >
                  Pay credit
                </Button>
              )}
            </span>
          </>
        );
      }}
    />
  );
}
