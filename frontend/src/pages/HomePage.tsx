import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Boxes,
  IndianRupee,
  PackagePlus,
  Recycle,
  Repeat,
  ShoppingCart,
  Sparkles,
  Truck,
  Users,
  Wheat,
} from "lucide-react";
import Button from "../components/ui/Button";
import PageHeader from "../components/ui/PageHeader";
import { Card, CardBody } from "../components/ui/Card";

const ACTIONS = [
  {
    to: "/inventory",
    title: "Inventory",
    desc: "Stock grouped by location — bags, loose kg and totals.",
    Icon: Boxes,
    color: "from-sky-500 to-cyan-500",
  },
  {
    to: "/sales-bills",
    title: "Sales bills",
    desc: "Outbound sales, delivery from bill location, payments.",
    Icon: ShoppingCart,
    color: "from-emerald-500 to-teal-500",
  },
  {
    to: "/purchase-bills",
    title: "Purchase bills",
    desc: "Inbound purchases, multi-location receive, supplier credit.",
    Icon: PackagePlus,
    color: "from-primary-500 to-primary-700",
  },
  {
    to: "/fulfillment",
    title: "Fulfillment",
    desc: "Deliver sales and receive purchase — queue by bill.",
    Icon: Truck,
    color: "from-amber-500 to-orange-500",
  },
  {
    to: "/payments",
    title: "Payments",
    desc: "Cash, bank and balance modes against open bills.",
    Icon: IndianRupee,
    color: "from-rose-500 to-pink-500",
  },
  {
    to: "/customers",
    title: "Customers",
    desc: "Parties, credit and debit balances.",
    Icon: Users,
    color: "from-primary-500 to-primary-700",
  },
];

const OPS = [
  { to: "/operations/processing", label: "Processing", Icon: Wheat },
  { to: "/operations/bag-change", label: "Bag change", Icon: Repeat },
  { to: "/operations/product-transfer", label: "Product transfer", Icon: Truck },
  { to: "/operations/stock-disposal", label: "Stock disposal", Icon: Recycle },
];

const TIPS = [
  {
    title: "Bills first",
    body: "Create a sales or purchase bill — stock moves only on fulfillment, not on submit.",
  },
  {
    title: "Concurrent-safe stock",
    body: "Row locks (v12.3) and CHECK constraints prevent overselling under load.",
  },
  {
    title: "Voidable history",
    body: "Wrong payment? Wrong delivery? Void it — cascades and stock restore are automatic.",
  },
];

export default function HomePage() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-1">
            <Sparkles className="h-3.5 w-3.5" /> v13.0 UI
          </span>
        }
        title="Welcome to GrainTrack"
        subtitle="Manage stock by location, bill sales and purchases, fulfill deliveries, and run warehouse operations — all in one place."
        actions={
          <Button rightIcon={<ArrowRight className="h-4 w-4" />} onClick={() => navigate("/dashboard")}>
            Open dashboard
          </Button>
        }
      />

      <section className="mb-8">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ACTIONS.map((a, i) => (
            <motion.div
              key={a.to}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: i * 0.04 }}
            >
              <Link to={a.to} className="group block focus:outline-none">
                <Card interactive className="h-full">
                  <CardBody>
                    <div className="flex items-start justify-between gap-3">
                      <span
                        className={`grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br text-white shadow-soft ${a.color}`}
                      >
                        <a.Icon className="h-6 w-6" />
                      </span>
                      <ArrowRight className="h-4 w-4 text-ink-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-primary-600" />
                    </div>
                    <h3 className="mt-4 text-base font-semibold text-ink">{a.title}</h3>
                    <p className="mt-1 text-sm text-ink-muted">{a.desc}</p>
                  </CardBody>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card>
          <CardBody>
            <h3 className="text-base font-semibold text-ink">Warehouse operations</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Bag change, transfer, processing, and disposal — adjust stock without touching bills.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {OPS.map((o) => (
                <Link
                  key={o.to}
                  to={o.to}
                  className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink-muted transition-colors hover:border-primary-300 hover:text-ink"
                >
                  <o.Icon className="h-4 w-4" /> {o.label}
                </Link>
              ))}
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <h3 className="text-base font-semibold text-ink">How it fits together</h3>
            <ul className="mt-3 space-y-3">
              {TIPS.map((t) => (
                <li key={t.title} className="flex gap-3">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-500" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-semibold text-ink">{t.title}</p>
                    <p className="text-sm text-ink-muted">{t.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      </section>
    </>
  );
}
