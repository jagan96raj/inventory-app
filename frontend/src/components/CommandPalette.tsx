import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, Combobox, Transition } from "@headlessui/react";
import {
  Banknote,
  BookOpen,
  Boxes,
  Briefcase,
  ClipboardList,
  ChevronRight,
  HandCoins,
  IndianRupee,
  LayoutDashboard,
  LogIn,
  MapPin,
  Package,
  PackagePlus,
  ReceiptText,
  Search,
  ShoppingCart,
  Tag,
  Truck,
  Users,
  Wallet,
  Wheat,
} from "lucide-react";
import { cn } from "../lib/cn";
import {
  api,
  type BillListItem,
  type Customer,
  type PageOut,
  type Product,
} from "../api/client";

type Item = {
  id: string;
  label: string;
  hint?: string;
  to: string;
  icon: typeof Search;
  section: string;
};

const NAV_ITEMS: Item[] = [
  { id: "nav:dashboard", label: "Dashboard", to: "/dashboard", icon: LayoutDashboard, section: "Navigate" },
  { id: "nav:sales", label: "Sales bills", to: "/sales-bills", icon: ShoppingCart, section: "Navigate" },
  { id: "nav:purchase", label: "Purchase bills", to: "/purchase-bills", icon: PackagePlus, section: "Navigate" },
  { id: "nav:payments", label: "Payments", to: "/payments", icon: IndianRupee, section: "Navigate" },
  { id: "nav:customers", label: "Customers", to: "/customers", icon: Users, section: "Navigate" },
  { id: "nav:job-work", label: "Job work orders", to: "/job-work", icon: Briefcase, section: "Navigate" },
  { id: "nav:job-work-fulfillment", label: "Job work fulfillment", to: "/job-work/fulfillment", icon: Truck, section: "Navigate" },
  { id: "nav:inventory", label: "Inventory", to: "/inventory", icon: Boxes, section: "Navigate" },
  { id: "nav:fulfillment", label: "Bill fulfillment", to: "/fulfillment", icon: Truck, section: "Navigate" },
  { id: "nav:fulfillment-history", label: "Fulfillment audit log", to: "/histories/fulfillment", icon: Truck, section: "Navigate" },
  { id: "nav:audit-log", label: "Audit log", to: "/histories/audit", icon: ClipboardList, section: "Navigate" },
  { id: "nav:login-history", label: "Login history", to: "/histories/logins", icon: LogIn, section: "Navigate" },
  { id: "nav:processing", label: "Processing", to: "/operations/processing", icon: Wheat, section: "Navigate" },
  { id: "nav:processing-history", label: "Processing history", to: "/histories/processing", icon: Wheat, section: "Navigate" },
  { id: "nav:accounts", label: "Accounts dashboard", to: "/accounts", icon: Wallet, section: "Accounts" },
  { id: "nav:cashbook", label: "Cash book", to: "/accounts/cashbook", icon: BookOpen, section: "Accounts" },
  { id: "nav:cust-balances", label: "Customer balances", to: "/accounts/customers", icon: HandCoins, section: "Accounts" },
  { id: "nav:bank-accounts", label: "Accounts", to: "/accounts/bank-accounts", icon: Banknote, section: "Accounts" },
  { id: "nav:expense-categories", label: "Expense categories", to: "/accounts/expense-categories", icon: ReceiptText, section: "Accounts" },
  { id: "nav:book-settings", label: "Book settings", to: "/accounts/setup", icon: Wallet, section: "Accounts" },
  { id: "nav:products", label: "Products", to: "/products", icon: Wheat, section: "Masters" },
  { id: "nav:brands", label: "Brands", to: "/brands", icon: Tag, section: "Masters" },
  { id: "nav:bag-types", label: "Bag types", to: "/bag-types", icon: Package, section: "Masters" },
  { id: "nav:locations", label: "Locations", to: "/locations", icon: MapPin, section: "Masters" },
];

const ACTION_ITEMS: Item[] = [
  { id: "act:new-sales", label: "New sales bill", to: "/sales-bills/new", icon: ShoppingCart, section: "Quick actions" },
  { id: "act:new-purchase", label: "New purchase bill", to: "/purchase-bills/new", icon: PackagePlus, section: "Quick actions" },
  { id: "act:record-payment", label: "Record payment", to: "/payments/new", icon: IndianRupee, section: "Quick actions" },
  { id: "act:new-expense", label: "Record expense", to: "/accounts/cashbook/new?type=expense", icon: ReceiptText, section: "Quick actions" },
  { id: "act:new-income", label: "Record income", to: "/accounts/cashbook/new?type=income", icon: HandCoins, section: "Quick actions" },
  { id: "act:new-transfer", label: "Cash ↔ Bank transfer", to: "/accounts/cashbook/new?type=transfer", icon: Banknote, section: "Quick actions" },
];

const PALETTE_SEARCH_LIMIT = 20;

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function CommandPalette({ open, onClose }: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [bills, setBills] = useState<BillListItem[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setBills([]);
    setCustomers([]);
    setProducts([]);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) {
      setBills([]);
      setCustomers([]);
      setProducts([]);
      setSearching(false);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      const params = `search=${encodeURIComponent(q)}&limit=${PALETTE_SEARCH_LIMIT}&offset=0`;
      void (async () => {
        try {
          const [sales, purchase, custs, prods] = await Promise.all([
            api.get<PageOut<BillListItem>>(`/api/bills?bill_type=sales&${params}`).catch(() => ({ items: [] })),
            api.get<PageOut<BillListItem>>(`/api/bills?bill_type=purchase&${params}`).catch(() => ({ items: [] })),
            api.get<PageOut<Customer>>(`/api/customers?${params}`).catch(() => ({ items: [] })),
            api.get<PageOut<Product>>(`/api/products?${params}`).catch(() => ({ items: [] })),
          ]);
          if (cancelled) return;
          setBills([...sales.items, ...purchase.items]);
          setCustomers(custs.items);
          setProducts(prods.items);
        } catch {
          if (!cancelled) {
            setBills([]);
            setCustomers([]);
            setProducts([]);
          }
        } finally {
          if (!cancelled) setSearching(false);
        }
      })();
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  const items: Item[] = useMemo(() => {
    const billItems: Item[] = bills.map((b) => ({
      id: `bill:${b.id}`,
      label: `${b.bill_number} · ${b.customer_name ?? "—"}`,
      hint: b.bill_type === "sales" ? "Sales bill" : "Purchase bill",
      to: `${b.bill_type === "sales" ? "/sales-bills" : "/purchase-bills"}/${b.id}`,
      icon: b.bill_type === "sales" ? ShoppingCart : PackagePlus,
      section: "Bills",
    }));
    const customerItems: Item[] = customers.map((c) => ({
      id: `cust:${c.id}`,
      label: c.name,
      hint: c.phone ?? c.district ?? "Customer",
      to: "/customers",
      icon: Users,
      section: "Customers",
    }));
    const productItems: Item[] = products.map((p) => ({
      id: `prod:${p.id}`,
      label: p.product_name,
      hint: "Product",
      to: "/products",
      icon: Wheat,
      section: "Products",
    }));
    const staticItems = [...ACTION_ITEMS, ...NAV_ITEMS];
    if (!query.trim()) return staticItems;
    return [...staticItems.filter((it) => it.label.toLowerCase().includes(query.trim().toLowerCase())), ...billItems, ...customerItems, ...productItems];
  }, [bills, customers, products, query]);

  const filtered = useMemo(() => items.slice(0, 30), [items]);

  const grouped = useMemo(() => {
    const map = new Map<string, Item[]>();
    for (const it of filtered) {
      const arr = map.get(it.section) ?? [];
      arr.push(it);
      map.set(it.section, arr);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const handleSelect = (it: Item | null) => {
    if (!it) return;
    onClose();
    navigate(it.to);
  };

  return (
    <Transition show={open} as={Fragment}>
      <Dialog onClose={onClose} className="relative z-[70]">
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-150"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
        </Transition.Child>
        <div className="fixed inset-0 flex items-start justify-center px-4 py-[10vh]">
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-150"
            enterFrom="opacity-0 -translate-y-2 scale-95"
            enterTo="opacity-100 translate-y-0 scale-100"
            leave="ease-in duration-100"
            leaveFrom="opacity-100 scale-100"
            leaveTo="opacity-0 scale-95"
          >
            <Dialog.Panel className="w-full max-w-xl overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
              <Combobox onChange={handleSelect} nullable>
                <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                  <Search className="h-4 w-4 text-ink-subtle" aria-hidden="true" />
                  <Combobox.Input
                    autoFocus
                    placeholder="Search bills, customers, products, or jump…"
                    className="w-full border-0 bg-transparent p-0 text-sm text-ink placeholder:text-ink-subtle focus:outline-none focus:ring-0"
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <kbd className="hidden v2-mono rounded border border-line bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-subtle sm:inline">
                    Esc
                  </kbd>
                </div>
                <Combobox.Options static className="max-h-[60vh] overflow-y-auto py-2">
                  {searching ? (
                    <p className="px-4 py-8 text-center text-sm text-ink-muted">Searching…</p>
                  ) : grouped.length === 0 ? (
                    <p className="px-4 py-8 text-center text-sm text-ink-muted">No results</p>
                  ) : (
                    grouped.map(([section, group]) => (
                      <div key={section} className="px-2">
                        <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">
                          {section}
                        </p>
                        {group.map((it) => (
                          <Combobox.Option
                            key={it.id}
                            value={it}
                            className={({ active }) =>
                              cn(
                                "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
                                active ? "bg-primary-50 dark:bg-primary-900/30" : "text-ink"
                              )
                            }
                          >
                            <it.icon className="h-4 w-4 text-ink-muted" />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-ink">{it.label}</p>
                              {it.hint && <p className="truncate text-xs text-ink-subtle">{it.hint}</p>}
                            </div>
                            <ChevronRight className="h-4 w-4 text-ink-subtle" />
                          </Combobox.Option>
                        ))}
                      </div>
                    ))
                  )}
                </Combobox.Options>
                <div className="flex items-center justify-between gap-2 border-t border-line bg-surface-subtle px-4 py-2 text-[11px] text-ink-subtle">
                  <span>
                    <kbd className="v2-mono">↑↓</kbd> navigate · <kbd className="v2-mono">Enter</kbd> open
                  </span>
                  <span>{filtered.length} result{filtered.length === 1 ? "" : "s"}</span>
                </div>
              </Combobox>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
}
