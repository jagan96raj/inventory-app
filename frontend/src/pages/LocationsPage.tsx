import AddressSummaryLink from "../components/AddressSummaryLink";
import PartyMasterCrud from "../components/PartyMasterCrud";
import { addressFormFields } from "../lib/addressFormFields";
type Location = {
  id: number;
  name: string;
  address_line: string | null;
  district: string | null;
  state: string | null;
  pin_code: string | null;
};

export default function LocationsPage() {
  return (
    <PartyMasterCrud<Location>
      kind="location"
      title="Locations"
      subtitle="Warehouses, mills, and godowns where stock is held"
      path="/locations"
      fields={[
        {
          key: "name",
          label: "Location name",
          section: "basic",
          placeholder: "e.g. Main godown, Mill store",
        },
        ...addressFormFields,
      ]}
      columns={[
        { key: "name", label: "Name" },
        {
          key: "address_line",
          label: "Address",
          render: (r) => <AddressSummaryLink address={r} title={`${r.name} — address`} />,
        },
      ]}
      getInitial={() => ({
        name: "",
        address_line: "",
        district: "",
        state: "",
        pin_code: "",
      })}
    />
  );
}
