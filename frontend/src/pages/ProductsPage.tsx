import MasterCrud from "../components/MasterCrud";

export default function ProductsPage() {
  return (
    <MasterCrud
      title="Products"
      subtitle="Pulses, millets, cereals and other commodities you trade"
      path="/products"
      fields={[{ key: "product_name", label: "Product name" }]}
      columns={[{ key: "product_name", label: "Name" }]}
      getInitial={() => ({ product_name: "" })}
    />
  );
}
