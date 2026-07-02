import MasterCrud from "../components/MasterCrud";

export default function BrandsPage() {
  return (
    <MasterCrud
      title="Brands"
      subtitle="Millers, traders, and brand labels on stock"
      path="/brands"
      fields={[{ key: "name", label: "Name" }]}
      columns={[{ key: "name", label: "Name" }]}
      getInitial={() => ({ name: "" })}
    />
  );
}
